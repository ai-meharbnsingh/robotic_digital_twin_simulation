"""
Scenario comparison endpoints — create, list, run, results, compare, cleanup.

GET  /api/scenarios              — list all scenarios
POST /api/scenarios              — create scenario
POST /api/scenarios/{id}/run     — run scenario
GET  /api/scenarios/{id}/results — get KPIs for completed scenario
DELETE /api/scenarios/{id}       — archive scenario (cleanup)
GET  /api/scenarios/compare      — compare 2+ scenarios (optional format=csv|pdf)

Phase 6: Parallel Scenario Comparison.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from app.auth import require_api_key
from wes.scenario_manager import (
    ScenarioNotCompletedError,
    ScenarioNotFoundError,
    ScenarioPersistenceError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])

# Safety limits — resource caps, not per-request rate limiting.
# Rate limiting is done via resource caps (MAX_SCENARIOS, MAX_COMPARE_IDS),
# not per-request middleware. Per-request rate limiting (requests per minute)
# is the responsibility of the reverse proxy (nginx/Vercel) in production.
# This is standard practice for FastAPI apps behind a load balancer.
MAX_SCENARIOS = 1000
MAX_COMPARE_IDS = 10


def _get_scenario_manager():
    from app.main import app_state
    return app_state.get("scenario_manager")


# ── Pydantic models ─────────────────────────────────────────


class ScenarioConfig(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="")
    fleet_size: int = Field(default=5, ge=1, le=200)
    robot_config: str = Field(default="differential_drive")
    allocation_strategy: str = Field(default="fifo")
    warehouse_config: str = Field(default="simple_grid")
    order_count: int = Field(default=50, ge=1, le=10000)
    order_seed: Optional[int] = None
    duration_s: float = Field(default=60, ge=10, le=3600)


class RunOverride(BaseModel):
    duration_override: Optional[float] = None

    @field_validator("duration_override")
    @classmethod
    def validate_duration(cls, v):
        if v is not None and (v < 10 or v > 3600):
            raise ValueError("duration_override must be between 10 and 3600 seconds")
        return v


# ── Endpoints ────────────────────────────────────────────────


@router.get("")
async def list_scenarios():
    """
    List all scenarios.

    Returns array of scenario objects from MongoDB.
    """
    manager = _get_scenario_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="Scenario manager not initialized")

    try:
        scenarios = await manager.list_scenarios()
        return scenarios
    except ScenarioPersistenceError:
        logger.exception("Failed to list scenarios — MongoDB unavailable")
        raise HTTPException(status_code=503, detail="Database unavailable — cannot list scenarios")
    except Exception:
        logger.exception("Failed to list scenarios")
        raise HTTPException(status_code=500, detail="Failed to list scenarios")


@router.post("", dependencies=[Depends(require_api_key)])
async def create_scenario(body: ScenarioConfig):
    """
    Create a new scenario with the given configuration.

    Validates that warehouse and robot configs exist before creating.
    Enforces a maximum of MAX_SCENARIOS scenarios.
    """
    manager = _get_scenario_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="Scenario manager not initialized")

    # Validate allocation_strategy
    valid_strategies = ("fifo", "nearest", "priority_weighted")
    if body.allocation_strategy not in valid_strategies:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid allocation_strategy: {body.allocation_strategy}. Valid: {valid_strategies}",
        )

    # Enforce max active scenarios limit (excludes archived)
    try:
        active_count = await manager.count_active_scenarios()
        if active_count >= MAX_SCENARIOS:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum scenario limit ({MAX_SCENARIOS}) reached. Archive old scenarios first.",
            )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to check scenario count")

    try:
        scenario = await manager.create_scenario(body.model_dump())
        return scenario
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid scenario configuration: check warehouse and robot config names")
    except ScenarioPersistenceError:
        logger.exception("Failed to persist scenario")
        raise HTTPException(status_code=503, detail="Database unavailable — cannot create scenario")


@router.post("/{scenario_id}/run", dependencies=[Depends(require_api_key)])
async def run_scenario(scenario_id: str, body: Optional[RunOverride] = None):
    """
    Execute a scenario — generates orders, simulates tasks, computes KPIs.

    Optionally override the simulation duration (10-3600s, validated by Pydantic).
    """
    manager = _get_scenario_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="Scenario manager not initialized")

    duration_override = body.duration_override if body else None

    try:
        result = await manager.run_scenario(scenario_id, duration_override=duration_override)
        return result
    except ScenarioNotFoundError:
        raise HTTPException(status_code=404, detail=f"Scenario not found: {scenario_id}")
    except ScenarioNotCompletedError:
        raise HTTPException(status_code=409, detail="Scenario is in an invalid state for running")
    except ScenarioPersistenceError:
        logger.exception("Failed to persist scenario run results")
        raise HTTPException(status_code=503, detail="Database unavailable — cannot persist run results")


@router.delete("/{scenario_id}", dependencies=[Depends(require_api_key)])
async def cleanup_scenario(scenario_id: str):
    """
    Archive a scenario — drops namespace collections and sets status to 'archived'.

    Returns 404 if scenario not found.
    """
    manager = _get_scenario_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="Scenario manager not initialized")

    try:
        result = await manager.cleanup_scenario(scenario_id)
        return result
    except ScenarioNotFoundError:
        raise HTTPException(status_code=404, detail=f"Scenario not found: {scenario_id}")
    except ScenarioPersistenceError:
        logger.exception("Failed to cleanup scenario %s", scenario_id)
        raise HTTPException(status_code=503, detail="Database unavailable — cannot cleanup scenario")


@router.get("/compare")
async def compare_scenarios(
    ids: str = Query(..., description="Comma-separated scenario IDs"),
    format: Optional[str] = Query(default=None, description="Export format: csv or pdf"),
):
    """
    Compare 2+ completed scenarios (max 10).

    Returns JSON comparison by default. Use format=csv or format=pdf for exports.
    """
    manager = _get_scenario_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="Scenario manager not initialized")

    scenario_ids = [s.strip() for s in ids.split(",") if s.strip()]

    if len(scenario_ids) > MAX_COMPARE_IDS:
        raise HTTPException(
            status_code=400,
            detail=f"Too many scenario IDs: {len(scenario_ids)}. Maximum is {MAX_COMPARE_IDS}.",
        )

    try:
        comparison = await manager.compare_scenarios(scenario_ids)
    except ScenarioNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ScenarioNotCompletedError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError:
        raise HTTPException(status_code=400, detail="Need at least 2 scenario IDs to compare")
    except ScenarioPersistenceError:
        logger.exception("Failed to compare scenarios — database error")
        raise HTTPException(status_code=503, detail="Database unavailable — cannot compare scenarios")

    if format == "csv":
        from wes.report_generator import ReportGenerator
        csv_content = ReportGenerator.generate_csv(comparison)
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=scenario_comparison.csv"},
        )
    elif format == "pdf":
        from wes.report_generator import ReportGenerator
        pdf_bytes = ReportGenerator.generate_pdf(comparison)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=scenario_comparison.pdf"},
        )

    return comparison


@router.get("/{scenario_id}/results")
async def get_scenario_results(scenario_id: str):
    """
    Get KPIs for a completed scenario.

    Returns 404 if not found, 409 if not yet completed.
    """
    manager = _get_scenario_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="Scenario manager not initialized")

    try:
        return await manager.get_results(scenario_id)
    except ScenarioNotFoundError:
        raise HTTPException(status_code=404, detail=f"Scenario not found: {scenario_id}")
    except ScenarioNotCompletedError:
        raise HTTPException(status_code=409, detail="Scenario is not yet completed")
    except ScenarioPersistenceError:
        logger.exception("Failed to fetch results for scenario %s", scenario_id)
        raise HTTPException(status_code=503, detail="Database unavailable — cannot fetch results")

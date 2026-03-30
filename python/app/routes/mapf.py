"""
MAPF (Multi-Agent Path Finding) endpoints — Phase 11.

POST /api/mapf/solve          — solve MAPF for given agents (CBS or PIBT)
GET  /api/mapf/status         — solver status (last solve time, conflicts)
POST /api/mapf/step           — single PIBT step (for real-time integration)
GET  /api/mapf/benchmarks     — performance metrics (solve time vs agent count)
GET  /api/mapf/congestion     — congestion hotspot data from tracker

Phase 11: Scale to 100+ Robots.
"""

import asyncio
import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.auth import require_api_key
from wes.congestion_tracker import CongestionTracker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mapf", tags=["mapf"])


# ── Solver state (module-level, shared across requests) ────────
# Protected by _solver_lock for async safety.

_solver_lock = asyncio.Lock()

_solver_state = {
    "last_solve_time_ms": 0.0,
    "last_conflicts_resolved": 0,
    "total_solves": 0,
    "benchmark_history": [],
}

# Module-level congestion tracker — updated after every solve/step
_congestion_tracker = CongestionTracker()


def _get_warehouse_graph() -> dict:
    """Build graph from the current warehouse config."""
    from app.main import app_state
    from wes.mapf_solver import CBSSolver

    wh = app_state.get("warehouse_config")
    if wh is None:
        raise HTTPException(status_code=503, detail="Warehouse config not loaded")
    return CBSSolver.build_graph_from_warehouse(wh)


def _validate_nodes_exist(graph: dict, node_ids: list[str]) -> None:
    """Validate that all node IDs exist in the warehouse graph. Raises HTTPException 400."""
    for node_id in node_ids:
        if node_id not in graph:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid node ID: '{node_id}' does not exist in warehouse graph",
            )


# ── Pydantic models ─────────────────────────────────────────


class CBSAgent(BaseModel):
    agent_id: str
    start: str
    goal: str


class PIBTAgent(BaseModel):
    agent_id: str
    position: str
    goal: str
    priority: int = Field(default=0)
    wait_time: int = Field(default=0)


MAX_AGENTS_CBS = 200  # CBS exponential complexity limit
MAX_AGENTS_PIBT = 500  # PIBT is linear, handles more
MAX_STEP_AGENTS = 200  # Step endpoint guard (real-time budget)
MAX_BENCHMARK_HISTORY = 1000  # Prevent unbounded memory growth


class SolveRequest(BaseModel):
    solver: str = Field(..., description="Solver type: 'cbs' or 'pibt'")
    agents: list[CBSAgent]
    time_limit_s: Optional[float] = Field(default=5.0, ge=0.001, le=30.0)

    @field_validator("agents")
    @classmethod
    def validate_agent_count(cls, v, info):
        solver = info.data.get("solver", "cbs")
        max_agents = MAX_AGENTS_CBS if solver == "cbs" else MAX_AGENTS_PIBT
        if len(v) > max_agents:
            raise ValueError(f"Too many agents for {solver}: max {max_agents}")
        if len(v) < 1:
            raise ValueError("At least one agent required")
        return v


class StepRequest(BaseModel):
    agents: list[PIBTAgent]


# ── Endpoints ────────────────────────────────────────────────


@router.post("/solve", dependencies=[Depends(require_api_key)])
async def mapf_solve(body: SolveRequest):
    """
    Solve MAPF for given agents using CBS or PIBT.

    CBS: optimal, offline planning. Returns full paths.
    PIBT: fast, online. Returns single-step moves.
    """
    if body.solver not in ("cbs", "pibt"):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown solver: {body.solver}. Valid: cbs, pibt",
        )

    graph = _get_warehouse_graph()

    # Validate all agent node IDs exist in graph
    all_nodes: list[str] = []
    for a in body.agents:
        all_nodes.append(a.start)
        all_nodes.append(a.goal)
    _validate_nodes_exist(graph, all_nodes)

    # Validate no duplicate agent IDs
    agent_ids = [a.agent_id for a in body.agents]
    if len(agent_ids) != len(set(agent_ids)):
        raise HTTPException(status_code=400, detail="Duplicate agent_id values in request")

    agents_dicts = [a.model_dump() for a in body.agents]

    if body.solver == "cbs":
        from wes.mapf_solver import CBSSolver

        solver = CBSSolver(
            graph=graph,
            max_agents=MAX_AGENTS_CBS,
            time_limit_s=body.time_limit_s or 5.0,
        )
        result = solver.solve(agents_dicts)

        # Update congestion tracker with final positions from paths
        if result.get("paths"):
            final_positions = {
                aid: path[-1] for aid, path in result["paths"].items() if path
            }
            _congestion_tracker.update(final_positions)

        # Update state (async-safe)
        async with _solver_lock:
            _solver_state["last_solve_time_ms"] = result["solve_time_ms"]
            _solver_state["last_conflicts_resolved"] = result["conflicts_resolved"]
            _solver_state["total_solves"] += 1
            _solver_state["benchmark_history"].append({
                "solver": "cbs",
                "agent_count": len(body.agents),
                "solve_time_ms": result["solve_time_ms"],
                "conflicts_resolved": result["conflicts_resolved"],
                "success": result["success"],
            })
            # Trim history to prevent unbounded growth
            if len(_solver_state["benchmark_history"]) > MAX_BENCHMARK_HISTORY:
                _solver_state["benchmark_history"] = _solver_state["benchmark_history"][-MAX_BENCHMARK_HISTORY:]

        return result

    else:  # pibt
        from wes.pibt_solver import PIBTSolver

        pibt_agents = [
            {
                "agent_id": a.agent_id,
                "position": a.start,
                "goal": a.goal,
                "priority": 0,
                "wait_time": 0,
            }
            for a in body.agents
        ]

        solver = PIBTSolver()
        start_t = time.monotonic()
        result = solver.step(pibt_agents, graph)
        elapsed_ms = (time.monotonic() - start_t) * 1000.0

        # Update congestion tracker with agent moves
        if result.get("moves"):
            _congestion_tracker.update(result["moves"])

        async with _solver_lock:
            _solver_state["last_solve_time_ms"] = elapsed_ms
            _solver_state["total_solves"] += 1
            _solver_state["benchmark_history"].append({
                "solver": "pibt",
                "agent_count": len(body.agents),
                "solve_time_ms": round(elapsed_ms, 3),
                "success": result["success"],
            })
            # Trim history to prevent unbounded growth
            if len(_solver_state["benchmark_history"]) > MAX_BENCHMARK_HISTORY:
                _solver_state["benchmark_history"] = _solver_state["benchmark_history"][-MAX_BENCHMARK_HISTORY:]

        return result


@router.get("/status")
async def mapf_status():
    """
    Solver status — last solve time, conflicts, total solves.
    """
    async with _solver_lock:
        return {
            "last_solve_time_ms": _solver_state["last_solve_time_ms"],
            "last_conflicts_resolved": _solver_state["last_conflicts_resolved"],
            "total_solves": _solver_state["total_solves"],
        }


@router.post("/step", dependencies=[Depends(require_api_key)])
async def mapf_step(body: StepRequest):
    """
    Single PIBT step — returns next position for each agent.

    For real-time integration with the 15Hz FMS loop.
    """
    from wes.pibt_solver import PIBTSolver

    # Guard: max agents for step endpoint
    if len(body.agents) > MAX_STEP_AGENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Too many agents for step: {len(body.agents)} exceeds max {MAX_STEP_AGENTS}",
        )

    # Validate no duplicate agent IDs
    agent_ids = [a.agent_id for a in body.agents]
    if len(agent_ids) != len(set(agent_ids)):
        raise HTTPException(status_code=400, detail="Duplicate agent_id values in request")

    graph = _get_warehouse_graph()

    # Validate all agent node IDs exist in graph
    all_nodes: list[str] = []
    for a in body.agents:
        all_nodes.append(a.position)
        all_nodes.append(a.goal)
    _validate_nodes_exist(graph, all_nodes)

    agents_dicts = [a.model_dump() for a in body.agents]

    solver = PIBTSolver()
    result = solver.step(agents_dicts, graph)

    # Update congestion tracker with agent moves
    if result.get("moves"):
        _congestion_tracker.update(result["moves"])

    return result


@router.get("/benchmarks")
async def mapf_benchmarks():
    """
    Performance metrics — solve time vs agent count for recent solves.
    """
    async with _solver_lock:
        return {
            "solves": list(_solver_state["benchmark_history"]),
            "total_solves": _solver_state["total_solves"],
        }


@router.get("/congestion")
async def mapf_congestion():
    """
    Congestion hotspot data — top bottleneck nodes and full congestion map.

    Updated after every MAPF solve/step with agent positions.
    """
    bottlenecks = _congestion_tracker.get_bottlenecks(top_n=10)
    congestion_map = _congestion_tracker.get_congestion_map()

    return {
        "congestion_map": congestion_map,
        "bottlenecks": bottlenecks,
        "total_nodes_tracked": len(congestion_map),
    }

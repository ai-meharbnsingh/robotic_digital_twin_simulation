"""
Simulation control endpoints.
GET /api/simulation/status — current simulation status
POST /api/simulation/start — start the simulation
POST /api/simulation/stop — stop the simulation
POST /api/simulation/inject-fault — inject a fault for testing
"""

import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.auth import require_api_key

router = APIRouter(prefix="/api/simulation", tags=["simulation"])


def _get_db():
    from app.main import app_state
    return app_state.get("mongo_db")


def _get_sim_state():
    from app.main import app_state
    return app_state.get("simulation_state", {})


def _set_sim_state(state: dict):
    from app.main import app_state
    app_state["simulation_state"] = state


class FaultInjection(BaseModel):
    fault_type: str  # "battery_drain", "obstacle", "network_loss", "motor_failure"
    robot_id: Optional[str] = None
    duration_s: float = 10.0
    parameters: dict[str, str | int | float | bool] = {}


@router.get("/status")
async def simulation_status():
    """Return current simulation status."""
    state = _get_sim_state()
    return {
        "running": state.get("running", False),
        "tick_count": state.get("tick_count", 0),
        "elapsed_s": state.get("elapsed_s", 0.0),
        "num_robots": state.get("num_robots", 0),
        "num_active_tasks": state.get("num_active_tasks", 0),
        "faults_injected": state.get("faults_injected", 0),
        "started_at": state.get("started_at"),
    }


@router.post("/start", dependencies=[Depends(require_api_key)])
async def simulation_start():
    """Start the simulation."""
    state = _get_sim_state()
    if state.get("running"):
        return {"status": "already_running", "started_at": state.get("started_at")}

    new_state = {
        "running": True,
        "tick_count": 0,
        "elapsed_s": 0.0,
        "num_robots": 0,
        "num_active_tasks": 0,
        "faults_injected": 0,
        "started_at": time.time(),
    }
    _set_sim_state(new_state)

    db = _get_db()
    if db is not None:
        try:
            robots = await db["robots"].count_documents({})
            tasks = await db["tasks"].count_documents({"status": {"$in": ["pending", "assigned", "in_progress"]}})
            new_state["num_robots"] = robots
            new_state["num_active_tasks"] = tasks
            _set_sim_state(new_state)
        except Exception:
            pass

    return {"status": "started", "started_at": new_state["started_at"]}


@router.post("/stop", dependencies=[Depends(require_api_key)])
async def simulation_stop():
    """Stop the simulation."""
    state = _get_sim_state()
    if not state.get("running"):
        return {"status": "already_stopped"}

    state["running"] = False
    _set_sim_state(state)
    return {"status": "stopped", "elapsed_s": state.get("elapsed_s", 0.0)}


@router.post("/inject-fault", dependencies=[Depends(require_api_key)])
async def inject_fault(fault: FaultInjection):
    """Inject a fault into the simulation for testing resilience."""
    state = _get_sim_state()
    db = _get_db()

    fault_doc = {
        "fault_type": fault.fault_type,
        "robot_id": fault.robot_id,
        "duration_s": fault.duration_s,
        "parameters": fault.parameters,
        "injected_at": time.time(),
        "status": "active",
    }

    if db is not None:
        try:
            await db["faults"].insert_one(fault_doc.copy())
        except Exception:
            pass

    state["faults_injected"] = state.get("faults_injected", 0) + 1
    _set_sim_state(state)

    fault_doc.pop("_id", None)
    return {"status": "fault_injected", "fault": fault_doc}

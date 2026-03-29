"""
Robot endpoints.
GET /api/robots — list all robots
GET /api/robots/{id} — single robot detail
POST /api/robots/{id}/command — send command to robot
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.auth import require_api_key

router = APIRouter(prefix="/api/robots", tags=["robots"])


def _get_db():
    from app.main import app_state
    return app_state.get("mongo_db")


class RobotCommand(BaseModel):
    action: str
    target_node: Optional[str] = None
    parameters: dict[str, str | int | float | bool] = {}


@router.get("")
async def list_robots():
    """List all robots from MongoDB."""
    db = _get_db()
    if db is None:
        return []

    try:
        robots = await db["robots"].find({}, {"_id": 0}).to_list(length=1000)
        return robots
    except Exception:
        return []


@router.get("/{robot_id}")
async def get_robot(robot_id: str):
    """Get a single robot by ID."""
    db = _get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        robot = await db["robots"].find_one({"robot_id": robot_id}, {"_id": 0})
        if robot is None:
            raise HTTPException(status_code=404, detail=f"Robot {robot_id} not found")
        return robot
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Database error")


@router.post("/{robot_id}/command", dependencies=[Depends(require_api_key)])
async def send_command(robot_id: str, cmd: RobotCommand):
    """Send a command to a specific robot. Writes to MongoDB command queue."""
    db = _get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        # Verify robot exists
        robot = await db["robots"].find_one({"robot_id": robot_id})
        if robot is None:
            raise HTTPException(status_code=404, detail=f"Robot {robot_id} not found")

        import time
        command_doc = {
            "robot_id": robot_id,
            "action": cmd.action,
            "target_node": cmd.target_node,
            "parameters": cmd.parameters,
            "timestamp": time.time(),
            "status": "pending",
        }
        result = await db["robot_commands"].insert_one(command_doc)
        return {
            "command_id": str(result.inserted_id),
            "robot_id": robot_id,
            "action": cmd.action,
            "status": "pending",
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Database error")

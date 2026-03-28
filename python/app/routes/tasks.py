"""
Task endpoints.
GET /api/tasks — list all tasks
POST /api/tasks — create a new task
GET /api/tasks/{id} — single task detail
DELETE /api/tasks/{id} — delete/cancel a task
POST /api/tasks/{id}/cancel — cancel a running task
"""

import time
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _get_db():
    from app.main import app_state
    return app_state.get("mongo_db")


class TaskCreate(BaseModel):
    task_type: str = "pick_and_drop"
    source_node: str
    destination_node: str
    priority: int = 0
    payload_kg: float = 0.0


@router.get("")
async def list_tasks():
    """List all tasks."""
    db = _get_db()
    if db is None:
        return []

    try:
        tasks = await db["tasks"].find({}, {"_id": 0}).to_list(length=10000)
        return tasks
    except Exception:
        return []


@router.post("")
async def create_task(task: TaskCreate):
    """Create a new task."""
    db = _get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        task_doc = {
            "task_id": str(uuid.uuid4()),
            "task_type": task.task_type,
            "status": "pending",
            "assigned_robot_id": None,
            "source_node": task.source_node,
            "destination_node": task.destination_node,
            "priority": task.priority,
            "created_at": time.time(),
            "assigned_at": None,
            "started_at": None,
            "completed_at": None,
            "payload_kg": task.payload_kg,
            "error_message": None,
        }
        await db["tasks"].insert_one(task_doc)
        # Return without _id
        task_doc.pop("_id", None)
        return task_doc
    except Exception:
        raise HTTPException(status_code=503, detail="Database error")


@router.get("/{task_id}")
async def get_task(task_id: str):
    """Get a single task by ID."""
    db = _get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        task = await db["tasks"].find_one({"task_id": task_id}, {"_id": 0})
        if task is None:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        return task
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Database error")


@router.delete("/{task_id}")
async def delete_task(task_id: str):
    """Delete a task (mark as cancelled if in progress)."""
    db = _get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        result = await db["tasks"].find_one_and_update(
            {"task_id": task_id},
            {"$set": {"status": "cancelled", "completed_at": time.time()}},
        )
        if result is None:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        return {"task_id": task_id, "status": "cancelled"}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Database error")


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str):
    """Cancel a running task."""
    db = _get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        task = await db["tasks"].find_one({"task_id": task_id})
        if task is None:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        if task.get("status") in ("completed", "cancelled"):
            raise HTTPException(
                status_code=400,
                detail=f"Task {task_id} already {task.get('status')}",
            )

        await db["tasks"].update_one(
            {"task_id": task_id},
            {"$set": {"status": "cancelled", "completed_at": time.time(), "error_message": "Cancelled by user"}},
        )
        return {"task_id": task_id, "status": "cancelled"}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Database error")

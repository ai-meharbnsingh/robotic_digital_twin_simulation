"""
Stats endpoint.
GET /api/stats/throughput — throughput statistics over time
"""

import time

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/stats", tags=["stats"])


def _get_db():
    from app.main import app_state
    return app_state.get("mongo_db")


@router.get("/throughput")
async def throughput_stats(
    window_s: int = Query(default=3600, ge=60, le=86400, description="Time window in seconds"),
):
    """
    Compute throughput stats: tasks completed within the given time window.
    """
    db = _get_db()
    if db is None:
        return _empty_throughput()

    try:
        cutoff = time.time() - window_s
        completed = await db["tasks"].find(
            {"status": "completed", "completed_at": {"$gte": cutoff}},
            {"_id": 0},
        ).to_list(length=50000)

        total = len(completed)
        tasks_per_hour = total / (window_s / 3600) if window_s > 0 else 0.0

        # Breakdown by task type
        by_type: dict[str, int] = {}
        for t in completed:
            tt = t.get("task_type", "unknown")
            by_type[tt] = by_type.get(tt, 0) + 1

        return {
            "window_s": window_s,
            "tasks_completed": total,
            "tasks_per_hour": round(tasks_per_hour, 1),
            "by_type": by_type,
        }
    except Exception:
        return _empty_throughput()


def _empty_throughput() -> dict:
    return {
        "window_s": 3600,
        "tasks_completed": 0,
        "tasks_per_hour": 0.0,
        "by_type": {},
    }

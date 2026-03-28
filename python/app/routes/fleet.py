"""
Fleet status endpoint.
GET /api/fleet/status — aggregate fleet overview from MongoDB.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/fleet", tags=["fleet"])


def _get_db():
    """Get MongoDB database from app state. Returns None if unavailable."""
    from app.main import app_state
    return app_state.get("mongo_db")


@router.get("/status")
async def fleet_status():
    """
    Aggregate fleet status: total robots, how many in each state,
    active tasks, completed tasks, fleet utilisation %.
    """
    db = _get_db()
    if db is None:
        return _empty_fleet_status()

    try:
        robots_coll = db["robots"]
        tasks_coll = db["tasks"]

        robots = await robots_coll.find({}).to_list(length=1000)
        tasks = await tasks_coll.find({}).to_list(length=10000)

        total_robots = len(robots)
        status_counts = {}
        for r in robots:
            st = r.get("status", "idle")
            status_counts[st] = status_counts.get(st, 0) + 1

        active_tasks = sum(1 for t in tasks if t.get("status") in ("pending", "assigned", "in_progress"))
        completed_tasks = sum(1 for t in tasks if t.get("status") == "completed")
        failed_tasks = sum(1 for t in tasks if t.get("status") == "failed")

        busy = status_counts.get("moving", 0) + status_counts.get("loading", 0) + status_counts.get("unloading", 0)
        utilisation = (busy / total_robots * 100) if total_robots > 0 else 0.0

        return {
            "total_robots": total_robots,
            "status_counts": status_counts,
            "active_tasks": active_tasks,
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
            "utilisation_pct": round(utilisation, 1),
        }
    except Exception:
        return _empty_fleet_status()


def _empty_fleet_status() -> dict:
    return {
        "total_robots": 0,
        "status_counts": {},
        "active_tasks": 0,
        "completed_tasks": 0,
        "failed_tasks": 0,
        "utilisation_pct": 0.0,
    }

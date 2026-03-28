"""
Telemetry endpoint.
GET /api/telemetry/{id} — recent telemetry for a specific robot
"""

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])


def _get_db():
    from app.main import app_state
    return app_state.get("mongo_db")


@router.get("/{robot_id}")
async def get_telemetry(
    robot_id: str,
    limit: int = Query(default=100, ge=1, le=10000, description="Max points to return"),
):
    """
    Return recent telemetry for a robot.
    Reads from MongoDB telemetry collection (written by InfluxWriter mirror).
    """
    db = _get_db()
    if db is None:
        return {"robot_id": robot_id, "points": []}

    try:
        points = (
            await db["telemetry"]
            .find({"robot_id": robot_id}, {"_id": 0})
            .sort("timestamp", -1)
            .limit(limit)
            .to_list(length=limit)
        )
        return {"robot_id": robot_id, "points": points}
    except Exception:
        return {"robot_id": robot_id, "points": []}

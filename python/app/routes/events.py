"""
Events endpoint.
GET /api/events — list system events from MongoDB
"""

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/events", tags=["events"])


def _get_db():
    from app.main import app_state
    return app_state.get("mongo_db")


@router.get("")
async def list_events(
    limit: int = Query(default=100, ge=1, le=10000),
    severity: str = Query(default=None, description="Filter by severity"),
    robot_id: str = Query(default=None, description="Filter by robot"),
):
    """List system events, newest first."""
    db = _get_db()
    if db is None:
        return []

    try:
        query: dict = {}
        if severity:
            query["severity"] = severity
        if robot_id:
            query["robot_id"] = robot_id

        events = (
            await db["events"]
            .find(query, {"_id": 0})
            .sort("timestamp", -1)
            .limit(limit)
            .to_list(length=limit)
        )
        return events
    except Exception:
        return []

"""
Reservations endpoint.
GET /api/reservations/active — list active node reservations
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/reservations", tags=["reservations"])


def _get_db():
    from app.main import app_state
    return app_state.get("mongo_db")


@router.get("/active")
async def active_reservations():
    """
    List active node reservations from the fleet manager.
    Each reservation locks a node for a specific robot to prevent collisions.
    """
    db = _get_db()
    if db is None:
        return []

    try:
        reservations = await db["reservations"].find(
            {"status": "active"},
            {"_id": 0},
        ).to_list(length=5000)
        return reservations
    except Exception:
        return []

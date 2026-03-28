"""
WCS (Warehouse Control System) endpoints.
GET /api/wcs/conveyors — conveyor belt status
GET /api/wcs/lanes — lane status
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/wcs", tags=["wcs"])


def _get_db():
    from app.main import app_state
    return app_state.get("mongo_db")


@router.get("/conveyors")
async def list_conveyors():
    """List all conveyor belts and their current status."""
    db = _get_db()
    if db is None:
        return []

    try:
        conveyors = await db["conveyors"].find({}, {"_id": 0}).to_list(length=200)
        return conveyors
    except Exception:
        return []


@router.get("/lanes")
async def list_lanes():
    """List all warehouse lanes and their occupancy."""
    db = _get_db()
    if db is None:
        return []

    try:
        lanes = await db["lanes"].find({}, {"_id": 0}).to_list(length=500)
        return lanes
    except Exception:
        return []

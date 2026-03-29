"""
io-gita endpoints.
GET /api/iogita/status — io-gita intelligence layer status
GET /api/iogita/zones — zone identification results
POST /api/iogita/cold-start/{id} — trigger cold start recovery for a robot
"""

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_api_key

router = APIRouter(prefix="/api/iogita", tags=["iogita"])


def _get_db():
    from app.main import app_state
    return app_state.get("mongo_db")


def _get_iogita():
    """Get the io-gita zone identifier instance."""
    from app.main import app_state
    return app_state.get("iogita_zone_identifier")


def _get_cold_start():
    """Get the cold start recovery instance."""
    from app.main import app_state
    return app_state.get("iogita_cold_start")


@router.get("/status")
async def iogita_status():
    """Return io-gita intelligence layer status."""
    zone_id = _get_iogita()
    cold_start = _get_cold_start()

    return {
        "engine": "io-gita",
        "zone_identifier_loaded": zone_id is not None,
        "cold_start_loaded": cold_start is not None,
        "backend": getattr(zone_id, "backend", "none") if zone_id else "none",
        "num_zones": getattr(zone_id, "num_zones", 0) if zone_id else 0,
    }


@router.get("/zones")
async def iogita_zones():
    """Return zone identification results for each robot."""
    db = _get_db()
    zone_id = _get_iogita()

    if zone_id is None:
        return {"zones": [], "engine": "none"}

    try:
        robots = []
        if db is not None:
            robots = await db["robots"].find({}, {"_id": 0}).to_list(length=1000)

        zone_results = []
        for robot in robots:
            pose = robot.get("pose", {})
            features = [pose.get("x", 0.0), pose.get("y", 0.0)]
            zone = zone_id.identify(features)
            zone_results.append({
                "robot_id": robot.get("robot_id", ""),
                "zone": zone,
                "pose": pose,
            })

        return {"zones": zone_results, "engine": zone_id.backend}
    except Exception:
        return {"zones": [], "engine": "fallback"}


@router.post("/cold-start/{robot_id}", dependencies=[Depends(require_api_key)])
async def cold_start_recovery(robot_id: str):
    """Trigger cold start recovery for a robot."""
    db = _get_db()
    cold_start = _get_cold_start()

    if cold_start is None:
        raise HTTPException(status_code=503, detail="Cold start engine not available")

    try:
        robot = None
        if db is not None:
            robot = await db["robots"].find_one({"robot_id": robot_id}, {"_id": 0})

        if robot is None:
            # Generate recovery hints without prior state
            hints = cold_start.generate_recovery_hints(robot_id, {})
        else:
            hints = cold_start.generate_recovery_hints(robot_id, robot)

        return {
            "robot_id": robot_id,
            "recovery_hints": hints,
            "cold_start_engine": "io-gita",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Cold start recovery failed")

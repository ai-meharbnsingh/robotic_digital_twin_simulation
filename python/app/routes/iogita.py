"""
io-gita v4 endpoints — hierarchical zone-first identification.

GET  /api/iogita/status              — intelligence layer status
GET  /api/iogita/zones               — zone identification per robot (from MongoDB poses)
POST /api/iogita/cold-start/{id}     — trigger cold start recovery for a robot
"""

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_api_key

router = APIRouter(prefix="/api/iogita", tags=["iogita"])


def _get_db():
    from app.main import app_state
    return app_state.get("mongo_db")


def _get_iogita():
    """Get the io-gita v4 zone identifier instance."""
    from app.main import app_state
    return app_state.get("iogita_zone_identifier")


def _get_cold_start():
    """Get the cold start state manager instance."""
    from app.main import app_state
    return app_state.get("iogita_cold_start")


def _get_engine():
    """Get the io-gita KDTree engine instance (for LiDAR-based recovery)."""
    from app.main import app_state
    return app_state.get("iogita_engine")


@router.get("/status")
async def iogita_status():
    """Return io-gita intelligence layer status."""
    zone_id = _get_iogita()
    cold_start = _get_cold_start()
    engine = _get_engine()

    num_zones = 0
    num_nodes = 0
    if zone_id is not None:
        num_zones = len(zone_id.zones)
        num_nodes = len(zone_id.nodes_by_name)

    backend = "kdtree" if engine is not None else "hierarchical_hopfield_d10000"
    version = "5.0" if engine is not None else "4.0"

    return {
        "engine": f"io-gita-v{version}",
        "version": version,
        "zone_identifier_loaded": zone_id is not None,
        "cold_start_loaded": cold_start is not None,
        "backend": backend,
        "num_zones": num_zones,
        "num_nodes": num_nodes,
        "strategy": "KDTree nearest-neighbor (0.008ms, 525x faster than Hopfield ODE)"
                    if engine else "zone-first (12 geometry features) → node-second",
    }


@router.get("/zones")
async def iogita_zones():
    """Return zone identification results for each robot from MongoDB poses."""
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

        return {"zones": zone_results, "engine": "io-gita-v4-hierarchical"}
    except Exception:
        return {"zones": [], "engine": "fallback"}


@router.post("/cold-start/{robot_id}", dependencies=[Depends(require_api_key)])
async def cold_start_recovery(robot_id: str):
    """Trigger cold start recovery for a robot (hint-based, no LiDAR)."""
    db = _get_db()
    cold_start = _get_cold_start()

    if cold_start is None:
        raise HTTPException(status_code=503, detail="Cold start engine not available")

    try:
        robot = None
        if db is not None:
            robot = await db["robots"].find_one({"robot_id": robot_id}, {"_id": 0})

        if robot is None:
            hints = cold_start.generate_recovery_hints(robot_id, {})
        else:
            hints = cold_start.generate_recovery_hints(robot_id, robot)

        engine = _get_engine()
        return {
            "robot_id": robot_id,
            "recovery_hints": hints,
            "cold_start_engine": "io-gita-v5-kdtree" if engine else "io-gita-v4",
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Cold start recovery temporarily unavailable")


@router.post("/recover/{robot_id}", dependencies=[Depends(require_api_key)])
async def lidar_recovery(robot_id: str, body: dict):
    """Full LiDAR-based cold start recovery using KDTree engine.

    Body:
        scan: list[float]       — 360-ray LiDAR scan
        last_known_node: str    — last confirmed node (from FMS)
        heading_deg: float      — current heading in degrees (from IMU)

    Returns:
        zone, node, confidence, recovery_time_ms, safety_ok
    """
    engine = _get_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="KDTree engine not available")

    scan = body.get("scan")
    last_node = body.get("last_known_node", "")
    heading = body.get("heading_deg", 0.0)

    if not scan or not isinstance(scan, list):
        raise HTTPException(status_code=400, detail="'scan' must be a list of 360 floats")

    import numpy as np
    scan_arr = np.array(scan, dtype=np.float64)

    result = engine.full_recovery(scan_arr, last_node, heading)

    return {
        "robot_id": robot_id,
        "zone": result["zone"],
        "node": result["node"],
        "zone_confidence": result["zone_confidence"],
        "node_confidence": result["node_confidence"],
        "method": result["method"],
        "recovery_time_ms": result["recovery_time_ms"],
        "safety_ok": result["safety_ok"],
        "engine": "io-gita-v5-kdtree",
    }

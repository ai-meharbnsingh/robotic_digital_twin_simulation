"""
Analytics endpoints.
GET /api/analytics/fleet — fleet-wide analytics
GET /api/analytics/predictions — SG prediction results
GET /api/analytics/ab-comparison — A/B comparison of strategies
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _get_db():
    from app.main import app_state
    return app_state.get("mongo_db")


def _get_bottleneck_predictor():
    from app.main import app_state
    return app_state.get("bottleneck_predictor")


@router.get("/fleet")
async def fleet_analytics():
    """Fleet-wide analytics: throughput, avg task time, battery stats."""
    db = _get_db()
    if db is None:
        return _empty_analytics()

    try:
        tasks = await db["tasks"].find({}, {"_id": 0}).to_list(length=50000)
        robots = await db["robots"].find({}, {"_id": 0}).to_list(length=1000)

        completed = [t for t in tasks if t.get("status") == "completed"]
        avg_task_time = 0.0
        if completed:
            times = []
            for t in completed:
                started = t.get("started_at")
                done = t.get("completed_at")
                if started and done:
                    times.append(done - started)
            if times:
                avg_task_time = sum(times) / len(times)

        battery_levels = [
            r.get("battery", {}).get("charge_pct", 0)
            for r in robots
            if isinstance(r.get("battery"), dict)
        ]
        avg_battery = sum(battery_levels) / len(battery_levels) if battery_levels else 0.0

        return {
            "total_tasks": len(tasks),
            "completed_tasks": len(completed),
            "failed_tasks": sum(1 for t in tasks if t.get("status") == "failed"),
            "avg_task_time_s": round(avg_task_time, 2),
            "total_robots": len(robots),
            "avg_battery_pct": round(avg_battery, 1),
            "throughput_tasks_per_hour": round(len(completed) / max(1, avg_task_time / 3600), 1) if avg_task_time > 0 else 0.0,
        }
    except Exception:
        return _empty_analytics()


@router.get("/predictions")
async def sg_predictions():
    """Return SG-engine bottleneck predictions."""
    predictor = _get_bottleneck_predictor()
    db = _get_db()

    if predictor is None:
        return {"predictions": [], "engine": "none"}

    try:
        robots = []
        if db is not None:
            robots = await db["robots"].find({}, {"_id": 0}).to_list(length=1000)

        # Encode fleet state and predict
        predictions = predictor.predict(robots)
        return {
            "predictions": predictions,
            "engine": "sg_prediction",
            "num_robots_analyzed": len(robots),
        }
    except Exception:
        return {"predictions": [], "engine": "error"}


@router.get("/ab-comparison")
async def ab_comparison():
    """A/B comparison of task allocation strategies."""
    db = _get_db()
    if db is None:
        return {"comparisons": [], "strategies": []}

    try:
        comparisons = await db["ab_comparisons"].find({}, {"_id": 0}).to_list(length=100)
        return {
            "comparisons": comparisons,
            "strategies": ["fifo", "nearest", "priority_weighted"],
        }
    except Exception:
        return {"comparisons": [], "strategies": ["fifo", "nearest", "priority_weighted"]}


def _empty_analytics() -> dict:
    return {
        "total_tasks": 0,
        "completed_tasks": 0,
        "failed_tasks": 0,
        "avg_task_time_s": 0.0,
        "total_robots": 0,
        "avg_battery_pct": 0.0,
        "throughput_tasks_per_hour": 0.0,
    }

"""
WES (Warehouse Execution System) endpoints.
POST /api/wes/inject-orders — inject orders into the system
GET /api/wes/kpi — WES key performance indicators
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/wes", tags=["wes"])


def _get_db():
    from app.main import app_state
    return app_state.get("mongo_db")


def _get_wes():
    from app.main import app_state
    return (
        app_state.get("wes_order_generator"),
        app_state.get("wes_task_generator"),
        app_state.get("wes_kpi_tracker"),
    )


class OrderInjection(BaseModel):
    num_orders: int = 1
    order_type: Optional[str] = "pick_and_drop"


@router.post("/inject-orders")
async def inject_orders(injection: OrderInjection):
    """Inject orders into the WES order generator."""
    db = _get_db()
    order_gen, task_gen, _ = _get_wes()

    if order_gen is None:
        return {"injected": 0, "error": "WES order generator not available"}

    try:
        orders = order_gen.generate_batch(injection.num_orders)

        # Generate tasks from orders if TaskGenerator available
        tasks = []
        if task_gen is not None:
            tasks = task_gen.from_orders(orders)

        if db is not None:
            for order in orders:
                await db["orders"].insert_one(order.copy())
            for task in tasks:
                await db["tasks"].insert_one(task.copy())

        # Strip _id before returning
        for order in orders:
            order.pop("_id", None)
        for task in tasks:
            task.pop("_id", None)

        return {"injected": len(orders), "orders": orders, "tasks_created": len(tasks)}
    except Exception:
        return {"injected": 0, "error": "Order injection failed"}


@router.get("/kpi")
async def wes_kpi():
    """Return WES KPI metrics."""
    _, _, kpi_tracker = _get_wes()
    db = _get_db()

    if kpi_tracker is None:
        return _empty_kpi()

    try:
        tasks = []
        orders = []
        if db is not None:
            tasks = await db["tasks"].find({}, {"_id": 0}).to_list(length=50000)
            orders = await db["orders"].find({}, {"_id": 0}).to_list(length=50000)

        kpi = kpi_tracker.compute(orders, tasks)
        return kpi
    except Exception:
        return _empty_kpi()


def _empty_kpi() -> dict:
    return {
        "orders_per_hour": 0.0,
        "pick_accuracy_pct": 100.0,
        "throughput_items_per_hour": 0.0,
        "avg_order_cycle_time_s": 0.0,
        "pending_orders": 0,
        "completed_orders": 0,
    }

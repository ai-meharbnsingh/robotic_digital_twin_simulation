"""
Order import endpoint.
POST /api/wes/orders/import — upload CSV file of orders, validate, create tasks.
"""

import csv
import io
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException

from app.auth import require_api_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/wes", tags=["wes"])

# Required CSV columns
REQUIRED_COLUMNS = {"source_node", "destination_node"}
OPTIONAL_COLUMNS = {"priority", "payload_kg", "order_type", "order_id"}


def _get_db():
    from app.main import app_state
    return app_state.get("mongo_db")


def _get_wes():
    from app.main import app_state
    return app_state.get("wes_task_generator")


def _get_valid_nodes() -> set[str]:
    """Get set of valid node names from loaded warehouse config."""
    from app.main import app_state
    config = app_state.get("warehouse_config")
    if config is None:
        return set()
    return {n["name"] for n in config.get("nodes", [])}


def _parse_and_validate(
    content: str, valid_nodes: set[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Parse CSV content and validate each row.

    Returns:
        (valid_orders, errors) — valid orders ready for TaskGenerator,
        errors with row number and message.
    """
    reader = csv.DictReader(io.StringIO(content))

    if reader.fieldnames is None:
        raise ValueError("CSV file is empty or has no header row")

    columns = set(reader.fieldnames)
    missing = REQUIRED_COLUMNS - columns
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

    orders = []
    errors = []

    for row_num, row in enumerate(reader, start=2):  # row 1 = header
        source = row.get("source_node", "").strip()
        dest = row.get("destination_node", "").strip()

        # Validate required fields are non-empty
        if not source:
            errors.append({"row": row_num, "error": "source_node is empty"})
            continue
        if not dest:
            errors.append({"row": row_num, "error": "destination_node is empty"})
            continue

        # Validate nodes exist in warehouse
        if valid_nodes and source not in valid_nodes:
            errors.append({"row": row_num, "error": f"source_node '{source}' not in warehouse"})
            continue
        if valid_nodes and dest not in valid_nodes:
            errors.append({"row": row_num, "error": f"destination_node '{dest}' not in warehouse"})
            continue

        # Parse optional fields
        try:
            priority = int(row.get("priority", 0) or 0)
        except ValueError:
            errors.append({"row": row_num, "error": f"priority '{row.get('priority')}' is not an integer"})
            continue

        try:
            payload = float(row.get("payload_kg", 0.0) or 0.0)
        except ValueError:
            errors.append({"row": row_num, "error": f"payload_kg '{row.get('payload_kg')}' is not a number"})
            continue

        order_type = row.get("order_type", "pick_and_drop").strip() or "pick_and_drop"
        order_id = row.get("order_id", "").strip() or str(uuid.uuid4())

        orders.append({
            "order_id": order_id,
            "source_node": source,
            "destination_node": dest,
            "priority": priority,
            "payload_kg": payload,
            "order_type": order_type,
            "created_at": time.time(),
            "status": "pending",
        })

    return orders, errors


@router.post("/orders/import", dependencies=[Depends(require_api_key)])
async def import_orders(file: UploadFile = File(...)):
    """
    Import orders from a CSV file.

    CSV must have columns: source_node, destination_node
    Optional columns: priority, payload_kg, order_type, order_id

    Returns imported order count, created task count, and any validation errors.
    """
    # Validate file type
    if file.content_type and file.content_type not in (
        "text/csv", "text/plain", "application/vnd.ms-excel",
        "application/octet-stream",
    ):
        raise HTTPException(status_code=400, detail=f"Expected CSV file, got {file.content_type}")

    # Read file content
    try:
        raw = await file.read()
        content = raw.decode("utf-8-sig")  # Handle BOM from Excel
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File is not valid UTF-8 text")

    if not content.strip():
        raise HTTPException(status_code=400, detail="CSV file is empty")

    # Parse and validate
    valid_nodes = _get_valid_nodes()
    try:
        orders, errors = _parse_and_validate(content, valid_nodes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not orders:
        return {
            "imported": 0,
            "tasks_created": 0,
            "errors": errors,
            "message": "No valid orders found in CSV",
        }

    # Generate tasks
    task_gen = _get_wes()
    tasks = []
    if task_gen is not None:
        tasks = task_gen.from_orders(orders)

    # Store in MongoDB
    db = _get_db()
    if db is not None:
        try:
            for order in orders:
                await db["orders"].insert_one(order.copy())
            for task in tasks:
                await db["tasks"].insert_one(task.copy())
        except Exception:
            logger.exception("Failed to store imported orders in MongoDB")

    # Strip _id before returning
    for order in orders:
        order.pop("_id", None)
    for task in tasks:
        task.pop("_id", None)

    return {
        "imported": len(orders),
        "tasks_created": len(tasks),
        "errors": errors,
        "orders": orders,
    }

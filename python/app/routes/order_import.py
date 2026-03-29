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

# Allowed order_type values (must match TaskGenerator branches)
ALLOWED_ORDER_TYPES = {"pick_and_drop", "separate"}

# Safety limits
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_ROWS = 10_000


def _get_db():
    from app.main import app_state
    return app_state.get("mongo_db")


def _get_wes():
    from app.main import app_state
    return app_state.get("wes_task_generator")


def _get_valid_nodes() -> tuple[set[str], bool]:
    """Get set of valid node names from loaded warehouse config.

    Returns:
        (valid_nodes, config_loaded) — the node set and whether a warehouse
        config was loaded at all.  When config_loaded is True but valid_nodes
        is empty, that means the config has zero nodes which is an error.
    """
    from app.main import app_state
    config = app_state.get("warehouse_config")
    if config is None:
        return set(), False
    return {n["name"] for n in config.get("nodes", [])}, True


def _parse_and_validate(
    content: str, valid_nodes: set[str], config_loaded: bool
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

    # Finding #3: If warehouse config was loaded but has zero nodes, that is
    # an error — we cannot validate node references at all.
    if config_loaded and not valid_nodes:
        raise ValueError("Warehouse config loaded but contains no nodes — cannot validate orders")

    orders = []
    errors = []

    for row_num, row in enumerate(reader, start=2):  # row 1 = header
        if row_num > MAX_ROWS + 1:
            errors.append({"row": row_num, "error": f"Exceeded {MAX_ROWS} row limit"})
            break
        source = row.get("source_node", "").strip()
        dest = row.get("destination_node", "").strip()

        # Validate required fields are non-empty
        if not source:
            errors.append({"row": row_num, "error": "source_node is empty"})
            continue
        if not dest:
            errors.append({"row": row_num, "error": "destination_node is empty"})
            continue

        # Finding #4: source and destination must differ
        if source == dest:
            errors.append({"row": row_num, "error": "source_node and destination_node must differ"})
            continue

        # Validate nodes exist in warehouse (only when config was loaded)
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

        # Finding #4: priority must be 0..100
        if priority < 0 or priority > 100:
            errors.append({"row": row_num, "error": f"priority {priority} out of range 0-100"})
            continue

        try:
            payload = float(row.get("payload_kg", 0.0) or 0.0)
        except ValueError:
            errors.append({"row": row_num, "error": f"payload_kg '{row.get('payload_kg')}' is not a number"})
            continue

        # Finding #4: payload_kg must be non-negative
        if payload < 0:
            errors.append({"row": row_num, "error": f"payload_kg {payload} must be >= 0"})
            continue

        order_type = row.get("order_type", "pick_and_drop").strip() or "pick_and_drop"

        # Finding #4: order_type must be in allowed set
        if order_type not in ALLOWED_ORDER_TYPES:
            errors.append({
                "row": row_num,
                "error": f"order_type '{order_type}' not in {sorted(ALLOWED_ORDER_TYPES)}",
            })
            continue

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

    # Read file content with size limit
    try:
        raw = await file.read()
        if len(raw) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail=f"File exceeds {MAX_FILE_SIZE // (1024*1024)}MB limit")
        content = raw.decode("utf-8-sig")  # Handle BOM from Excel
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File is not valid UTF-8 text")

    if not content.strip():
        raise HTTPException(status_code=400, detail="CSV file is empty")

    # Parse and validate
    valid_nodes, config_loaded = _get_valid_nodes()
    try:
        orders, errors = _parse_and_validate(content, valid_nodes, config_loaded)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not orders:
        return {
            "imported": 0,
            "tasks_created": 0,
            "errors": errors,
            "order_ids": [],
            "persisted": False,
            "message": "No valid orders found in CSV",
        }

    # Finding #6: Wrap task generation in try/except
    task_gen = _get_wes()
    tasks = []
    if task_gen is not None:
        try:
            tasks = task_gen.from_orders(orders)
        except Exception:
            logger.exception("TaskGenerator.from_orders() failed")
            errors.append({"row": 0, "error": "Task generation failed"})

    # Finding #1 & #2: Track persistence success; use insert_many for atomicity
    persisted = False
    db = _get_db()
    if db is not None:
        try:
            if orders:
                await db["orders"].insert_many([o.copy() for o in orders])
            if tasks:
                await db["tasks"].insert_many([t.copy() for t in tasks])
            persisted = True
        except Exception:
            logger.exception("Failed to store imported orders in MongoDB")

    # Finding #5: Only return summary — no full order/task bodies
    order_ids = [o["order_id"] for o in orders]

    return {
        "imported": len(orders),
        "tasks_created": len(tasks),
        "errors": errors,
        "order_ids": order_ids,
        "persisted": persisted,
    }

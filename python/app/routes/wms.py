"""
WMS/ERP REST endpoints.

GET  /api/wms/status              — connector status (SAP/Odoo/Webhook, connected)
POST /api/wms/sync                — trigger order sync from WMS
GET  /api/wms/orders              — list orders pulled from WMS
POST /api/wms/webhook/receive     — receive order via webhook
GET  /api/wms/dlq                 — list dead letter queue
POST /api/wms/dlq/{id}/retry      — retry dead letter

Phase 12: WMS/SAP Connector Backend.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.auth import require_api_key

logger = logging.getLogger(__name__)

MAX_SYNC_ORDERS = 1_000
MAX_WEBHOOK_ITEMS = 500
MAX_ORDER_RETENTION = 10_000

router = APIRouter(prefix="/api/wms", tags=["wms"])


def _get_wms_connector():
    """Get active WMS connector from app_state."""
    from app.main import app_state
    return app_state.get("wms_connector")


def _get_dlq():
    """Get DLQ from app_state."""
    from app.main import app_state
    return app_state.get("wms_dlq")


def _get_order_store():
    """Get synced orders list from app_state."""
    from app.main import app_state
    return app_state.get("wms_orders", [])


# ── Request models ─────────────────────────────────────────


class WebhookItem(BaseModel):
    """A single line item in a webhook order."""
    sku: str = Field(description="SKU identifier", min_length=1, max_length=128)
    quantity: int = Field(description="Quantity ordered", gt=0)
    location: str = Field(default="", description="Preferred pick location", max_length=128)


class WebhookPayload(BaseModel):
    """Request body for POST /api/wms/webhook/receive."""
    id: str = Field(default="", description="External order ID", max_length=256)
    items: list[WebhookItem] = Field(default_factory=list, description="Order line items")
    priority: int = Field(default=3, ge=1, le=5, description="Priority 1-5")
    customer: str = Field(default="", description="Customer name", max_length=512)

    @field_validator("items")
    @classmethod
    def items_not_too_large(cls, v: list[WebhookItem]) -> list[WebhookItem]:
        if len(v) > MAX_WEBHOOK_ITEMS:
            raise ValueError(f"Too many items ({len(v)}). Max is {MAX_WEBHOOK_ITEMS}.")
        return v


# ── Endpoints ──────────────────────────────────────────────


@router.get("/status")
async def get_wms_status():
    """
    Get WMS connector status.

    Returns connector type, connection state, and DLQ summary.
    """
    connector = _get_wms_connector()
    dlq = _get_dlq()

    if connector is None:
        return {
            "connector_initialized": False,
            "type": None,
            "connected": False,
            "dlq": {"total": 0, "dead": 0, "retrying": 0, "rabbitmq_connected": False},
        }

    status = connector.get_status()
    status["connector_initialized"] = True
    status["dlq"] = dlq.get_status() if dlq else {"total": 0, "dead": 0, "retrying": 0, "rabbitmq_connected": False}
    return status


@router.post("/sync", dependencies=[Depends(require_api_key)])
async def sync_orders():
    """
    Trigger order sync from WMS.

    Pulls pending orders from the active connector and translates them
    to internal format via OrderTranslator.
    """
    connector = _get_wms_connector()
    if connector is None:
        raise HTTPException(status_code=503, detail="WMS connector not initialized")

    dlq = _get_dlq()

    try:
        raw_orders = await connector.fetch_orders()
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail=f"WMS unreachable: {exc}")
    except Exception as exc:
        logger.exception("WMS sync failed")
        raise HTTPException(status_code=500, detail="Internal error during WMS sync")

    # Cap orders per sync to prevent resource exhaustion
    if len(raw_orders) > MAX_SYNC_ORDERS:
        logger.warning("Sync truncated: %d orders to %d", len(raw_orders), MAX_SYNC_ORDERS)
        raw_orders = raw_orders[:MAX_SYNC_ORDERS]

    from wms.order_translator import OrderTranslator
    from app.main import app_state

    translated = []
    errors = []
    source = connector.get_status().get("type", "webhook")

    for raw in raw_orders:
        try:
            internal = OrderTranslator.to_internal(source, raw)
            translated.append(internal)
        except Exception as exc:
            errors.append({"order": raw, "error": str(exc)})
            if dlq:
                await dlq.enqueue(raw, str(exc))

    # Store synced orders (capped at MAX_ORDER_RETENTION to prevent unbounded growth)
    order_store = app_state.setdefault("wms_orders", [])
    order_store.extend(translated)
    if len(order_store) > MAX_ORDER_RETENTION:
        order_store[:] = order_store[-MAX_ORDER_RETENTION:]

    # Feed translated orders into WES TaskGenerator for wave/task processing
    tasks_created = 0
    task_gen = app_state.get("wes_task_generator")
    if task_gen is not None and translated:
        try:
            tasks = task_gen.from_orders(translated)
            tasks_created = len(tasks) if tasks else 0
        except Exception:
            logger.exception("WMS→WES task generation failed")

    return {
        "synced": len(translated),
        "errors": len(errors),
        "total_orders": len(order_store),
        "tasks_created": tasks_created,
    }


@router.get("/orders")
async def list_orders(offset: int = 0, limit: int = 100):
    """
    List orders pulled from WMS.

    Returns paginated orders that have been synced (translated to internal format).
    """
    limit = max(1, min(limit, 1000))
    offset = max(0, offset)
    orders = _get_order_store()
    page = orders[offset:offset + limit]
    return {"orders": page, "total": len(orders), "offset": offset, "limit": limit}


@router.post("/webhook/receive", dependencies=[Depends(require_api_key)])
async def receive_webhook(payload: WebhookPayload):
    """
    Receive order via webhook.

    Any external WMS can POST orders here. The webhook adapter stores them
    until the next sync.
    """
    connector = _get_wms_connector()
    if connector is None:
        raise HTTPException(status_code=503, detail="WMS connector not initialized")

    # Validate payload has at minimum an id or items
    if not payload.id and not payload.items:
        raise HTTPException(status_code=400, detail="Webhook payload must include 'id' or 'items'")

    try:
        result = await connector.receive_order(payload.model_dump())
        return result
    except NotImplementedError:
        connector_type = connector.get_status().get("type", "unknown")
        raise HTTPException(
            status_code=405,
            detail=f"Active connector ({connector_type}) does not support webhook receive",
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=f"Order validation error: {exc}")
    except OverflowError as exc:
        raise HTTPException(status_code=507, detail=str(exc))
    except Exception:
        logger.exception("Webhook receive failed")
        raise HTTPException(status_code=500, detail="Internal error processing webhook")


@router.get("/dlq")
async def list_dlq(limit: int = 100):
    """
    List dead letter queue entries.

    Returns failed orders with error reasons, newest first.
    """
    limit = max(1, min(limit, 1000))
    dlq = _get_dlq()
    if dlq is None:
        return {"dead_letters": [], "total": 0}

    entries = await dlq.list_dead_letters(limit=limit)
    status = dlq.get_status()
    return {
        "dead_letters": entries,
        "total": status["total"],
        "rabbitmq_connected": status["rabbitmq_connected"],
    }


@router.post("/dlq/{message_id}/retry", dependencies=[Depends(require_api_key)])
async def retry_dlq(message_id: str):
    """
    Retry a dead letter.

    Returns the order for re-processing.
    """
    dlq = _get_dlq()
    if dlq is None:
        raise HTTPException(status_code=503, detail="DLQ not initialized")

    try:
        result = await dlq.retry(message_id)
        return result
    except KeyError:
        raise HTTPException(status_code=404, detail=f"DLQ message not found: {message_id}")
    except Exception as exc:
        logger.exception("DLQ retry failed")
        raise HTTPException(status_code=500, detail="Internal error during DLQ retry")

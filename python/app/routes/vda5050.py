"""
VDA5050 REST endpoints.

GET  /api/vda5050/status           — gateway status (broker connected, AGVs online)
POST /api/vda5050/orders           — send VDA5050 order to AGV via MQTT
POST /api/vda5050/instant-actions  — send instant action (E-stop, cancel)
GET  /api/vda5050/agvs             — list connected AGVs with latest state
GET  /api/vda5050/agvs/{id}/state  — get AGV's latest VDA5050 state

Phase 8: VDA5050 Gateway Backend.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import require_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vda5050", tags=["vda5050"])

# ── Resource limits ──────────────────────────────────────
MAX_AGVS = 200
MAX_ORDER_NODES = 500


def _get_gateway():
    """Get VDA5050Gateway from app_state."""
    from app.main import app_state
    return app_state.get("vda5050_gateway")


# ── Request models ─────────────────────────────────────────


class OrderRequest(BaseModel):
    """Request body for POST /api/vda5050/orders."""
    agv_id: str = Field(..., description="Target AGV serial number")
    order: dict = Field(..., description="VDA5050 order message as JSON")


class InstantActionRequest(BaseModel):
    """Request body for POST /api/vda5050/instant-actions."""
    agv_id: str = Field(..., description="Target AGV serial number")
    action_type: str = Field(..., description="VDA5050 action type (cancelOrder, stopPause, etc.)")
    action_id: str = Field(..., description="Unique action ID")


# ── Endpoints ──────────────────────────────────────────────


@router.get("/status")
async def get_status():
    """
    Get VDA5050 gateway status.

    Returns broker connection state and count of connected AGVs.
    """
    gateway = _get_gateway()
    if gateway is None:
        return {
            "broker_connected": False,
            "agvs_online": 0,
            "agvs_total": 0,
            "gateway_initialized": False,
        }
    status = gateway.get_status()
    status["gateway_initialized"] = True
    return status


@router.post("/orders", dependencies=[Depends(require_api_key)])
async def send_order(body: OrderRequest):
    """
    Send VDA5050 order to AGV via MQTT.

    Returns 503 if MQTT broker is not connected.
    Returns 400 if order exceeds MAX_ORDER_NODES limit.
    """
    gateway = _get_gateway()
    if gateway is None:
        raise HTTPException(status_code=503, detail="VDA5050 gateway not initialized")

    # Enforce MAX_AGVS — prevent fleet size explosion
    existing_agvs = gateway.get_agv_states()
    if body.agv_id not in existing_agvs and len(existing_agvs) >= MAX_AGVS:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_AGVS} AGVs reached — cannot dispatch to new AGV '{body.agv_id}'",
        )

    from vda5050.models import VDA5050Order

    try:
        order = VDA5050Order.model_validate(body.order)
    except Exception as exc:
        logger.warning("Invalid VDA5050 order from client: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid VDA5050 order format")

    # Resource limit: cap nodes per order
    if len(order.nodes) > MAX_ORDER_NODES:
        raise HTTPException(
            status_code=400,
            detail=f"Order exceeds maximum of {MAX_ORDER_NODES} nodes",
        )

    try:
        await gateway.dispatch_order(body.agv_id, order)
    except ConnectionError:
        raise HTTPException(status_code=503, detail="MQTT broker not connected — cannot send order")
    except Exception as exc:
        logger.exception("Failed to dispatch order to %s", body.agv_id)
        raise HTTPException(status_code=500, detail="Internal error dispatching order")

    return {
        "status": "dispatched",
        "agv_id": body.agv_id,
        "order_id": order.orderId,
    }


@router.post("/instant-actions", dependencies=[Depends(require_api_key)])
async def send_instant_action(body: InstantActionRequest):
    """
    Send instant action (E-stop, cancel, pause) to AGV via MQTT.

    Returns 503 if MQTT broker is not connected.
    """
    gateway = _get_gateway()
    if gateway is None:
        raise HTTPException(status_code=503, detail="VDA5050 gateway not initialized")

    try:
        await gateway.send_instant_action(body.agv_id, body.action_type, body.action_id)
    except ConnectionError:
        raise HTTPException(
            status_code=503,
            detail="MQTT broker not connected — cannot send instant action",
        )
    except Exception as exc:
        logger.exception("Failed to send instant action to %s", body.agv_id)
        raise HTTPException(status_code=500, detail="Internal error sending instant action")

    return {
        "status": "sent",
        "agv_id": body.agv_id,
        "action_type": body.action_type,
        "action_id": body.action_id,
    }


@router.get("/agvs")
async def list_agvs():
    """
    List all connected AGVs with their latest state.

    Returns array of AGV state summaries.
    """
    gateway = _get_gateway()
    if gateway is None:
        return []

    states = gateway.get_agv_states()
    agvs = []
    for serial, state in states.items():
        agvs.append({
            "serial_number": serial,
            "last_state": state,
        })
    return agvs


@router.get("/agvs/{agv_id}/state")
async def get_agv_state(agv_id: str):
    """
    Get latest VDA5050 state for a specific AGV.

    Returns 404 if AGV not found.
    """
    gateway = _get_gateway()
    if gateway is None:
        raise HTTPException(status_code=404, detail="AGV not found")

    state = gateway.get_agv_state(agv_id)
    if state is None:
        raise HTTPException(status_code=404, detail="AGV not found or no state received")

    return {
        "serial_number": agv_id,
        "state": state,
    }

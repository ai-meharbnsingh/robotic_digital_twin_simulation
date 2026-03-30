"""
Inventory Management REST endpoints.

Phase 14: Full inventory lifecycle — SKU catalog, stock operations,
replenishment, and storage optimization.

GET  /api/inventory/skus                          — all SKUs from catalog
GET  /api/inventory/skus/{sku_id}                 — single SKU + stock locations
GET  /api/inventory/stock-levels                  — all SKU stock levels with status
GET  /api/inventory/stock/{node_name}             — stock at a specific node
POST /api/inventory/receive                       — receive inventory
POST /api/inventory/pick                          — pick inventory
POST /api/inventory/adjust                        — adjust after cycle count
POST /api/inventory/transfer                      — transfer between nodes
POST /api/inventory/cycle-count                   — perform cycle count at node
GET  /api/inventory/movements                     — recent stock movements
GET  /api/inventory/replenishment                 — pending replenishment orders
POST /api/inventory/replenishment/check           — check and generate replenishment
POST /api/inventory/replenishment/{id}/complete   — complete a replenishment order
POST /api/inventory/replenishment/{id}/cancel     — cancel a replenishment order
GET  /api/inventory/optimizer/abc                 — ABC analysis
GET  /api/inventory/optimizer/recommendations     — slotting recommendations
GET  /api/inventory/optimizer/zone-balance         — zone balance analysis
GET  /api/inventory/stats                         — combined stats

Route ordering: fixed paths BEFORE parameterized paths (Phase 13 lesson).
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.auth import require_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


def _get_inventory():
    """Get inventory components from app_state."""
    from app.main import app_state
    return {
        "manager": app_state.get("inventory_manager"),
        "replenishment": app_state.get("replenishment_engine"),
        "optimizer": app_state.get("storage_optimizer"),
    }


# ── Request Models ──────────────────────────────────────


class ReceiveRequest(BaseModel):
    sku_id: str = Field(..., min_length=1, max_length=50)
    node_name: str = Field(..., min_length=1, max_length=50)
    quantity: int = Field(..., gt=0, le=100000)


class PickRequest(BaseModel):
    sku_id: str = Field(..., min_length=1, max_length=50)
    node_name: str = Field(..., min_length=1, max_length=50)
    quantity: int = Field(..., gt=0, le=100000)


class AdjustRequest(BaseModel):
    sku_id: str = Field(..., min_length=1, max_length=50)
    node_name: str = Field(..., min_length=1, max_length=50)
    new_quantity: int = Field(..., ge=0, le=100000)
    reason: str = Field("", max_length=200)


class TransferRequest(BaseModel):
    sku_id: str = Field(..., min_length=1, max_length=50)
    from_node: str = Field(..., min_length=1, max_length=50)
    to_node: str = Field(..., min_length=1, max_length=50)
    quantity: int = Field(..., gt=0, le=100000)


class CycleCountRequest(BaseModel):
    node_name: str = Field(..., min_length=1, max_length=50)
    counts: dict[str, int] = Field(..., description="Mapping of sku_id to actual quantity")

    @field_validator("counts")
    @classmethod
    def validate_counts(cls, v: dict[str, int]) -> dict[str, int]:
        if len(v) > 500:
            raise ValueError(f"Too many items ({len(v)}). Max 500 per cycle count.")
        for sku_id, qty in v.items():
            if qty < 0:
                raise ValueError(f"Negative quantity for '{sku_id}': {qty}")
        return v


# ── SKU Endpoints (fixed paths first) ──────────────────


@router.get("/skus")
async def list_skus():
    """List all SKUs from catalog."""
    inv = _get_inventory()
    if inv["manager"] is None:
        return []
    return inv["manager"].get_all_skus()


@router.get("/skus/{sku_id}")
async def get_sku(sku_id: str):
    """Get single SKU details with stock locations."""
    inv = _get_inventory()
    if inv["manager"] is None:
        return {}
    sku = inv["manager"].get_sku(sku_id)
    if sku is None:
        raise HTTPException(status_code=404, detail=f"SKU '{sku_id}' not found")
    locations = inv["manager"].get_stock_for_sku(sku_id)
    total = inv["manager"].get_total_stock(sku_id)
    putaway_zone = inv["manager"].get_putaway_zone(sku_id)
    return {
        **sku,
        "locations": locations,
        "total_stock": total,
        "putaway_zone": putaway_zone,
    }


# ── Stock Level Endpoints ──────────────────────────────


@router.get("/stock-levels")
async def get_stock_levels():
    """All SKU stock levels with min/max/reorder status."""
    inv = _get_inventory()
    if inv["manager"] is None:
        return []
    return inv["manager"].get_stock_levels()


@router.get("/stock/{node_name}")
async def get_stock_at_node(node_name: str):
    """Stock at a specific warehouse node."""
    inv = _get_inventory()
    if inv["manager"] is None:
        return []
    return inv["manager"].get_stock_at_node(node_name)


# ── Stock Operations ───────────────────────────────────


@router.post("/receive", dependencies=[Depends(require_api_key)])
async def receive_inventory(body: ReceiveRequest):
    """Receive inventory (inbound putaway)."""
    inv = _get_inventory()
    if inv["manager"] is None:
        raise HTTPException(status_code=503, detail="Inventory not initialized")
    result = inv["manager"].receive(body.sku_id, body.node_name, body.quantity)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/pick", dependencies=[Depends(require_api_key)])
async def pick_inventory(body: PickRequest):
    """Pick inventory (outbound)."""
    inv = _get_inventory()
    if inv["manager"] is None:
        raise HTTPException(status_code=503, detail="Inventory not initialized")
    result = inv["manager"].pick(body.sku_id, body.node_name, body.quantity)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])
    # Feed pick data to optimizer for ABC analysis
    if inv["optimizer"] is not None:
        inv["optimizer"].record_pick(body.sku_id)
    return result


@router.post("/adjust", dependencies=[Depends(require_api_key)])
async def adjust_inventory(body: AdjustRequest):
    """Adjust inventory after cycle count."""
    inv = _get_inventory()
    if inv["manager"] is None:
        raise HTTPException(status_code=503, detail="Inventory not initialized")
    result = inv["manager"].adjust(body.sku_id, body.node_name, body.new_quantity, body.reason)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/transfer", dependencies=[Depends(require_api_key)])
async def transfer_inventory(body: TransferRequest):
    """Transfer inventory between nodes."""
    inv = _get_inventory()
    if inv["manager"] is None:
        raise HTTPException(status_code=503, detail="Inventory not initialized")
    result = inv["manager"].transfer(body.sku_id, body.from_node, body.to_node, body.quantity)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/cycle-count", dependencies=[Depends(require_api_key)])
async def cycle_count(body: CycleCountRequest):
    """Perform cycle count at a node."""
    inv = _get_inventory()
    if inv["manager"] is None:
        raise HTTPException(status_code=503, detail="Inventory not initialized")
    return inv["manager"].cycle_count(body.node_name, body.counts)


# ── Movement Log ───────────────────────────────────────


@router.get("/movements")
async def get_movements(limit: int = 50, sku_id: str = None):
    """Get recent stock movements, optionally filtered by SKU."""
    inv = _get_inventory()
    if inv["manager"] is None:
        return []
    clamped_limit = max(1, min(limit, 500))
    return inv["manager"].get_movements(limit=clamped_limit, sku_id=sku_id)


# ── Replenishment Endpoints (fixed paths before {id}) ──


@router.get("/replenishment")
async def get_replenishment():
    """Get pending replenishment orders."""
    inv = _get_inventory()
    if inv["replenishment"] is None:
        return {"pending": [], "all": []}
    return {
        "pending": inv["replenishment"].get_pending(),
        "all": inv["replenishment"].get_all(),
    }


@router.post("/replenishment/check", dependencies=[Depends(require_api_key)])
async def check_replenishment():
    """Check stock levels and generate replenishment orders for SKUs below reorder point."""
    inv = _get_inventory()
    if inv["replenishment"] is None:
        raise HTTPException(status_code=503, detail="Replenishment engine not initialized")
    new_orders = inv["replenishment"].check_and_generate()
    return {
        "new_orders": new_orders,
        "count": len(new_orders),
        "total_pending": len(inv["replenishment"].get_pending()),
    }


@router.post("/replenishment/{order_id}/complete", dependencies=[Depends(require_api_key)])
async def complete_replenishment(order_id: str):
    """Complete a replenishment order (receives inventory at target node)."""
    inv = _get_inventory()
    if inv["replenishment"] is None:
        raise HTTPException(status_code=503, detail="Replenishment engine not initialized")
    result = inv["replenishment"].complete_order(order_id)
    if not result["ok"]:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/replenishment/{order_id}/cancel", dependencies=[Depends(require_api_key)])
async def cancel_replenishment(order_id: str):
    """Cancel a replenishment order."""
    inv = _get_inventory()
    if inv["replenishment"] is None:
        raise HTTPException(status_code=503, detail="Replenishment engine not initialized")
    result = inv["replenishment"].cancel_order(order_id)
    if not result["ok"]:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ── Storage Optimizer Endpoints ────────────────────────


@router.get("/optimizer/abc")
async def get_abc_analysis():
    """ABC analysis — classify SKUs by pick frequency."""
    inv = _get_inventory()
    if inv["optimizer"] is None:
        return {"A": [], "B": [], "C": []}
    return inv["optimizer"].abc_analysis()


@router.get("/optimizer/recommendations")
async def get_recommendations():
    """Slotting recommendations — move fast-movers closer to pick stations."""
    inv = _get_inventory()
    if inv["optimizer"] is None:
        return []
    return inv["optimizer"].get_recommendations()


@router.get("/optimizer/zone-balance")
async def get_zone_balance():
    """Zone balance analysis — inventory distribution across zones."""
    inv = _get_inventory()
    if inv["optimizer"] is None:
        return {}
    return inv["optimizer"].get_zone_balance()


# ── Combined Stats ─────────────────────────────────────


@router.get("/stats")
async def get_inventory_stats():
    """Combined inventory + replenishment + optimizer stats."""
    inv = _get_inventory()
    result = {}
    if inv["manager"]:
        result["inventory"] = inv["manager"].get_stats()
    if inv["replenishment"]:
        result["replenishment"] = inv["replenishment"].get_stats()
    if inv["optimizer"]:
        result["optimizer"] = inv["optimizer"].get_stats()
    return result

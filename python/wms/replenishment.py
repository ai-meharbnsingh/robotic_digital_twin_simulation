"""
ReplenishmentEngine — auto-generates replenishment orders when stock falls below reorder point.

Flow:
  1. Check all SKU stock levels
  2. Find SKUs below reorder point
  3. Generate replenishment orders (source: inbound staging → target: storage location)
  4. Returns orders for WES integration (caller wires to WES for task generation)

Integrates with InventoryManager for stock levels.
"""

import time
import uuid
from typing import Any, Optional

from .inventory_manager import InventoryManager


class ReplenishOrder:
    """A replenishment order for a single SKU."""

    def __init__(self, sku_id: str, quantity: int, source_zone: str,
                 target_node: str, priority: int = 5):
        self.order_id = str(uuid.uuid4())[:12]
        self.sku_id = sku_id
        self.quantity = quantity
        self.source_zone = source_zone
        self.target_node = target_node
        self.priority = priority
        self.status = "pending"
        self.created_at = time.time()
        self.completed_at: Optional[float] = None

    def complete(self):
        self.status = "completed"
        self.completed_at = time.time()

    def cancel(self):
        self.status = "cancelled"

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "sku_id": self.sku_id,
            "quantity": self.quantity,
            "source_zone": self.source_zone,
            "target_node": self.target_node,
            "priority": self.priority,
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


class ReplenishmentEngine:
    """Generates and manages replenishment orders.

    Usage:
        engine = ReplenishmentEngine(inventory_manager, default_source="Staging")
        orders = engine.check_and_generate()
        # Orders feed into WES for task creation
    """

    def __init__(self, inventory: InventoryManager, default_source: str = "Staging"):
        self._inventory = inventory
        self._default_source = default_source
        self._orders: list[ReplenishOrder] = []
        self._max_orders = 1000

    def check_and_generate(self) -> list[dict]:
        """Check stock levels and generate replenishment orders for SKUs below reorder point.

        Returns list of newly created replenishment orders.
        """
        below = self._inventory.get_items_below_reorder()
        new_orders = []

        for item in below:
            sku_id = item["sku_id"]

            # Skip if there's already a pending order for this SKU
            if any(o.sku_id == sku_id and o.status == "pending" for o in self._orders):
                continue

            sku = self._inventory.get_sku(sku_id)
            if sku is None:
                continue

            # Determine target node from existing stock locations
            existing = self._inventory.get_stock_for_sku(sku_id)
            target_node = existing[0]["node_name"] if existing else "STOR_A_0_0"

            # Priority scale: 10=critical (below min_stock), 5=low (below reorder but above min)
            priority = 10 if item["below_min"] else 5

            order = ReplenishOrder(
                sku_id=sku_id,
                quantity=sku["reorder_qty"],
                source_zone=self._default_source,
                target_node=target_node,
                priority=priority,
            )
            self._orders.append(order)
            new_orders.append(order.to_dict())

        # Trim old completed orders
        if len(self._orders) > self._max_orders:
            self._orders = [o for o in self._orders if o.status == "pending"] + \
                           [o for o in self._orders if o.status != "pending"][-100:]

        return new_orders

    def get_pending(self) -> list[dict]:
        """Return all replenishment orders with status 'pending'."""
        return [o.to_dict() for o in self._orders if o.status == "pending"]

    def get_all(self) -> list[dict]:
        """Return all replenishment orders regardless of status."""
        return [o.to_dict() for o in self._orders]

    def complete_order(self, order_id: str) -> dict:
        """Mark a replenishment order as completed."""
        for o in self._orders:
            if o.order_id == order_id:
                if o.status != "pending":
                    return {"ok": False, "error": f"order status is '{o.status}', not pending"}
                o.complete()
                # Actually receive the inventory
                result = self._inventory.receive(o.sku_id, o.target_node, o.quantity)
                return {"ok": True, "order_id": order_id, "receive_result": result}
        return {"ok": False, "error": f"order '{order_id}' not found"}

    def cancel_order(self, order_id: str) -> dict:
        """Cancel a replenishment order."""
        for o in self._orders:
            if o.order_id == order_id:
                if o.status != "pending":
                    return {"ok": False, "error": f"order status is '{o.status}', not pending"}
                o.cancel()
                return {"ok": True, "order_id": order_id}
        return {"ok": False, "error": f"order '{order_id}' not found"}

    def get_stats(self) -> dict:
        total = len(self._orders)
        pending = sum(1 for o in self._orders if o.status == "pending")
        completed = sum(1 for o in self._orders if o.status == "completed")
        cancelled = sum(1 for o in self._orders if o.status == "cancelled")
        return {
            "total_orders": total,
            "pending": pending,
            "completed": completed,
            "cancelled": cancelled,
        }

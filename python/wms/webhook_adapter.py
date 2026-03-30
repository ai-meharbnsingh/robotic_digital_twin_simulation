"""
Generic webhook adapter — any WMS that can POST orders to us.

This adapter receives orders via HTTP webhook (POST to /api/wms/webhook/receive)
and stores them in memory until fetch_orders() is called.

This is the primary adapter for testing since it requires no external services.
"""

import logging
import time
import uuid

from wms.connector import WMSConnector

logger = logging.getLogger(__name__)

MAX_ORDERS = 50_000


class WebhookAdapter(WMSConnector):
    """Generic HTTP webhook — any WMS that can POST orders."""

    def __init__(self, callback_url: str = ""):
        """
        Args:
            callback_url: Optional URL to notify when order is processed.
        """
        self._callback_url = callback_url
        self._pending_orders: list[dict] = []
        self._processed_orders: list[dict] = []
        self._seen_order_ids: set[str] = set()

    async def receive_order(self, order: dict) -> dict:
        """Called when webhook POSTs an order to us.

        Args:
            order: Raw order payload from external WMS.

        Returns:
            Receipt confirmation with assigned internal ID.

        Raises:
            ValueError: If order with same external ID already exists.
            OverflowError: If order store is at capacity (MAX_ORDERS).
        """
        # Duplicate order ID check
        ext_id = order.get("id", "")
        if ext_id and ext_id in self._seen_order_ids:
            raise ValueError(f"Duplicate order ID: {ext_id}")

        # Capacity check
        total = len(self._pending_orders) + len(self._processed_orders)
        if total >= MAX_ORDERS:
            raise OverflowError(
                f"Order store at capacity ({MAX_ORDERS}). Sync or purge before adding more."
            )

        internal_id = str(uuid.uuid4())[:8]
        enriched = {
            **order,
            "_internal_id": internal_id,
            "_received_at": time.time(),
            "_source": "webhook",
        }
        self._pending_orders.append(enriched)
        if ext_id:
            self._seen_order_ids.add(ext_id)
        logger.info("Webhook received order %s (internal_id=%s)", order.get("id", "?"), internal_id)
        return {"internal_id": internal_id, "status": "received"}

    async def fetch_orders(self) -> list[dict]:
        """Return and clear pending orders."""
        orders = list(self._pending_orders)
        self._processed_orders.extend(orders)
        self._pending_orders.clear()
        return orders

    async def update_order_status(self, order_id: str, status: str) -> dict:
        """Update status of a processed order (in-memory)."""
        for order in self._processed_orders:
            if order.get("_internal_id") == order_id or order.get("id") == order_id:
                order["_status"] = status
                return {"order_id": order_id, "status": status, "updated": True}
        return {"order_id": order_id, "error": "not_found"}

    async def get_inventory(self) -> list[dict]:
        """Webhook adapter has no inventory — return empty list."""
        return []

    def get_status(self) -> dict:
        """Return webhook adapter status."""
        return {
            "type": "webhook",
            "connected": True,  # Always connected — we ARE the receiver
            "pending_orders": len(self._pending_orders),
            "processed_orders": len(self._processed_orders),
            "callback_url": self._callback_url,
        }

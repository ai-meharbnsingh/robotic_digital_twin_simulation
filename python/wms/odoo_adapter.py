"""
Odoo ERP adapter — Odoo integration via XML-RPC.

Uses Odoo's standard XML-RPC interface (xmlrpc/2/common + xmlrpc/2/object)
to pull sale.order records and update their status.

Graceful degradation: if Odoo is unreachable, methods raise ConnectionError.
"""

import asyncio
import logging
import xmlrpc.client

from wms.connector import WMSConnector

logger = logging.getLogger(__name__)


class OdooAdapter(WMSConnector):
    """Odoo ERP integration via XML-RPC."""

    def __init__(self, url: str, db: str, user: str, password: str):
        """
        Args:
            url: Odoo server URL (e.g. http://odoo:8069).
            db: Odoo database name.
            user: Odoo username.
            password: Odoo password.
        """
        self._url = url.rstrip("/")
        self._db = db
        self._user = user
        self._password = password
        self._uid: int | None = None
        self._connected = False

    def _authenticate(self) -> int:
        """Authenticate with Odoo XML-RPC and return uid."""
        try:
            common = xmlrpc.client.ServerProxy(f"{self._url}/xmlrpc/2/common")
            uid = common.authenticate(self._db, self._user, self._password, {})
            if not uid:
                raise ConnectionError("Odoo authentication failed")
            self._uid = uid
            self._connected = True
            return uid
        except Exception as exc:
            self._connected = False
            logger.error("Odoo authentication failed: %s", exc)
            raise ConnectionError(f"Odoo unreachable: {exc}") from exc

    def _models(self) -> xmlrpc.client.ServerProxy:
        """Get Odoo models proxy."""
        return xmlrpc.client.ServerProxy(f"{self._url}/xmlrpc/2/object")

    def _fetch_orders_sync(self) -> list[dict]:
        """Synchronous fetch — runs in thread to avoid blocking event loop."""
        uid = self._uid or self._authenticate()
        models = self._models()
        order_ids = models.execute_kw(
            self._db, uid, self._password,
            "sale.order", "search",
            [[["state", "in", ["sale", "done"]]]],
            {"limit": 100},
        )
        if not order_ids:
            return []
        orders = models.execute_kw(
            self._db, uid, self._password,
            "sale.order", "read",
            [order_ids],
            {"fields": ["name", "partner_id", "order_line", "state", "date_order"]},
        )
        self._connected = True
        return orders

    async def fetch_orders(self) -> list[dict]:
        """Pull pending sale.order records from Odoo via XML-RPC (threaded)."""
        try:
            return await asyncio.to_thread(self._fetch_orders_sync)
        except Exception as exc:
            self._connected = False
            logger.error("Odoo fetch_orders failed: %s", exc)
            raise ConnectionError(f"Odoo unreachable: {exc}") from exc

    def _update_order_status_sync(self, order_id: str, status: str) -> dict:
        """Synchronous update — runs in thread."""
        uid = self._uid or self._authenticate()
        models = self._models()
        ids = models.execute_kw(
            self._db, uid, self._password,
            "sale.order", "search",
            [[["name", "=", order_id]]],
        )
        if not ids:
            return {"error": "order_not_found", "order_id": order_id}
        models.execute_kw(
            self._db, uid, self._password,
            "sale.order", "write",
            [ids, {"note": f"RDT status: {status}"}],
        )
        self._connected = True
        return {"order_id": order_id, "status": status, "updated": True}

    async def update_order_status(self, order_id: str, status: str) -> dict:
        """Update order status in Odoo (threaded)."""
        try:
            return await asyncio.to_thread(self._update_order_status_sync, order_id, status)
        except Exception as exc:
            self._connected = False
            logger.error("Odoo update_order_status failed: %s", exc)
            raise ConnectionError(f"Odoo unreachable: {exc}") from exc

    def _get_inventory_sync(self) -> list[dict]:
        """Synchronous inventory fetch — runs in thread."""
        uid = self._uid or self._authenticate()
        models = self._models()
        quant_ids = models.execute_kw(
            self._db, uid, self._password,
            "stock.quant", "search",
            [[]],
            {"limit": 500},
        )
        if not quant_ids:
            return []
        quants = models.execute_kw(
            self._db, uid, self._password,
            "stock.quant", "read",
            [quant_ids],
            {"fields": ["product_id", "location_id", "quantity", "lot_id"]},
        )
        self._connected = True
        return quants

    async def get_inventory(self) -> list[dict]:
        """Pull stock.quant records from Odoo (threaded)."""
        try:
            return await asyncio.to_thread(self._get_inventory_sync)
        except Exception as exc:
            self._connected = False
            logger.error("Odoo get_inventory failed: %s", exc)
            raise ConnectionError(f"Odoo unreachable: {exc}") from exc

    def get_status(self) -> dict:
        """Return Odoo connector status."""
        return {
            "type": "odoo",
            "url": self._url,
            "database": self._db,
            "connected": self._connected,
            "authenticated": self._uid is not None,
        }

"""
WMS Connector — abstract base for WMS/ERP integrations.

All adapters (SAP, Odoo, Webhook) implement this interface.
The API layer uses only this interface, never adapter-specific methods.
"""

from abc import ABC, abstractmethod


class WMSConnector(ABC):
    """Abstract base for WMS/ERP integrations."""

    @abstractmethod
    async def fetch_orders(self) -> list[dict]:
        """Pull pending orders from WMS.

        Returns:
            List of orders in the WMS-specific format.
            Use OrderTranslator to convert to internal format.
        """

    @abstractmethod
    async def update_order_status(self, order_id: str, status: str) -> dict:
        """Push status back to WMS.

        Args:
            order_id: Internal order ID.
            status: New status string (e.g. 'picked', 'shipped', 'failed').

        Returns:
            Dict with update confirmation from WMS.
        """

    @abstractmethod
    async def get_inventory(self) -> list[dict]:
        """Get current inventory positions from WMS.

        Returns:
            List of inventory items in WMS-specific format.
        """

    @abstractmethod
    def get_status(self) -> dict:
        """Return connector status (type, connected, etc.)."""

    async def receive_order(self, order: dict) -> dict:
        """Receive an inbound order (webhook-style).

        Not all connectors support inbound webhooks.  The default
        implementation raises NotImplementedError — only the
        WebhookAdapter overrides this.

        Args:
            order: Raw order payload from external WMS.

        Returns:
            Receipt confirmation dict.

        Raises:
            NotImplementedError: If the concrete adapter does not
                support receiving orders (e.g. SAP, Odoo).
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support receive_order"
        )

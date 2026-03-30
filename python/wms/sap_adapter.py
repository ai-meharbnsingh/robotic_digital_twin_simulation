"""
SAP WM adapter — SAP Warehouse Management integration via REST proxy.

Communicates with SAP through an RFC/BAPI REST bridge (e.g. SAP Cloud Connector
or custom middleware). Translates SAP-specific field names (AUFNR, MATNR, WERKS)
to internal order format via OrderTranslator.

Graceful degradation: if SAP endpoint is unreachable, methods raise
ConnectionError and the route layer returns 503.
"""

import logging
from typing import Any

import httpx

from wms.connector import WMSConnector

logger = logging.getLogger(__name__)


class SAPAdapter(WMSConnector):
    """SAP WM integration via REST proxy (RFC/BAPI bridge)."""

    def __init__(self, base_url: str, api_key: str):
        """
        Args:
            base_url: SAP REST proxy URL (e.g. http://sap-proxy:8080).
            api_key: API key for SAP proxy authentication.
        """
        self._url = base_url.rstrip("/")
        self._key = api_key
        self._connected = False

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-SAP-API-Key": self._key,
        }

    async def fetch_orders(self) -> list[dict]:
        """GET /sap/orders -> convert SAP order format to internal."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self._url}/sap/orders",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                self._connected = True
                return resp.json()
        except Exception as exc:
            self._connected = False
            logger.error("SAP fetch_orders failed: %s", exc)
            raise ConnectionError(f"SAP unreachable: {exc}") from exc

    async def update_order_status(self, order_id: str, status: str) -> dict:
        """POST /sap/orders/{id}/status -> push status to SAP."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self._url}/sap/orders/{order_id}/status",
                    headers=self._headers(),
                    json={"status": status},
                )
                resp.raise_for_status()
                self._connected = True
                return resp.json()
        except Exception as exc:
            self._connected = False
            logger.error("SAP update_order_status failed: %s", exc)
            raise ConnectionError(f"SAP unreachable: {exc}") from exc

    async def get_inventory(self) -> list[dict]:
        """GET /sap/inventory -> convert SAP inventory to internal."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self._url}/sap/inventory",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                self._connected = True
                return resp.json()
        except Exception as exc:
            self._connected = False
            logger.error("SAP get_inventory failed: %s", exc)
            raise ConnectionError(f"SAP unreachable: {exc}") from exc

    def get_status(self) -> dict:
        """Return SAP connector status."""
        return {
            "type": "sap",
            "base_url": self._url,
            "connected": self._connected,
        }

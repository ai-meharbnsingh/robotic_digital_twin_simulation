"""
Tests for Phase 12 — WMS/SAP Connector.

Tests WMS connector, adapters, order translator, DLQ, and REST endpoints.
TDD: Written FIRST, then implementation until green.

No MagicMock. Real objects. Real assertions.
All tests work WITHOUT SAP/Odoo — uses webhook adapter.
"""

import os
import time

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app, app_state, lifespan


@pytest_asyncio.fixture
async def client():
    """Async test client with lifespan."""
    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c


@pytest_asyncio.fixture
async def authed_client():
    """Async test client with API key header."""
    async with lifespan(app):
        transport = ASGITransport(app=app)
        headers = {"X-API-Key": app_state.get("settings").api_key}
        async with AsyncClient(transport=transport, base_url="http://testserver", headers=headers) as c:
            yield c


# ── WebhookAdapter unit tests ─────────────────────────────


class TestWebhookAdapter:
    """Test WebhookAdapter without any external services."""

    @pytest.mark.asyncio
    async def test_webhook_receive_order(self):
        """Webhook adapter stores received orders."""
        from wms.webhook_adapter import WebhookAdapter

        adapter = WebhookAdapter()
        result = await adapter.receive_order({"id": "WH-001", "items": [{"sku": "BOLT-M8", "quantity": 50}]})

        assert result["status"] == "received"
        assert "internal_id" in result
        assert len(result["internal_id"]) == 8

    @pytest.mark.asyncio
    async def test_webhook_fetch_orders(self):
        """fetch_orders returns and clears pending orders."""
        from wms.webhook_adapter import WebhookAdapter

        adapter = WebhookAdapter()
        await adapter.receive_order({"id": "WH-001", "items": [{"sku": "A", "quantity": 1}]})
        await adapter.receive_order({"id": "WH-002", "items": [{"sku": "B", "quantity": 2}]})

        orders = await adapter.fetch_orders()
        assert len(orders) == 2
        assert orders[0]["id"] == "WH-001"
        assert orders[1]["id"] == "WH-002"
        assert orders[0]["_source"] == "webhook"

        # Second fetch returns empty — orders were cleared
        orders2 = await adapter.fetch_orders()
        assert len(orders2) == 0

    @pytest.mark.asyncio
    async def test_webhook_update_order_status(self):
        """update_order_status marks processed order."""
        from wms.webhook_adapter import WebhookAdapter

        adapter = WebhookAdapter()
        receipt = await adapter.receive_order({"id": "WH-003", "items": []})
        await adapter.fetch_orders()  # Move to processed

        result = await adapter.update_order_status(receipt["internal_id"], "picked")
        assert result["updated"] is True
        assert result["status"] == "picked"

    @pytest.mark.asyncio
    async def test_webhook_get_status(self):
        """Webhook adapter always reports connected."""
        from wms.webhook_adapter import WebhookAdapter

        adapter = WebhookAdapter(callback_url="http://test/callback")
        status = adapter.get_status()

        assert status["type"] == "webhook"
        assert status["connected"] is True
        assert status["pending_orders"] == 0
        assert status["callback_url"] == "http://test/callback"

    @pytest.mark.asyncio
    async def test_webhook_get_inventory_empty(self):
        """Webhook adapter returns empty inventory."""
        from wms.webhook_adapter import WebhookAdapter

        adapter = WebhookAdapter()
        inv = await adapter.get_inventory()
        assert inv == []


# ── OrderTranslator unit tests ─────────────────────────────


class TestOrderTranslator:
    """Test order format translation for all sources."""

    def test_order_translator_sap(self):
        """SAP order with AUFNR/MATNR fields translates correctly."""
        from wms.order_translator import OrderTranslator

        sap_order = {
            "AUFNR": "SAP-40001234",
            "KUNNR": "CUST-99",
            "PRIOK": 1,
            "ERDAT": "2026-03-30T10:00:00Z",
            "items": [
                {"MATNR": "BOLT-M8", "MENGE": 100, "LGORT": "BIN-A3"},
                {"MATNR": "NUT-M8", "MENGE": 200, "LGORT": "BIN-B7"},
            ],
        }
        result = OrderTranslator.from_sap(sap_order)

        assert result["order_id"] == "SAP-40001234"
        assert result["source"] == "sap"
        assert result["customer"] == "CUST-99"
        assert result["priority"] == 1
        assert len(result["items"]) == 2
        assert result["items"][0]["sku"] == "BOLT-M8"
        assert result["items"][0]["quantity"] == 100
        assert result["items"][0]["location"] == "BIN-A3"
        assert result["items"][1]["sku"] == "NUT-M8"
        assert result["items"][1]["quantity"] == 200
        assert result["raw"] == sap_order

    def test_order_translator_odoo(self):
        """Odoo sale.order with partner_id/order_line translates correctly."""
        from wms.order_translator import OrderTranslator

        odoo_order = {
            "name": "SO0042",
            "partner_id": [7, "Acme Corp"],
            "state": "sale",
            "date_order": "2026-03-30 08:00:00",
            "order_line": [
                {"product_id": [15, "Widget-X"], "product_uom_qty": 25, "warehouse_id": "WH-1"},
            ],
        }
        result = OrderTranslator.from_odoo(odoo_order)

        assert result["order_id"] == "SO0042"
        assert result["source"] == "odoo"
        assert result["customer"] == "Acme Corp"
        assert result["priority"] == 3  # Odoo default
        assert len(result["items"]) == 1
        assert result["items"][0]["sku"] == "Widget-X"
        assert result["items"][0]["quantity"] == 25
        assert result["raw"] == odoo_order

    def test_order_translator_webhook(self):
        """Generic webhook payload translates correctly."""
        from wms.order_translator import OrderTranslator

        payload = {
            "id": "WEB-777",
            "customer": "Bob's Warehouse",
            "priority": 2,
            "items": [
                {"sku": "PALLET-WRAP", "quantity": 10, "location": "DOCK-3"},
            ],
        }
        result = OrderTranslator.from_webhook(payload)

        assert result["order_id"] == "WEB-777"
        assert result["source"] == "webhook"
        assert result["customer"] == "Bob's Warehouse"
        assert result["priority"] == 2
        assert len(result["items"]) == 1
        assert result["items"][0]["sku"] == "PALLET-WRAP"
        assert result["items"][0]["quantity"] == 10
        assert result["items"][0]["location"] == "DOCK-3"

    def test_order_translator_to_internal_auto_detect(self):
        """to_internal routes to correct translator by source."""
        from wms.order_translator import OrderTranslator

        sap = OrderTranslator.to_internal("sap", {"AUFNR": "X", "items": []})
        assert sap["source"] == "sap"

        odoo = OrderTranslator.to_internal("odoo", {"name": "SO1", "order_line": []})
        assert odoo["source"] == "odoo"

        webhook = OrderTranslator.to_internal("webhook", {"id": "W1", "items": []})
        assert webhook["source"] == "webhook"

    def test_order_translator_unknown_source_raises(self):
        """to_internal raises ValueError for unknown source."""
        from wms.order_translator import OrderTranslator

        with pytest.raises(ValueError, match="Unknown WMS source"):
            OrderTranslator.to_internal("oracle", {})


# ── DLQ unit tests ─────────────────────────────────────────


class TestDeadLetterQueue:
    """Test DLQ without RabbitMQ (in-memory mode)."""

    @pytest.mark.asyncio
    async def test_dlq_enqueue(self):
        """DLQ enqueues failed orders gracefully without RabbitMQ."""
        from wms.dlq import DeadLetterQueue

        dlq = DeadLetterQueue()  # No RabbitMQ URL — in-memory mode
        result = await dlq.enqueue({"id": "FAIL-1"}, "Connection timeout")

        assert result["status"] == "enqueued"
        assert "message_id" in result
        assert len(result["message_id"]) == 12

    @pytest.mark.asyncio
    async def test_dlq_list_dead_letters(self):
        """DLQ lists entries newest first."""
        from wms.dlq import DeadLetterQueue

        dlq = DeadLetterQueue()
        await dlq.enqueue({"id": "F1"}, "Error 1")
        await dlq.enqueue({"id": "F2"}, "Error 2")

        entries = await dlq.list_dead_letters()
        assert len(entries) == 2
        assert entries[0]["order"]["id"] == "F2"  # Newest first
        assert entries[1]["order"]["id"] == "F1"
        assert entries[0]["error"] == "Error 2"
        assert entries[0]["status"] == "dead"

    @pytest.mark.asyncio
    async def test_dlq_retry(self):
        """DLQ retry marks entry as retrying and returns order."""
        from wms.dlq import DeadLetterQueue

        dlq = DeadLetterQueue()
        receipt = await dlq.enqueue({"id": "F3"}, "Timeout")
        message_id = receipt["message_id"]

        result = await dlq.retry(message_id)
        assert result["status"] == "retrying"
        assert result["retry_count"] == 1
        assert result["order"]["id"] == "F3"

    @pytest.mark.asyncio
    async def test_dlq_retry_nonexistent(self):
        """DLQ retry raises KeyError for unknown message_id."""
        from wms.dlq import DeadLetterQueue

        dlq = DeadLetterQueue()
        with pytest.raises(KeyError, match="DLQ message not found"):
            await dlq.retry("nonexistent-id")

    @pytest.mark.asyncio
    async def test_dlq_status(self):
        """DLQ status reports correct counts."""
        from wms.dlq import DeadLetterQueue

        dlq = DeadLetterQueue()
        await dlq.enqueue({"id": "X1"}, "err")
        r = await dlq.enqueue({"id": "X2"}, "err")
        await dlq.retry(r["message_id"])

        status = dlq.get_status()
        assert status["total"] == 2
        assert status["dead"] == 1
        assert status["retrying"] == 1
        assert status["rabbitmq_connected"] is False


# ── WMS Connector base test ────────────────────────────────


class TestWMSConnectorABC:
    """Test that WMSConnector is a proper ABC — cannot be instantiated."""

    def test_cannot_instantiate_abstract(self):
        """WMSConnector raises TypeError if instantiated directly."""
        from wms.connector import WMSConnector

        with pytest.raises(TypeError):
            WMSConnector()


# ── SAP Adapter test (no real SAP) ─────────────────────────


class TestSAPAdapter:
    """Test SAP adapter structure (no real SAP endpoint)."""

    def test_sap_adapter_status(self):
        """SAP adapter reports status correctly."""
        from wms.sap_adapter import SAPAdapter

        adapter = SAPAdapter(base_url="http://sap-proxy:8080", api_key="test-key")
        status = adapter.get_status()

        assert status["type"] == "sap"
        assert status["base_url"] == "http://sap-proxy:8080"
        assert status["connected"] is False  # Not connected until successful call


# ── REST endpoint tests ────────────────────────────────────


class TestWMSEndpoints:
    """Test WMS REST endpoints via ASGI test client."""

    @pytest.mark.asyncio
    async def test_wms_status_endpoint(self, client):
        """GET /api/wms/status returns connector status."""
        resp = await client.get("/api/wms/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "connector_initialized" in data
        assert "dlq" in data

    @pytest.mark.asyncio
    async def test_wms_orders_endpoint(self, client):
        """GET /api/wms/orders returns order list."""
        resp = await client.get("/api/wms/orders")
        assert resp.status_code == 200
        data = resp.json()
        assert "orders" in data
        assert "total" in data
        assert isinstance(data["orders"], list)

    @pytest.mark.asyncio
    async def test_wms_webhook_endpoint(self, authed_client):
        """POST /api/wms/webhook/receive accepts order."""
        payload = {
            "id": "TEST-WH-001",
            "items": [{"sku": "WIDGET", "quantity": 5, "location": "BIN-1"}],
            "priority": 2,
            "customer": "Test Corp",
        }
        resp = await authed_client.post("/api/wms/webhook/receive", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "received"
        assert "internal_id" in data

    @pytest.mark.asyncio
    async def test_wms_sync_endpoint(self, authed_client):
        """POST /api/wms/sync pulls orders from connector."""
        # First send an order via webhook
        await authed_client.post("/api/wms/webhook/receive", json={
            "id": "SYNC-001",
            "items": [{"sku": "PART-A", "quantity": 10}],
        })
        # Then sync
        resp = await authed_client.post("/api/wms/sync")
        assert resp.status_code == 200
        data = resp.json()
        assert data["synced"] >= 1
        assert "errors" in data
        assert "total_orders" in data

    @pytest.mark.asyncio
    async def test_wms_dlq_endpoint(self, client):
        """GET /api/wms/dlq returns DLQ entries."""
        resp = await client.get("/api/wms/dlq")
        assert resp.status_code == 200
        data = resp.json()
        assert "dead_letters" in data
        assert "total" in data
        assert isinstance(data["dead_letters"], list)

    @pytest.mark.asyncio
    async def test_invalid_webhook_payload(self, authed_client):
        """POST /api/wms/webhook/receive with empty payload returns 400."""
        resp = await authed_client.post("/api/wms/webhook/receive", json={
            "id": "",
            "items": [],
        })
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_retry_nonexistent_dlq(self, authed_client):
        """POST /api/wms/dlq/{id}/retry with bad ID returns 404."""
        resp = await authed_client.post("/api/wms/dlq/nonexistent-id/retry")
        assert resp.status_code == 404


# ── Endpoint count test ────────────────────────────────────


# ── Odoo translator with real structure ───────────────────


class TestOdooTranslatorEdgeCases:
    """Test Odoo translator handles real Odoo response shapes."""

    def test_odoo_order_line_as_id_array(self):
        """Odoo sometimes returns order_line as bare integer IDs."""
        from wms.order_translator import OrderTranslator

        odoo_order = {
            "name": "SO0099",
            "partner_id": [42, "Test Partner"],
            "state": "sale",
            "date_order": "2026-03-30 12:00:00",
            "order_line": [101, 102, 103],  # ID-only array
        }
        result = OrderTranslator.from_odoo(odoo_order)

        assert result["order_id"] == "SO0099"
        assert result["source"] == "odoo"
        assert len(result["items"]) == 3
        assert result["items"][0]["sku"] == "odoo-line-101"
        assert result["items"][1]["sku"] == "odoo-line-102"
        assert result["items"][2]["sku"] == "odoo-line-103"
        assert result["customer"] == "Test Partner"

    def test_odoo_product_id_as_bare_int(self):
        """Odoo product_id can be a bare int instead of [id, name] tuple."""
        from wms.order_translator import OrderTranslator

        odoo_order = {
            "name": "SO0100",
            "partner_id": "Direct Customer",
            "order_line": [
                {"product_id": 77, "product_uom_qty": 5},
            ],
        }
        result = OrderTranslator.from_odoo(odoo_order)

        assert result["items"][0]["sku"] == "77"
        assert result["items"][0]["quantity"] == 5
        # partner_id as bare string
        assert result["customer"] == "Direct Customer"

    def test_odoo_empty_order_line(self):
        """Odoo order with empty order_line produces zero items."""
        from wms.order_translator import OrderTranslator

        result = OrderTranslator.from_odoo({"name": "SO-EMPTY", "order_line": []})
        assert result["items"] == []
        assert result["order_id"] == "SO-EMPTY"


# ── SAP translator edge cases ────────────────────────────


class TestSAPTranslatorEdgeCases:
    """Test SAP translator edge cases."""

    def test_sap_order_with_posnr_items(self):
        """SAP order using POSNR key for line items."""
        from wms.order_translator import OrderTranslator

        sap_order = {
            "AUFNR": "SAP-99999",
            "KUNNR": "CUST-1",
            "PRIOK": 2,
            "POSNR": [
                {"MATNR": "GEAR-01", "MENGE": 10, "LGORT": "SHELF-A"},
            ],
        }
        result = OrderTranslator.from_sap(sap_order)
        assert result["order_id"] == "SAP-99999"
        assert result["items"][0]["sku"] == "GEAR-01"
        assert result["items"][0]["quantity"] == 10
        assert result["items"][0]["location"] == "SHELF-A"

    def test_sap_order_with_generic_keys(self):
        """SAP order using generic key names (fallback)."""
        from wms.order_translator import OrderTranslator

        sap_order = {
            "order_id": "GEN-001",
            "customer": "Generic Corp",
            "priority": 4,
            "items": [
                {"sku": "PART-Z", "quantity": 3, "location": "BIN-99"},
            ],
        }
        result = OrderTranslator.from_sap(sap_order)
        assert result["order_id"] == "GEN-001"
        assert result["customer"] == "Generic Corp"
        assert result["priority"] == 4
        assert result["items"][0]["sku"] == "PART-Z"

    def test_sap_order_no_items(self):
        """SAP order with no items key produces empty items list."""
        from wms.order_translator import OrderTranslator

        result = OrderTranslator.from_sap({"AUFNR": "SAP-EMPTY"})
        assert result["items"] == []
        assert result["order_id"] == "SAP-EMPTY"


# ── Webhook duplicate order rejection ────────────────────


class TestWebhookDuplicateRejection:
    """Test that webhook adapter rejects duplicate order IDs."""

    @pytest.mark.asyncio
    async def test_duplicate_order_id_rejected(self):
        """Second order with same ID raises ValueError."""
        from wms.webhook_adapter import WebhookAdapter

        adapter = WebhookAdapter()
        await adapter.receive_order({"id": "DUP-001", "items": []})

        with pytest.raises(ValueError, match="Duplicate order ID"):
            await adapter.receive_order({"id": "DUP-001", "items": []})

    @pytest.mark.asyncio
    async def test_empty_id_allows_duplicates(self):
        """Orders with empty ID are not tracked for duplicates."""
        from wms.webhook_adapter import WebhookAdapter

        adapter = WebhookAdapter()
        r1 = await adapter.receive_order({"id": "", "items": [{"sku": "A", "quantity": 1}]})
        r2 = await adapter.receive_order({"id": "", "items": [{"sku": "B", "quantity": 2}]})
        assert r1["status"] == "received"
        assert r2["status"] == "received"


# ── DLQ max size enforcement ─────────────────────────────


class TestDLQMaxSize:
    """Test DLQ evicts oldest entries when at capacity."""

    @pytest.mark.asyncio
    async def test_dlq_evicts_oldest_at_capacity(self):
        """DLQ drops oldest entry when MAX_DLQ_SIZE reached."""
        from wms.dlq import DeadLetterQueue, MAX_DLQ_SIZE

        dlq = DeadLetterQueue()
        # Use a small MAX for testing — temporarily override
        import wms.dlq as dlq_mod
        original_max = dlq_mod.MAX_DLQ_SIZE
        dlq_mod.MAX_DLQ_SIZE = 5
        try:
            for i in range(6):
                await dlq.enqueue({"id": f"F-{i}"}, f"Error {i}")

            status = dlq.get_status()
            assert status["total"] == 5  # Oldest was evicted
            entries = await dlq.list_dead_letters()
            # Oldest entry (F-0) should be gone, newest (F-5) should be present
            ids = [e["order"]["id"] for e in entries]
            assert "F-0" not in ids
            assert "F-5" in ids
        finally:
            dlq_mod.MAX_DLQ_SIZE = original_max


# ── Auth on webhook endpoint ─────────────────────────────


class TestWebhookAuth:
    """Test that webhook endpoint requires API key when configured."""

    @pytest.mark.asyncio
    async def test_webhook_403_without_api_key(self):
        """POST /api/wms/webhook/receive returns 403 without API key when key is set."""
        # Set API_KEY env var so get_settings() creates a Settings with auth enabled
        original_env = os.environ.get("API_KEY", "")
        os.environ["API_KEY"] = "test-secret-key-for-auth"
        try:
            async with lifespan(app):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://testserver") as c:
                    resp = await c.post("/api/wms/webhook/receive", json={
                        "id": "NOAUTH-001",
                        "items": [{"sku": "X", "quantity": 1}],
                    })
                    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"
        finally:
            if original_env:
                os.environ["API_KEY"] = original_env
            else:
                os.environ.pop("API_KEY", None)

    @pytest.mark.asyncio
    async def test_webhook_200_with_api_key(self, authed_client):
        """POST /api/wms/webhook/receive succeeds with valid API key."""
        resp = await authed_client.post("/api/wms/webhook/receive", json={
            "id": "AUTH-001",
            "items": [{"sku": "Y", "quantity": 1}],
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "received"


# ── Endpoint count test ────────────────────────────────────


class TestEndpointCount:
    """Verify total endpoint count after Phase 12."""

    @pytest.mark.asyncio
    async def test_endpoint_count_71(self, client):
        """Total API endpoint count is 71 after Phase 12 (was 65)."""
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["endpoints"] == 71, f"Expected 71 endpoints, got {data['endpoints']}"

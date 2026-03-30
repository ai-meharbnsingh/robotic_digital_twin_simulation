"""
Inventory API Endpoint Tests -- HTTP-level tests via AsyncClient.

Tests all 18 inventory endpoints: SKU catalog, stock operations,
replenishment, storage optimizer, stats.
Verifies: status codes, response shapes, auth guards, error responses,
route ordering (fixed paths before parameterized).

Phase 14 -- matches test_wcs_api.py pattern.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app, lifespan


API_KEY = "test-key-for-dev"
AUTH_HEADERS = {"X-API-Key": API_KEY}


@pytest_asyncio.fixture
async def client():
    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c


# ==========================================================
# SKU CATALOG ENDPOINTS
# ==========================================================


class TestSKUEndpoints:
    async def test_list_skus(self, client):
        r = await client.get("/api/inventory/skus")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 8
        ids = {s["sku_id"] for s in data}
        assert "SKU-ELEC-001" in ids
        assert "SKU-FOOD-001" in ids
        assert "SKU-IND-002" in ids

    async def test_get_sku_details(self, client):
        r = await client.get("/api/inventory/skus/SKU-ELEC-001")
        assert r.status_code == 200
        data = r.json()
        assert data["sku_id"] == "SKU-ELEC-001"
        assert data["name"] == "Wireless Headphones"
        assert data["category"] == "electronics"
        assert data["storage_class"] == "standard"
        assert data["min_stock"] == 20
        assert data["max_stock"] == 200
        assert data["reorder_point"] == 50
        assert data["reorder_qty"] == 100
        assert isinstance(data["locations"], list)
        assert isinstance(data["total_stock"], int)
        assert "putaway_zone" in data

    async def test_get_sku_404(self, client):
        r = await client.get("/api/inventory/skus/NONEXISTENT")
        assert r.status_code == 404

    async def test_sku_cold_storage(self, client):
        r = await client.get("/api/inventory/skus/SKU-FOOD-001")
        assert r.status_code == 200
        assert r.json()["storage_class"] == "cold"
        assert r.json()["putaway_zone"] == "Storage_B"


# ==========================================================
# STOCK LEVEL ENDPOINTS
# ==========================================================


class TestStockLevelEndpoints:
    async def test_stock_levels(self, client):
        r = await client.get("/api/inventory/stock-levels")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 8
        for item in data:
            assert item["total_stock"] == 0
            assert item["status"] == "critical"
            assert item["below_min"] is True

    async def test_stock_at_node_empty(self, client):
        r = await client.get("/api/inventory/stock/STOR_A_0_0")
        assert r.status_code == 200
        assert r.json() == []

    async def test_stock_at_node_after_receive(self, client):
        await client.post(
            "/api/inventory/receive",
            json={"sku_id": "SKU-ELEC-001", "node_name": "STOR_A_0_0", "quantity": 50},
            headers=AUTH_HEADERS,
        )
        r = await client.get("/api/inventory/stock/STOR_A_0_0")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["sku_id"] == "SKU-ELEC-001"
        assert data[0]["quantity"] == 50


# ==========================================================
# STOCK OPERATION ENDPOINTS
# ==========================================================


class TestReceiveEndpoint:
    async def test_receive_inventory(self, client):
        r = await client.post(
            "/api/inventory/receive",
            json={"sku_id": "SKU-ELEC-001", "node_name": "STOR_A_0_0", "quantity": 50},
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["sku_id"] == "SKU-ELEC-001"
        assert data["node"] == "STOR_A_0_0"
        assert data["new_quantity"] == 50

    async def test_receive_unknown_sku(self, client):
        r = await client.post(
            "/api/inventory/receive",
            json={"sku_id": "FAKE-SKU", "node_name": "STOR_A_0_0", "quantity": 10},
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 400

    async def test_receive_works_in_sim_mode(self, client):
        """Auth skipped in simulation mode (API_KEY not set)."""
        r = await client.post(
            "/api/inventory/receive",
            json={"sku_id": "SKU-ELEC-001", "node_name": "STOR_A_0_0", "quantity": 10},
        )
        assert r.status_code == 200


class TestPickEndpoint:
    async def test_pick_inventory(self, client):
        await client.post(
            "/api/inventory/receive",
            json={"sku_id": "SKU-ELEC-001", "node_name": "STOR_A_0_0", "quantity": 50},
            headers=AUTH_HEADERS,
        )
        r = await client.post(
            "/api/inventory/pick",
            json={"sku_id": "SKU-ELEC-001", "node_name": "STOR_A_0_0", "quantity": 10},
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["picked"] == 10
        assert data["remaining"] == 40

    async def test_pick_insufficient(self, client):
        r = await client.post(
            "/api/inventory/pick",
            json={"sku_id": "SKU-ELEC-001", "node_name": "STOR_A_0_0", "quantity": 999},
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 400


class TestAdjustEndpoint:
    async def test_adjust_inventory(self, client):
        await client.post(
            "/api/inventory/receive",
            json={"sku_id": "SKU-ELEC-001", "node_name": "STOR_A_0_0", "quantity": 30},
            headers=AUTH_HEADERS,
        )
        r = await client.post(
            "/api/inventory/adjust",
            json={
                "sku_id": "SKU-ELEC-001",
                "node_name": "STOR_A_0_0",
                "new_quantity": 50,
                "reason": "found extra",
            },
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["old_quantity"] == 30
        assert data["new_quantity"] == 50
        assert data["delta"] == 20


class TestTransferEndpoint:
    async def test_transfer_inventory(self, client):
        await client.post(
            "/api/inventory/receive",
            json={"sku_id": "SKU-ELEC-001", "node_name": "STOR_A_0_0", "quantity": 50},
            headers=AUTH_HEADERS,
        )
        r = await client.post(
            "/api/inventory/transfer",
            json={
                "sku_id": "SKU-ELEC-001",
                "from_node": "STOR_A_0_0",
                "to_node": "STOR_B_0_0",
                "quantity": 20,
            },
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["from"] == "STOR_A_0_0"
        assert data["to"] == "STOR_B_0_0"
        assert data["quantity"] == 20

    async def test_transfer_insufficient(self, client):
        r = await client.post(
            "/api/inventory/transfer",
            json={
                "sku_id": "SKU-ELEC-001",
                "from_node": "EMPTY_NODE",
                "to_node": "STOR_B_0_0",
                "quantity": 999,
            },
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 400


class TestCycleCountEndpoint:
    async def test_cycle_count(self, client):
        await client.post(
            "/api/inventory/receive",
            json={"sku_id": "SKU-ELEC-001", "node_name": "STOR_A_0_0", "quantity": 50},
            headers=AUTH_HEADERS,
        )
        r = await client.post(
            "/api/inventory/cycle-count",
            json={
                "node_name": "STOR_A_0_0",
                "counts": {"SKU-ELEC-001": 45},
            },
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["items_counted"] == 1
        assert data["discrepancies"] == 1
        assert data["details"][0]["expected"] == 50
        assert data["details"][0]["actual"] == 45
        assert data["details"][0]["delta"] == -5


# ==========================================================
# MOVEMENT LOG ENDPOINT
# ==========================================================


class TestMovementEndpoint:
    async def test_movements_empty(self, client):
        r = await client.get("/api/inventory/movements")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    async def test_movements_after_operations(self, client):
        await client.post(
            "/api/inventory/receive",
            json={"sku_id": "SKU-ELEC-001", "node_name": "STOR_A_0_0", "quantity": 50},
            headers=AUTH_HEADERS,
        )
        r = await client.get("/api/inventory/movements")
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 1
        assert data[0]["type"] == "receive"
        assert data[0]["sku_id"] == "SKU-ELEC-001"

    async def test_movements_filtered_by_sku(self, client):
        await client.post(
            "/api/inventory/receive",
            json={"sku_id": "SKU-ELEC-001", "node_name": "STOR_A_0_0", "quantity": 10},
            headers=AUTH_HEADERS,
        )
        await client.post(
            "/api/inventory/receive",
            json={"sku_id": "SKU-CLOTH-001", "node_name": "STOR_A_0_0", "quantity": 20},
            headers=AUTH_HEADERS,
        )
        r = await client.get("/api/inventory/movements", params={"sku_id": "SKU-ELEC-001"})
        assert r.status_code == 200
        data = r.json()
        assert all(m["sku_id"] == "SKU-ELEC-001" for m in data)


# ==========================================================
# REPLENISHMENT ENDPOINTS
# ==========================================================


class TestReplenishmentEndpoints:
    async def test_get_replenishment_empty(self, client):
        r = await client.get("/api/inventory/replenishment")
        assert r.status_code == 200
        data = r.json()
        assert "pending" in data
        assert "all" in data
        assert isinstance(data["pending"], list)

    async def test_check_replenishment(self, client):
        """All SKUs at zero stock means generates 8 replenishment orders."""
        r = await client.post("/api/inventory/replenishment/check", headers=AUTH_HEADERS)
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 8
        assert data["total_pending"] == 8
        assert len(data["new_orders"]) == 8

    async def test_no_duplicate_replenishment(self, client):
        """Second check should not create duplicates."""
        await client.post("/api/inventory/replenishment/check", headers=AUTH_HEADERS)
        r = await client.post("/api/inventory/replenishment/check", headers=AUTH_HEADERS)
        assert r.status_code == 200
        assert r.json()["count"] == 0  # No new orders

    async def test_complete_replenishment(self, client):
        r = await client.post("/api/inventory/replenishment/check", headers=AUTH_HEADERS)
        order_id = r.json()["new_orders"][0]["order_id"]

        r = await client.post(
            f"/api/inventory/replenishment/{order_id}/complete",
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["receive_result"]["ok"] is True

    async def test_cancel_replenishment(self, client):
        r = await client.post("/api/inventory/replenishment/check", headers=AUTH_HEADERS)
        order_id = r.json()["new_orders"][1]["order_id"]

        r = await client.post(
            f"/api/inventory/replenishment/{order_id}/cancel",
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True

    async def test_complete_nonexistent_order(self, client):
        r = await client.post(
            "/api/inventory/replenishment/FAKE-ORDER/complete",
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 404

    async def test_cancel_nonexistent_order(self, client):
        r = await client.post(
            "/api/inventory/replenishment/FAKE-ORDER/cancel",
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 404

    async def test_replenishment_check_works_in_sim_mode(self, client):
        """Auth skipped in simulation mode."""
        r = await client.post("/api/inventory/replenishment/check")
        assert r.status_code == 200


# ==========================================================
# OPTIMIZER ENDPOINTS
# ==========================================================


class TestOptimizerEndpoints:
    async def test_abc_analysis_empty(self, client):
        r = await client.get("/api/inventory/optimizer/abc")
        assert r.status_code == 200
        data = r.json()
        assert "A" in data
        assert "B" in data
        assert "C" in data

    async def test_recommendations_empty(self, client):
        r = await client.get("/api/inventory/optimizer/recommendations")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    async def test_zone_balance_empty(self, client):
        r = await client.get("/api/inventory/optimizer/zone-balance")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)


# ==========================================================
# STATS ENDPOINT
# ==========================================================


class TestStatsEndpoint:
    async def test_stats(self, client):
        r = await client.get("/api/inventory/stats")
        assert r.status_code == 200
        data = r.json()
        assert "inventory" in data
        assert "replenishment" in data
        assert "optimizer" in data
        assert data["inventory"]["total_skus"] == 8
        assert data["inventory"]["active_locations"] == 0
        assert data["inventory"]["total_units"] == 0
        assert data["replenishment"]["total_orders"] == 0

    async def test_stats_after_operations(self, client):
        await client.post(
            "/api/inventory/receive",
            json={"sku_id": "SKU-ELEC-001", "node_name": "STOR_A_0_0", "quantity": 50},
            headers=AUTH_HEADERS,
        )
        r = await client.get("/api/inventory/stats")
        assert r.status_code == 200
        data = r.json()
        assert data["inventory"]["active_locations"] == 1
        assert data["inventory"]["total_units"] == 50
        assert data["inventory"]["total_movements"] == 1


# ==========================================================
# PYDANTIC 422 REJECTION TESTS
# ==========================================================


class TestPydanticValidation:
    async def test_receive_negative_quantity_422(self, client):
        """Pydantic rejects quantity <= 0 with 422."""
        r = await client.post(
            "/api/inventory/receive",
            json={"sku_id": "SKU-ELEC-001", "node_name": "STOR_A_0_0", "quantity": -5},
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 422

    async def test_receive_missing_sku_id_422(self, client):
        """Pydantic rejects missing required field with 422."""
        r = await client.post(
            "/api/inventory/receive",
            json={"node_name": "STOR_A_0_0", "quantity": 10},
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 422

    async def test_transfer_zero_quantity_422(self, client):
        """Pydantic rejects quantity=0 on transfer with 422."""
        r = await client.post(
            "/api/inventory/transfer",
            json={
                "sku_id": "SKU-ELEC-001",
                "from_node": "STOR_A_0_0",
                "to_node": "STOR_B_0_0",
                "quantity": 0,
            },
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 422


# ==========================================================
# AUTH GUARD SIM-MODE TESTS (pick, adjust, transfer)
# ==========================================================


class TestAuthGuardSimMode:
    async def test_pick_works_in_sim_mode(self, client):
        """Pick endpoint works without auth header in simulation mode."""
        await client.post(
            "/api/inventory/receive",
            json={"sku_id": "SKU-ELEC-001", "node_name": "STOR_A_0_0", "quantity": 50},
        )
        r = await client.post(
            "/api/inventory/pick",
            json={"sku_id": "SKU-ELEC-001", "node_name": "STOR_A_0_0", "quantity": 5},
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True

    async def test_adjust_works_in_sim_mode(self, client):
        """Adjust endpoint works without auth header in simulation mode."""
        r = await client.post(
            "/api/inventory/adjust",
            json={
                "sku_id": "SKU-ELEC-001",
                "node_name": "STOR_A_0_0",
                "new_quantity": 10,
                "reason": "test",
            },
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True

    async def test_transfer_works_in_sim_mode(self, client):
        """Transfer endpoint works without auth header in simulation mode."""
        await client.post(
            "/api/inventory/receive",
            json={"sku_id": "SKU-ELEC-001", "node_name": "STOR_A_0_0", "quantity": 50},
        )
        r = await client.post(
            "/api/inventory/transfer",
            json={
                "sku_id": "SKU-ELEC-001",
                "from_node": "STOR_A_0_0",
                "to_node": "STOR_B_0_0",
                "quantity": 10,
            },
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True

    async def test_cycle_count_works_in_sim_mode(self, client):
        """Cycle-count endpoint works without auth header in simulation mode."""
        r = await client.post(
            "/api/inventory/cycle-count",
            json={"node_name": "STOR_A_0_0", "counts": {"SKU-ELEC-001": 10}},
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True

    async def test_complete_replenishment_works_in_sim_mode(self, client):
        """Complete-replenishment endpoint works without auth header in simulation mode."""
        r = await client.post("/api/inventory/replenishment/check")
        order_id = r.json()["new_orders"][0]["order_id"]
        r = await client.post(f"/api/inventory/replenishment/{order_id}/complete")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    async def test_cancel_replenishment_works_in_sim_mode(self, client):
        """Cancel-replenishment endpoint works without auth header in simulation mode."""
        r = await client.post("/api/inventory/replenishment/check")
        order_id = r.json()["new_orders"][1]["order_id"]
        r = await client.post(f"/api/inventory/replenishment/{order_id}/cancel")
        assert r.status_code == 200
        assert r.json()["ok"] is True


# ==========================================================
# MOVEMENT LIMIT CLAMPING TEST
# ==========================================================


class TestMovementLimitClamping:
    async def test_negative_limit_clamped_to_1(self, client):
        """Negative limit query param is clamped to 1, not rejected."""
        await client.post(
            "/api/inventory/receive",
            json={"sku_id": "SKU-ELEC-001", "node_name": "STOR_A_0_0", "quantity": 10},
            headers=AUTH_HEADERS,
        )
        await client.post(
            "/api/inventory/receive",
            json={"sku_id": "SKU-CLOTH-001", "node_name": "STOR_A_0_0", "quantity": 5},
            headers=AUTH_HEADERS,
        )
        r = await client.get("/api/inventory/movements", params={"limit": -5})
        assert r.status_code == 200
        data = r.json()
        # Clamped to 1, so at most 1 result
        assert len(data) == 1

    async def test_zero_limit_clamped_to_1(self, client):
        """Zero limit clamped to 1."""
        await client.post(
            "/api/inventory/receive",
            json={"sku_id": "SKU-ELEC-001", "node_name": "STOR_A_0_0", "quantity": 10},
            headers=AUTH_HEADERS,
        )
        r = await client.get("/api/inventory/movements", params={"limit": 0})
        assert r.status_code == 200
        assert len(r.json()) == 1


# ==========================================================
# ROUTE ORDERING TESTS
# ==========================================================


class TestRouteOrdering:
    """Verify fixed paths are reachable and not captured by parameterized paths."""

    async def test_stock_levels_not_captured_by_stock_node(self, client):
        """GET /api/inventory/stock-levels must NOT be captured by /stock/{node_name}."""
        r = await client.get("/api/inventory/stock-levels")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 8  # Returns stock level objects, not node stock

    async def test_replenishment_check_not_captured_by_order_id(self, client):
        """POST /api/inventory/replenishment/check must NOT be captured by /{order_id}/complete."""
        r = await client.post("/api/inventory/replenishment/check", headers=AUTH_HEADERS)
        assert r.status_code == 200
        assert "count" in r.json()

    async def test_optimizer_abc_reachable(self, client):
        """GET /api/inventory/optimizer/abc is reachable."""
        r = await client.get("/api/inventory/optimizer/abc")
        assert r.status_code == 200
        assert "A" in r.json()

    async def test_optimizer_recommendations_reachable(self, client):
        r = await client.get("/api/inventory/optimizer/recommendations")
        assert r.status_code == 200

    async def test_optimizer_zone_balance_reachable(self, client):
        r = await client.get("/api/inventory/optimizer/zone-balance")
        assert r.status_code == 200


# ==========================================================
# END-TO-END API FLOW
# ==========================================================


class TestEndToEndAPI:
    async def test_receive_pick_replenish_flow(self, client):
        """Full API flow: receive, pick, stock drops, replenishment, complete."""
        # 1. Receive 60 (above reorder point of 50)
        r = await client.post(
            "/api/inventory/receive",
            json={"sku_id": "SKU-ELEC-001", "node_name": "STOR_A_0_0", "quantity": 60},
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 200
        assert r.json()["new_quantity"] == 60

        # 2. Check stock level
        r = await client.get("/api/inventory/stock-levels")
        headphones = next(item for item in r.json() if item["sku_id"] == "SKU-ELEC-001")
        assert headphones["total_stock"] == 60
        assert headphones["status"] == "ok"

        # 3. Pick 25 (60-25=35, below reorder point of 50)
        r = await client.post(
            "/api/inventory/pick",
            json={"sku_id": "SKU-ELEC-001", "node_name": "STOR_A_0_0", "quantity": 25},
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 200
        assert r.json()["remaining"] == 35

        # 4. Generate replenishment orders
        r = await client.post("/api/inventory/replenishment/check", headers=AUTH_HEADERS)
        assert r.status_code == 200
        new_orders = r.json()["new_orders"]
        elec_orders = [o for o in new_orders if o["sku_id"] == "SKU-ELEC-001"]
        assert len(elec_orders) == 1
        order_id = elec_orders[0]["order_id"]

        # 5. Complete replenishment
        r = await client.post(
            f"/api/inventory/replenishment/{order_id}/complete",
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True

        # 6. Verify stock restored
        r = await client.get("/api/inventory/skus/SKU-ELEC-001")
        assert r.json()["total_stock"] == 135  # 35 + 100 (reorder_qty)

        # 7. Check movements
        r = await client.get("/api/inventory/movements", params={"sku_id": "SKU-ELEC-001"})
        assert r.status_code == 200
        types = [m["type"] for m in r.json()]
        assert "receive" in types
        assert "pick" in types

        # 8. Check stats
        r = await client.get("/api/inventory/stats")
        assert r.status_code == 200
        assert r.json()["inventory"]["total_movements"] >= 3

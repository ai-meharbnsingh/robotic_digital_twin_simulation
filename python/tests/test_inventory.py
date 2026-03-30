"""
Inventory Management Tests — InventoryManager, ReplenishmentEngine, StorageOptimizer.

Phase 14: 60+ tests covering all inventory components.
Tests actual logic with real values from sku_catalog.yaml — no 'is not None' assertions.
"""

import os
import sys
import time
import yaml
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from wms.inventory_manager import (
    InventoryManager,
    SKU,
    StockLocation,
    StorageClass,
    MovementType,
)
from wms.replenishment import ReplenishmentEngine, ReplenishOrder
from wms.storage_optimizer import StorageOptimizer


# ── Load real config ────────────────────────────────────

CONFIG_PATH = os.path.join(ROOT, "..", "configs", "wms", "sku_catalog.yaml")


@pytest.fixture
def sku_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


@pytest.fixture
def manager(sku_config):
    mgr = InventoryManager()
    mgr.load_catalog(sku_config)
    return mgr


@pytest.fixture
def replenishment(manager):
    return ReplenishmentEngine(manager, default_source="Staging")


@pytest.fixture
def optimizer(manager):
    return StorageOptimizer(
        inventory=manager,
        pick_nodes=["PICK_0", "PICK_1"],
        node_positions={
            "PICK_0": {"x": 0, "y": 0, "zone": "Pick"},
            "PICK_1": {"x": 5, "y": 0, "zone": "Pick"},
            "STOR_A_0_0": {"x": 20, "y": 10, "zone": "Storage_A"},
            "STOR_A_1_0": {"x": 25, "y": 10, "zone": "Storage_A"},
            "STOR_B_0_0": {"x": 20, "y": 30, "zone": "Storage_B"},
        },
    )


# ══════════════════════════════════════════════════════════
# SKU CATALOG TESTS
# ══════════════════════════════════════════════════════════


class TestSKUCatalog:
    def test_loads_all_skus(self, manager):
        skus = manager.get_all_skus()
        assert len(skus) == 8, f"Expected 8 SKUs, got {len(skus)}"

    def test_sku_ids_match_config(self, manager):
        expected = {
            "SKU-ELEC-001", "SKU-ELEC-002", "SKU-ELEC-003",
            "SKU-CLOTH-001", "SKU-FOOD-001",
            "SKU-IND-001", "SKU-IND-002",
            "SKU-HOUSE-001",
        }
        actual = {s["sku_id"] for s in manager.get_all_skus()}
        assert actual == expected

    def test_sku_fields(self, manager):
        sku = manager.get_sku("SKU-ELEC-001")
        assert sku is not None
        assert sku["name"] == "Wireless Headphones"
        assert sku["category"] == "electronics"
        assert sku["storage_class"] == "standard"
        assert sku["weight_kg"] == 0.3
        assert sku["dimensions_cm"]["length"] == 20
        assert sku["dimensions_cm"]["width"] == 15
        assert sku["dimensions_cm"]["height"] == 8
        assert sku["min_stock"] == 20
        assert sku["max_stock"] == 200
        assert sku["reorder_point"] == 50
        assert sku["reorder_qty"] == 100

    def test_sku_storage_classes(self, manager):
        assert manager.get_sku("SKU-FOOD-001")["storage_class"] == "cold"
        assert manager.get_sku("SKU-IND-001")["storage_class"] == "hazmat"
        assert manager.get_sku("SKU-HOUSE-001")["storage_class"] == "fragile"
        assert manager.get_sku("SKU-IND-002")["storage_class"] == "heavy"
        assert manager.get_sku("SKU-ELEC-003")["storage_class"] == "high_value"

    def test_sku_not_found(self, manager):
        assert manager.get_sku("NONEXISTENT") is None

    def test_cold_storage_protein_bars(self, manager):
        sku = manager.get_sku("SKU-FOOD-001")
        assert sku["name"] == "Protein Bars (Box)"
        assert sku["weight_kg"] == 2.0
        assert sku["min_stock"] == 10
        assert sku["reorder_point"] == 25
        assert sku["reorder_qty"] == 50


# ══════════════════════════════════════════════════════════
# PUTAWAY RULES TESTS
# ══════════════════════════════════════════════════════════


class TestPutawayRules:
    def test_putaway_rule_count(self, manager):
        rules = manager.get_putaway_rules()
        assert len(rules) == 5

    def test_electronics_zone(self, manager):
        zone = manager.get_putaway_zone("SKU-ELEC-001")
        assert zone == "Storage_A"

    def test_clothing_zone(self, manager):
        zone = manager.get_putaway_zone("SKU-CLOTH-001")
        assert zone == "Storage_A"

    def test_food_zone(self, manager):
        zone = manager.get_putaway_zone("SKU-FOOD-001")
        assert zone == "Storage_B"

    def test_industrial_zone(self, manager):
        zone = manager.get_putaway_zone("SKU-IND-001")
        assert zone == "Storage_B"

    def test_household_zone(self, manager):
        zone = manager.get_putaway_zone("SKU-HOUSE-001")
        assert zone == "Storage_A"

    def test_unknown_sku_zone(self, manager):
        zone = manager.get_putaway_zone("FAKE-SKU")
        assert zone is None


# ══════════════════════════════════════════════════════════
# RECEIVE TESTS
# ══════════════════════════════════════════════════════════


class TestReceive:
    def test_receive_creates_location(self, manager):
        result = manager.receive("SKU-ELEC-001", "STOR_A_0_0", 50)
        assert result["ok"] is True
        assert result["sku_id"] == "SKU-ELEC-001"
        assert result["node"] == "STOR_A_0_0"
        assert result["new_quantity"] == 50

    def test_receive_adds_to_existing(self, manager):
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 30)
        result = manager.receive("SKU-ELEC-001", "STOR_A_0_0", 20)
        assert result["ok"] is True
        assert result["new_quantity"] == 50

    def test_receive_unknown_sku(self, manager):
        result = manager.receive("FAKE-SKU", "STOR_A_0_0", 10)
        assert result["ok"] is False
        assert "not in catalog" in result["error"]

    def test_receive_zero_quantity(self, manager):
        result = manager.receive("SKU-ELEC-001", "STOR_A_0_0", 0)
        assert result["ok"] is False
        assert "positive" in result["error"]

    def test_receive_negative_quantity(self, manager):
        result = manager.receive("SKU-ELEC-001", "STOR_A_0_0", -5)
        assert result["ok"] is False
        assert "positive" in result["error"]

    def test_receive_logs_movement(self, manager):
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 25)
        movements = manager.get_movements()
        assert len(movements) == 1
        assert movements[0]["type"] == "receive"
        assert movements[0]["sku_id"] == "SKU-ELEC-001"
        assert movements[0]["quantity"] == 25


# ══════════════════════════════════════════════════════════
# PICK TESTS
# ══════════════════════════════════════════════════════════


class TestPick:
    def test_pick_reduces_stock(self, manager):
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 50)
        result = manager.pick("SKU-ELEC-001", "STOR_A_0_0", 10)
        assert result["ok"] is True
        assert result["picked"] == 10
        assert result["remaining"] == 40

    def test_pick_all(self, manager):
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 20)
        result = manager.pick("SKU-ELEC-001", "STOR_A_0_0", 20)
        assert result["ok"] is True
        assert result["remaining"] == 0

    def test_pick_insufficient_stock(self, manager):
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 5)
        result = manager.pick("SKU-ELEC-001", "STOR_A_0_0", 10)
        assert result["ok"] is False
        assert "insufficient stock" in result["error"]
        assert "have=5" in result["error"]
        assert "need=10" in result["error"]

    def test_pick_from_empty_location(self, manager):
        result = manager.pick("SKU-ELEC-001", "STOR_EMPTY", 1)
        assert result["ok"] is False
        assert "insufficient stock" in result["error"]

    def test_pick_zero_quantity(self, manager):
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 50)
        result = manager.pick("SKU-ELEC-001", "STOR_A_0_0", 0)
        assert result["ok"] is False
        assert "positive" in result["error"]

    def test_pick_logs_negative_movement(self, manager):
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 50)
        manager.pick("SKU-ELEC-001", "STOR_A_0_0", 15)
        movements = manager.get_movements(sku_id="SKU-ELEC-001")
        pick_mvt = [m for m in movements if m["type"] == "pick"]
        assert len(pick_mvt) == 1
        assert pick_mvt[0]["quantity"] == -15


# ══════════════════════════════════════════════════════════
# ADJUST TESTS
# ══════════════════════════════════════════════════════════


class TestAdjust:
    def test_adjust_up(self, manager):
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 30)
        result = manager.adjust("SKU-ELEC-001", "STOR_A_0_0", 50, "found extra")
        assert result["ok"] is True
        assert result["old_quantity"] == 30
        assert result["new_quantity"] == 50
        assert result["delta"] == 20

    def test_adjust_down(self, manager):
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 30)
        result = manager.adjust("SKU-ELEC-001", "STOR_A_0_0", 10)
        assert result["ok"] is True
        assert result["old_quantity"] == 30
        assert result["new_quantity"] == 10
        assert result["delta"] == -20

    def test_adjust_to_zero(self, manager):
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 30)
        result = manager.adjust("SKU-ELEC-001", "STOR_A_0_0", 0)
        assert result["ok"] is True
        assert result["new_quantity"] == 0

    def test_adjust_negative_fails(self, manager):
        result = manager.adjust("SKU-ELEC-001", "STOR_A_0_0", -5)
        assert result["ok"] is False
        assert "negative" in result["error"]

    def test_adjust_creates_location_if_missing(self, manager):
        result = manager.adjust("SKU-ELEC-001", "NEW_LOC", 25)
        assert result["ok"] is True
        assert result["old_quantity"] == 0
        assert result["new_quantity"] == 25


# ══════════════════════════════════════════════════════════
# TRANSFER TESTS
# ══════════════════════════════════════════════════════════


class TestTransfer:
    def test_transfer_between_nodes(self, manager):
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 50)
        result = manager.transfer("SKU-ELEC-001", "STOR_A_0_0", "STOR_B_0_0", 20)
        assert result["ok"] is True
        assert result["from"] == "STOR_A_0_0"
        assert result["to"] == "STOR_B_0_0"
        assert result["quantity"] == 20
        # Verify balances
        assert manager.get_total_stock("SKU-ELEC-001") == 50  # Total unchanged

    def test_transfer_insufficient(self, manager):
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 10)
        result = manager.transfer("SKU-ELEC-001", "STOR_A_0_0", "STOR_B_0_0", 20)
        assert result["ok"] is False
        assert "insufficient stock" in result["error"]

    def test_transfer_zero_quantity(self, manager):
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 50)
        result = manager.transfer("SKU-ELEC-001", "STOR_A_0_0", "STOR_B_0_0", 0)
        assert result["ok"] is False
        assert "positive" in result["error"]

    def test_transfer_logs_two_movements(self, manager):
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 50)
        manager.transfer("SKU-ELEC-001", "STOR_A_0_0", "STOR_B_0_0", 15)
        movements = manager.get_movements()
        transfer_mvts = [m for m in movements if m["type"] == "transfer"]
        assert len(transfer_mvts) == 2  # One debit, one credit


# ══════════════════════════════════════════════════════════
# STOCK QUERY TESTS
# ══════════════════════════════════════════════════════════


class TestStockQueries:
    def test_stock_at_node(self, manager):
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 30)
        manager.receive("SKU-CLOTH-001", "STOR_A_0_0", 20)
        stock = manager.get_stock_at_node("STOR_A_0_0")
        assert len(stock) == 2
        skus = {s["sku_id"] for s in stock}
        assert skus == {"SKU-ELEC-001", "SKU-CLOTH-001"}

    def test_stock_for_sku(self, manager):
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 30)
        manager.receive("SKU-ELEC-001", "STOR_B_0_0", 20)
        locations = manager.get_stock_for_sku("SKU-ELEC-001")
        assert len(locations) == 2
        nodes = {l["node_name"] for l in locations}
        assert nodes == {"STOR_A_0_0", "STOR_B_0_0"}

    def test_total_stock_across_locations(self, manager):
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 30)
        manager.receive("SKU-ELEC-001", "STOR_B_0_0", 20)
        total = manager.get_total_stock("SKU-ELEC-001")
        assert total == 50

    def test_total_stock_zero_for_unknown(self, manager):
        assert manager.get_total_stock("NONEXISTENT") == 0

    def test_stock_levels_all_skus(self, manager):
        levels = manager.get_stock_levels()
        assert len(levels) == 8  # All 8 SKUs from catalog
        # All are at 0 stock
        for level in levels:
            assert level["total_stock"] == 0
            assert level["below_reorder"] is True
            assert level["below_min"] is True
            assert level["status"] == "critical"

    def test_stock_level_ok_status(self, manager):
        # Receive enough to be above reorder point for headphones (reorder=50, max=200)
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 60)
        levels = manager.get_stock_levels()
        headphones = next(l for l in levels if l["sku_id"] == "SKU-ELEC-001")
        assert headphones["total_stock"] == 60
        assert headphones["below_reorder"] is False
        assert headphones["below_min"] is False
        assert headphones["above_max"] is False
        assert headphones["status"] == "ok"

    def test_stock_level_low_status(self, manager):
        # Between min (20) and reorder (50)
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 30)
        levels = manager.get_stock_levels()
        headphones = next(l for l in levels if l["sku_id"] == "SKU-ELEC-001")
        assert headphones["status"] == "low"

    def test_stock_level_overstocked(self, manager):
        # Above max (200)
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 250)
        levels = manager.get_stock_levels()
        headphones = next(l for l in levels if l["sku_id"] == "SKU-ELEC-001")
        assert headphones["above_max"] is True
        assert headphones["status"] == "overstocked"

    def test_items_below_reorder(self, manager):
        # No stock at all — all 8 below reorder
        below = manager.get_items_below_reorder()
        assert len(below) == 8

    def test_items_below_reorder_after_stocking(self, manager):
        # Stock up headphones above reorder point (50)
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 60)
        below = manager.get_items_below_reorder()
        assert len(below) == 7  # 8 - 1 stocked above reorder
        sku_ids = {b["sku_id"] for b in below}
        assert "SKU-ELEC-001" not in sku_ids


# ══════════════════════════════════════════════════════════
# CYCLE COUNT TESTS
# ══════════════════════════════════════════════════════════


class TestCycleCount:
    def test_cycle_count_no_discrepancy(self, manager):
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 50)
        result = manager.cycle_count("STOR_A_0_0", {"SKU-ELEC-001": 50})
        assert result["ok"] is True
        assert result["items_counted"] == 1
        assert result["discrepancies"] == 0
        assert result["details"] == []

    def test_cycle_count_with_discrepancy(self, manager):
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 50)
        result = manager.cycle_count("STOR_A_0_0", {"SKU-ELEC-001": 45})
        assert result["ok"] is True
        assert result["discrepancies"] == 1
        assert result["details"][0]["expected"] == 50
        assert result["details"][0]["actual"] == 45
        assert result["details"][0]["delta"] == -5
        # Auto-adjust should set new quantity
        total = manager.get_total_stock("SKU-ELEC-001")
        assert total == 45

    def test_cycle_count_multiple_skus(self, manager):
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 50)
        manager.receive("SKU-CLOTH-001", "STOR_A_0_0", 30)
        result = manager.cycle_count("STOR_A_0_0", {
            "SKU-ELEC-001": 48,
            "SKU-CLOTH-001": 30,
        })
        assert result["items_counted"] == 2
        assert result["discrepancies"] == 1
        assert result["details"][0]["sku_id"] == "SKU-ELEC-001"

    def test_cycle_count_new_sku_at_node(self, manager):
        # Count an SKU that wasn't previously tracked at this node
        result = manager.cycle_count("STOR_A_0_0", {"SKU-FOOD-001": 5})
        assert result["discrepancies"] == 1
        assert result["details"][0]["expected"] == 0
        assert result["details"][0]["actual"] == 5
        assert manager.get_total_stock("SKU-FOOD-001") == 5


# ══════════════════════════════════════════════════════════
# MOVEMENT LOG TESTS
# ══════════════════════════════════════════════════════════


class TestMovementLog:
    def test_movements_empty_initially(self, manager):
        assert manager.get_movements() == []

    def test_movements_limited(self, manager):
        for i in range(10):
            manager.receive("SKU-ELEC-001", "STOR_A_0_0", 1)
        movements = manager.get_movements(limit=5)
        assert len(movements) == 5

    def test_movements_filtered_by_sku(self, manager):
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 10)
        manager.receive("SKU-CLOTH-001", "STOR_A_0_0", 20)
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 30)
        movements = manager.get_movements(sku_id="SKU-ELEC-001")
        assert len(movements) == 2
        assert all(m["sku_id"] == "SKU-ELEC-001" for m in movements)

    def test_movements_bounded_at_max(self, manager):
        original_max = manager._max_movements
        manager._max_movements = 10
        try:
            for i in range(15):
                manager.receive("SKU-ELEC-001", "STOR_A_0_0", 1)
            movements = manager.get_movements(limit=100)
            assert len(movements) == 10
        finally:
            manager._max_movements = original_max

    def test_movement_has_movement_id(self, manager):
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 10)
        movements = manager.get_movements()
        assert len(movements[0]["movement_id"]) == 12


# ══════════════════════════════════════════════════════════
# REPLENISHMENT TESTS
# ══════════════════════════════════════════════════════════


class TestReplenishment:
    def test_check_generates_orders_when_below_reorder(self, manager, replenishment):
        # All SKUs at zero → all below reorder → all get orders
        orders = replenishment.check_and_generate()
        assert len(orders) == 8  # All 8 SKUs need replenishment

    def test_no_duplicate_pending(self, manager, replenishment):
        # First check generates orders
        orders1 = replenishment.check_and_generate()
        assert len(orders1) == 8
        # Second check should skip — already pending
        orders2 = replenishment.check_and_generate()
        assert len(orders2) == 0

    def test_order_has_correct_fields(self, manager, replenishment):
        orders = replenishment.check_and_generate()
        elec_order = next(o for o in orders if o["sku_id"] == "SKU-ELEC-001")
        assert elec_order["quantity"] == 100  # reorder_qty from config
        assert elec_order["source_zone"] == "Staging"
        assert elec_order["status"] == "pending"
        assert "order_id" in elec_order
        assert len(elec_order["order_id"]) == 12

    def test_critical_gets_high_priority(self, manager, replenishment):
        # All SKUs at zero → below_min → priority=10
        orders = replenishment.check_and_generate()
        for order in orders:
            assert order["priority"] == 10  # All are critical (below_min)

    def test_low_gets_normal_priority(self, manager, replenishment):
        # Stock headphones between min(20) and reorder(50) → below_reorder but not below_min
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 30)
        orders = replenishment.check_and_generate()
        elec_order = next(o for o in orders if o["sku_id"] == "SKU-ELEC-001")
        assert elec_order["priority"] == 5  # Low, not critical

    def test_complete_order_receives_inventory(self, manager, replenishment):
        orders = replenishment.check_and_generate()
        elec_order = next(o for o in orders if o["sku_id"] == "SKU-ELEC-001")
        order_id = elec_order["order_id"]

        result = replenishment.complete_order(order_id)
        assert result["ok"] is True
        assert result["receive_result"]["ok"] is True
        # Inventory should increase by reorder_qty (100)
        total = manager.get_total_stock("SKU-ELEC-001")
        assert total == 100

    def test_cancel_order(self, manager, replenishment):
        orders = replenishment.check_and_generate()
        order_id = orders[0]["order_id"]

        result = replenishment.cancel_order(order_id)
        assert result["ok"] is True
        pending = replenishment.get_pending()
        assert all(o["order_id"] != order_id for o in pending)

    def test_complete_nonexistent_order(self, replenishment):
        result = replenishment.complete_order("FAKE-ORDER")
        assert result["ok"] is False
        assert "not found" in result["error"]

    def test_cancel_nonexistent_order(self, replenishment):
        result = replenishment.cancel_order("FAKE-ORDER")
        assert result["ok"] is False
        assert "not found" in result["error"]

    def test_complete_already_completed(self, manager, replenishment):
        orders = replenishment.check_and_generate()
        order_id = orders[0]["order_id"]
        replenishment.complete_order(order_id)
        result = replenishment.complete_order(order_id)
        assert result["ok"] is False
        assert "not pending" in result["error"]

    def test_cancel_already_cancelled(self, manager, replenishment):
        orders = replenishment.check_and_generate()
        order_id = orders[0]["order_id"]
        replenishment.cancel_order(order_id)
        result = replenishment.cancel_order(order_id)
        assert result["ok"] is False
        assert "not pending" in result["error"]

    def test_get_all_orders(self, manager, replenishment):
        replenishment.check_and_generate()
        all_orders = replenishment.get_all()
        assert len(all_orders) == 8

    def test_get_pending_orders(self, manager, replenishment):
        replenishment.check_and_generate()
        pending = replenishment.get_pending()
        assert len(pending) == 8
        assert all(o["status"] == "pending" for o in pending)

    def test_replenishment_stats(self, manager, replenishment):
        orders = replenishment.check_and_generate()
        order_id = orders[0]["order_id"]
        replenishment.complete_order(order_id)

        stats = replenishment.get_stats()
        assert stats["total_orders"] == 8
        assert stats["pending"] == 7
        assert stats["completed"] == 1
        assert stats["cancelled"] == 0

    def test_max_orders_trimming(self, manager, replenishment):
        """Verify _max_orders cap prunes old non-pending orders while keeping all pending.

        Trimming logic: when total orders > _max_orders, keep all pending +
        last 100 non-pending. We inject 105 completed orders so that 5 get
        pruned when check_and_generate triggers the trim.
        """
        replenishment._max_orders = 50  # Low enough to trigger trim

        # Manually inject 105 completed orders
        for i in range(105):
            order = ReplenishOrder(
                sku_id=f"SKU-FAKE-{i:03d}",
                quantity=10,
                source_zone="Staging",
                target_node="STOR_A_0_0",
                priority=5,
            )
            order.complete()
            replenishment._orders.append(order)

        assert len(replenishment._orders) == 105

        # Generate pending orders -- triggers trim because 105 + 8 = 113 > 50
        orders = replenishment.check_and_generate()
        assert len(orders) == 8

        all_orders = replenishment.get_all()
        pending = replenishment.get_pending()
        completed = [o for o in all_orders if o["status"] == "completed"]

        # All 8 pending orders preserved
        assert len(pending) == 8
        # Only last 100 completed orders kept (5 oldest pruned)
        assert len(completed) == 100
        # Total = 8 pending + 100 completed
        assert len(all_orders) == 108


# ══════════════════════════════════════════════════════════
# RECEIVE ABOVE MAX_STOCK TEST
# ══════════════════════════════════════════════════════════


class TestReceiveAboveMaxStock:
    def test_receive_above_max_stock_status(self, manager):
        """Receiving inventory above max_stock results in 'overstocked' status."""
        # SKU-ELEC-001 max_stock=200
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 250)
        levels = manager.get_stock_levels()
        headphones = next(l for l in levels if l["sku_id"] == "SKU-ELEC-001")
        assert headphones["total_stock"] == 250
        assert headphones["above_max"] is True
        assert headphones["status"] == "overstocked"

    def test_receive_incrementally_above_max(self, manager):
        """Multiple receives that push total above max_stock."""
        # max_stock=200 for SKU-ELEC-001
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 150)
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 100)  # total=250, above max=200
        total = manager.get_total_stock("SKU-ELEC-001")
        assert total == 250
        levels = manager.get_stock_levels()
        headphones = next(l for l in levels if l["sku_id"] == "SKU-ELEC-001")
        assert headphones["status"] == "overstocked"


# ══════════════════════════════════════════════════════════
# STORAGE OPTIMIZER TESTS
# ══════════════════════════════════════════════════════════


class TestStorageOptimizer:
    def test_abc_empty_no_picks(self, optimizer):
        abc = optimizer.abc_analysis()
        assert abc["A"] == []
        assert abc["B"] == []
        assert abc["C"] == []

    def test_abc_with_picks(self, optimizer):
        # Simulate picks: SKU-ELEC-001 is fast, SKU-IND-002 is slow
        for _ in range(100):
            optimizer.record_pick("SKU-ELEC-001")
        for _ in range(50):
            optimizer.record_pick("SKU-CLOTH-001")
        for _ in range(10):
            optimizer.record_pick("SKU-IND-002")
        for _ in range(5):
            optimizer.record_pick("SKU-FOOD-001")
        for _ in range(3):
            optimizer.record_pick("SKU-HOUSE-001")

        abc = optimizer.abc_analysis()
        # A = top 20% (1 SKU of 5)
        assert len(abc["A"]) == 1
        assert abc["A"][0]["sku_id"] == "SKU-ELEC-001"
        assert abc["A"][0]["pick_count"] == 100

    def test_recommendations_for_far_a_class(self, manager, optimizer):
        # Stock SKU-ELEC-001 at a far node
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 50)
        # Record picks to make it A-class
        for _ in range(100):
            optimizer.record_pick("SKU-ELEC-001")

        recs = optimizer.get_recommendations()
        # STOR_A_0_0 is 22.36m from PICK_0 (sqrt(20^2+10^2)), > 10m threshold
        assert len(recs) >= 1
        assert recs[0]["type"] == "move_closer"
        assert recs[0]["sku_id"] == "SKU-ELEC-001"
        assert recs[0]["distance_to_pick_m"] > 10.0

    def test_recommendations_empty_no_picks(self, optimizer):
        recs = optimizer.get_recommendations()
        assert recs == []

    def test_zone_balance_empty(self, optimizer):
        balance = optimizer.get_zone_balance()
        assert balance == {}

    def test_zone_balance_with_stock(self, manager, optimizer):
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 30)
        manager.receive("SKU-CLOTH-001", "STOR_A_1_0", 20)
        manager.receive("SKU-FOOD-001", "STOR_B_0_0", 40)

        balance = optimizer.get_zone_balance()
        assert "Storage_A" in balance
        assert "Storage_B" in balance
        assert balance["Storage_A"]["total_units"] == 50
        assert balance["Storage_A"]["unique_skus"] == 2
        assert balance["Storage_A"]["locations"] == 2
        assert balance["Storage_B"]["total_units"] == 40
        assert balance["Storage_B"]["unique_skus"] == 1

    def test_optimizer_stats(self, optimizer):
        optimizer.record_pick("SKU-ELEC-001")
        optimizer.record_pick("SKU-ELEC-001")
        optimizer.record_pick("SKU-CLOTH-001")
        stats = optimizer.get_stats()
        assert stats["total_tracked_skus"] == 2
        assert stats["total_picks"] == 3


# ══════════════════════════════════════════════════════════
# INVENTORY MANAGER STATS
# ══════════════════════════════════════════════════════════


class TestInventoryStats:
    def test_stats_empty(self, manager):
        stats = manager.get_stats()
        assert stats["total_skus"] == 8
        assert stats["active_locations"] == 0
        assert stats["total_units"] == 0
        assert stats["below_reorder"] == 8
        assert stats["below_min"] == 8
        assert stats["above_max"] == 0
        assert stats["total_movements"] == 0

    def test_stats_after_operations(self, manager):
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 60)
        manager.receive("SKU-CLOTH-001", "STOR_A_0_0", 150)
        manager.pick("SKU-ELEC-001", "STOR_A_0_0", 5)

        stats = manager.get_stats()
        assert stats["total_skus"] == 8
        assert stats["active_locations"] == 2
        assert stats["total_units"] == 205  # 55 + 150
        assert stats["total_movements"] == 3  # 2 receives + 1 pick

    def test_stats_below_reorder_decreases(self, manager):
        # Stock one above reorder
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 60)  # reorder_point=50
        stats = manager.get_stats()
        assert stats["below_reorder"] == 7  # 8 - 1 now OK


# ══════════════════════════════════════════════════════════
# SERIALIZATION TESTS
# ══════════════════════════════════════════════════════════


class TestSerialization:
    def test_sku_to_dict(self, manager):
        sku = manager.get_sku("SKU-ELEC-001")
        assert isinstance(sku, dict)
        assert "sku_id" in sku
        assert "dimensions_cm" in sku
        assert isinstance(sku["dimensions_cm"], dict)

    def test_stock_location_to_dict(self, manager):
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 25)
        locations = manager.get_stock_for_sku("SKU-ELEC-001")
        assert len(locations) == 1
        loc = locations[0]
        assert loc["sku_id"] == "SKU-ELEC-001"
        assert loc["node_name"] == "STOR_A_0_0"
        assert loc["quantity"] == 25
        assert isinstance(loc["last_updated"], float)

    def test_replenish_order_to_dict(self, manager, replenishment):
        orders = replenishment.check_and_generate()
        order = orders[0]
        assert isinstance(order, dict)
        assert "order_id" in order
        assert "sku_id" in order
        assert "quantity" in order
        assert "source_zone" in order
        assert "target_node" in order
        assert "priority" in order
        assert "status" in order
        assert "created_at" in order


# ══════════════════════════════════════════════════════════
# END-TO-END INTEGRATION
# ══════════════════════════════════════════════════════════


class TestEndToEnd:
    def test_receive_pick_replenish_complete_cycle(self, manager, replenishment):
        """Full lifecycle: receive → pick → stock drops → replenishment → complete → stock restored."""
        # 1. Receive inventory
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 60)  # Above reorder (50)
        assert manager.get_total_stock("SKU-ELEC-001") == 60

        # 2. No replenishment needed yet
        orders = replenishment.check_and_generate()
        elec_orders = [o for o in orders if o["sku_id"] == "SKU-ELEC-001"]
        assert len(elec_orders) == 0  # Above reorder

        # 3. Pick down to below reorder
        manager.pick("SKU-ELEC-001", "STOR_A_0_0", 20)  # 60-20=40, below reorder(50)
        assert manager.get_total_stock("SKU-ELEC-001") == 40

        # 4. Replenishment check generates order
        orders = replenishment.check_and_generate()
        elec_orders = [o for o in orders if o["sku_id"] == "SKU-ELEC-001"]
        assert len(elec_orders) == 1
        assert elec_orders[0]["quantity"] == 100  # reorder_qty
        order_id = elec_orders[0]["order_id"]

        # 5. Complete replenishment → inventory restored
        result = replenishment.complete_order(order_id)
        assert result["ok"] is True
        assert manager.get_total_stock("SKU-ELEC-001") == 140  # 40 + 100

        # 6. Verify movement log records full history
        movements = manager.get_movements(sku_id="SKU-ELEC-001")
        types = [m["type"] for m in movements]
        assert "receive" in types
        assert "pick" in types

    def test_cycle_count_with_replenishment(self, manager, replenishment):
        """Cycle count reveals missing stock → replenishment generated."""
        # Start with stock above reorder
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 60)

        # Cycle count discovers less than expected
        result = manager.cycle_count("STOR_A_0_0", {"SKU-ELEC-001": 15})
        assert result["discrepancies"] == 1
        assert result["details"][0]["delta"] == -45

        # Now below reorder(50) and below min(20)
        assert manager.get_total_stock("SKU-ELEC-001") == 15

        # Replenishment should trigger
        orders = replenishment.check_and_generate()
        elec_orders = [o for o in orders if o["sku_id"] == "SKU-ELEC-001"]
        assert len(elec_orders) == 1
        assert elec_orders[0]["priority"] == 10  # Critical (below min)

    def test_multi_sku_flow(self, manager, replenishment, optimizer):
        """Multiple SKUs through the full flow with optimizer tracking."""
        # Stock up multiple SKUs
        manager.receive("SKU-ELEC-001", "STOR_A_0_0", 60)
        manager.receive("SKU-CLOTH-001", "STOR_A_0_0", 150)
        manager.receive("SKU-FOOD-001", "STOR_B_0_0", 30)

        # Record picks for optimizer
        for _ in range(50):
            optimizer.record_pick("SKU-ELEC-001")
        for _ in range(10):
            optimizer.record_pick("SKU-CLOTH-001")

        # Verify optimizer ABC
        abc = optimizer.abc_analysis()
        assert abc["A"][0]["sku_id"] == "SKU-ELEC-001"

        # Verify stats
        inv_stats = manager.get_stats()
        assert inv_stats["total_units"] == 240  # 60 + 150 + 30
        assert inv_stats["active_locations"] == 3

        opt_stats = optimizer.get_stats()
        assert opt_stats["total_picks"] == 60

        rep_stats = replenishment.get_stats()
        assert rep_stats["total_orders"] == 0  # No orders yet

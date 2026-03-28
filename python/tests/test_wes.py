"""
Tests for WES (Warehouse Execution System) module.

- OrderGenerator: Poisson arrival process
- TaskGenerator: order → tasks
- KPITracker: metrics computation
"""

import time
import pytest


class TestOrderGenerator:
    def test_init(self):
        """OrderGenerator initializes with pick/drop nodes."""
        from wes.order_generator import OrderGenerator
        og = OrderGenerator(
            pick_nodes=["PICK_1", "PICK_2"],
            drop_nodes=["DROP_1"],
        )
        assert og.order_count == 0
        assert og.arrival_rate == 2.0

    def test_generate_one(self):
        """Generate a single order with correct structure."""
        from wes.order_generator import OrderGenerator
        og = OrderGenerator(
            pick_nodes=["PICK_1"],
            drop_nodes=["DROP_1"],
            seed=42,
        )
        order = og.generate_one()
        assert "order_id" in order
        assert order["source_node"] == "PICK_1"
        assert order["destination_node"] == "DROP_1"
        assert 0 <= order["priority"] <= 10
        assert order["payload_kg"] > 0
        assert order["status"] == "pending"
        assert order["order_type"] == "pick_and_drop"
        assert og.order_count == 1

    def test_generate_batch(self):
        """Generate a batch of orders."""
        from wes.order_generator import OrderGenerator
        og = OrderGenerator(
            pick_nodes=["PICK_1"],
            drop_nodes=["DROP_1"],
            seed=42,
        )
        orders = og.generate_batch(10)
        assert len(orders) == 10
        assert og.order_count == 10
        # All orders have unique IDs
        ids = [o["order_id"] for o in orders]
        assert len(set(ids)) == 10

    def test_generate_poisson_burst(self):
        """Poisson burst generates orders with staggered timestamps."""
        from wes.order_generator import OrderGenerator
        og = OrderGenerator(
            pick_nodes=["PICK_1"],
            drop_nodes=["DROP_1"],
            arrival_rate=5.0,  # 5 per minute
            seed=42,
        )
        orders = og.generate_poisson_burst(duration_s=60.0)
        assert len(orders) > 0
        # Timestamps should be increasing
        timestamps = [o["created_at"] for o in orders]
        for i in range(1, len(timestamps)):
            assert timestamps[i] >= timestamps[i - 1]

    def test_seed_reproducibility(self):
        """Same seed produces same orders."""
        from wes.order_generator import OrderGenerator
        og1 = OrderGenerator(pick_nodes=["P1"], drop_nodes=["D1"], seed=123)
        og2 = OrderGenerator(pick_nodes=["P1"], drop_nodes=["D1"], seed=123)
        o1 = og1.generate_batch(5)
        o2 = og2.generate_batch(5)
        for a, b in zip(o1, o2):
            assert a["source_node"] == b["source_node"]
            assert a["destination_node"] == b["destination_node"]
            assert a["priority"] == b["priority"]
            assert a["payload_kg"] == b["payload_kg"]

    def test_pick_drop_selection(self):
        """Orders use provided pick/drop nodes."""
        from wes.order_generator import OrderGenerator
        og = OrderGenerator(
            pick_nodes=["PICK_A", "PICK_B"],
            drop_nodes=["DROP_X", "DROP_Y"],
            seed=42,
        )
        orders = og.generate_batch(50)
        sources = set(o["source_node"] for o in orders)
        dests = set(o["destination_node"] for o in orders)
        assert sources.issubset({"PICK_A", "PICK_B"})
        assert dests.issubset({"DROP_X", "DROP_Y"})


class TestTaskGenerator:
    def test_init(self):
        """TaskGenerator initializes."""
        from wes.task_generator import TaskGenerator
        tg = TaskGenerator()
        assert tg.task_count == 0

    def test_from_order_pick_and_drop(self):
        """pick_and_drop order becomes a single combined task."""
        from wes.task_generator import TaskGenerator
        tg = TaskGenerator()
        order = {
            "order_id": "order_001",
            "source_node": "PICK_1",
            "destination_node": "DROP_1",
            "priority": 5,
            "payload_kg": 3.0,
            "order_type": "pick_and_drop",
        }
        tasks = tg.from_order(order)
        assert len(tasks) == 1
        t = tasks[0]
        assert t["task_type"] == "pick_and_drop"
        assert t["source_node"] == "PICK_1"
        assert t["destination_node"] == "DROP_1"
        assert t["priority"] == 5
        assert t["status"] == "pending"
        assert "task_id" in t
        assert t["order_id"] == "order_001"

    def test_from_order_separate(self):
        """Non pick_and_drop order becomes separate PICK and DROP tasks."""
        from wes.task_generator import TaskGenerator
        tg = TaskGenerator()
        order = {
            "order_id": "order_002",
            "source_node": "PICK_1",
            "destination_node": "DROP_1",
            "priority": 3,
            "payload_kg": 1.0,
            "order_type": "separate",
        }
        tasks = tg.from_order(order)
        assert len(tasks) == 2
        assert tasks[0]["task_type"] == "pick"
        assert tasks[1]["task_type"] == "drop"

    def test_from_orders_batch(self):
        """Batch conversion of orders to tasks."""
        from wes.task_generator import TaskGenerator
        from wes.order_generator import OrderGenerator

        og = OrderGenerator(pick_nodes=["P1"], drop_nodes=["D1"], seed=42)
        orders = og.generate_batch(5)

        tg = TaskGenerator()
        tasks = tg.from_orders(orders)
        assert len(tasks) == 5  # Each pick_and_drop order = 1 task
        for t in tasks:
            assert "task_id" in t
            assert "order_id" in t

    def test_task_ids_unique(self):
        """All generated tasks have unique IDs."""
        from wes.task_generator import TaskGenerator
        from wes.order_generator import OrderGenerator

        og = OrderGenerator(pick_nodes=["P1"], drop_nodes=["D1"], seed=42)
        tg = TaskGenerator()
        tasks = tg.from_orders(og.generate_batch(20))
        ids = [t["task_id"] for t in tasks]
        assert len(set(ids)) == len(ids)


class TestKPITracker:
    def test_init(self):
        """KPITracker initializes with callable compute method."""
        from wes.kpi_tracker import KPITracker
        kpi = KPITracker()
        assert hasattr(kpi, "compute")
        assert callable(kpi.compute)
        # Verify it returns a dict with expected keys
        result = kpi.compute([], [])
        assert isinstance(result, dict)
        assert "orders_per_hour" in result
        assert "pick_accuracy_pct" in result

    def test_compute_empty(self):
        """Empty data produces zero KPIs."""
        from wes.kpi_tracker import KPITracker
        kpi = KPITracker()
        result = kpi.compute([], [])
        assert result["orders_per_hour"] == 0.0
        assert result["pick_accuracy_pct"] == 100.0
        assert result["throughput_items_per_hour"] == 0.0
        assert result["avg_order_cycle_time_s"] == 0.0
        assert result["pending_orders"] == 0
        assert result["completed_orders"] == 0

    def test_compute_with_data(self):
        """KPI computation with real order/task data."""
        from wes.kpi_tracker import KPITracker
        now = time.time()
        kpi = KPITracker()

        orders = [
            {"order_id": "o1", "status": "completed", "created_at": now - 300, "completed_at": now - 100},
            {"order_id": "o2", "status": "completed", "created_at": now - 200, "completed_at": now - 50},
            {"order_id": "o3", "status": "pending", "created_at": now - 10},
        ]

        tasks = [
            {"task_id": "t1", "status": "completed", "created_at": now - 300},
            {"task_id": "t2", "status": "completed", "created_at": now - 200},
            {"task_id": "t3", "status": "failed", "created_at": now - 150},
            {"task_id": "t4", "status": "pending", "created_at": now - 10},
        ]

        result = kpi.compute(orders, tasks)
        assert result["total_orders"] == 3
        assert result["completed_orders"] == 2
        assert result["pending_orders"] == 1
        assert result["completed_tasks"] == 2
        assert result["failed_tasks"] == 1
        assert result["orders_per_hour"] > 0
        assert result["throughput_items_per_hour"] > 0
        # Pick accuracy: 2 completed / (2 completed + 1 failed) = 66.7%
        assert 66.0 <= result["pick_accuracy_pct"] <= 67.0
        # Avg cycle time: (200 + 150) / 2 = 175s
        assert result["avg_order_cycle_time_s"] == 175.0

    def test_compute_all_successful(self):
        """100% pick accuracy when no failures."""
        from wes.kpi_tracker import KPITracker
        now = time.time()
        kpi = KPITracker()
        tasks = [
            {"task_id": f"t{i}", "status": "completed", "created_at": now - 100}
            for i in range(10)
        ]
        result = kpi.compute([], tasks)
        assert result["pick_accuracy_pct"] == 100.0
        assert result["completed_tasks"] == 10
        assert result["failed_tasks"] == 0

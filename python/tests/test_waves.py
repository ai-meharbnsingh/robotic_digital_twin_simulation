"""
Phase 4: Wave Rule Engine — tests for WaveEngine, wave routes, and auto-wave.

Tests verify:
- WaveEngine creates waves from order IDs
- Auto-wave groups orders by zone affinity rules
- Rule evaluation filters by zone, priority, batch size
- Wave release generates correct tasks via TaskGenerator
- REST endpoints return correct response shapes
- Rules persist via GET/POST endpoints
- Edge cases: empty orders, no matching rules, already-released wave
"""

import time

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from wes.wave_engine import WaveEngine
from wes.task_generator import TaskGenerator
from app.main import app, lifespan

# ── Fixtures ─────────────────────────────────────────────

SIMPLE_WAREHOUSE = {
    "nodes": [
        {"name": "DOCK_1", "x": 0, "y": 0, "type": "charge"},
        {"name": "S_11", "x": 2, "y": 2, "type": "shelf"},
        {"name": "S_12", "x": 4, "y": 2, "type": "shelf"},
        {"name": "PICK_1", "x": 0, "y": 8, "type": "pick"},
        {"name": "DROP_1", "x": 8, "y": 8, "type": "drop"},
    ],
    "zones": [
        {"name": "Charging", "type": "dock", "nodes": ["DOCK_1"]},
        {"name": "Storage", "type": "shelf", "nodes": ["S_11", "S_12"]},
        {"name": "Operations", "type": "ops", "nodes": ["PICK_1", "DROP_1"]},
    ],
}


def make_order(order_id: str, source: str, dest: str, priority: int = 5) -> dict:
    return {
        "order_id": order_id,
        "source_node": source,
        "destination_node": dest,
        "priority": priority,
        "payload_kg": 10.0,
        "order_type": "pick_and_drop",
        "status": "pending",
        "created_at": time.time(),
    }


@pytest_asyncio.fixture
async def client():
    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c


# ── WaveEngine unit tests ────────────────────────────────


class TestWaveEngineUnit:
    def test_create_wave(self):
        engine = WaveEngine(SIMPLE_WAREHOUSE)
        wave = engine.create_wave(
            order_ids=["o1", "o2", "o3"],
            zone_affinity="Storage",
            max_robots=3,
        )
        assert wave["status"] == "pending"
        assert wave["order_ids"] == ["o1", "o2", "o3"]
        assert wave["zone_affinity"] == "Storage"
        assert wave["max_robots"] == 3
        assert wave["wave_id"]  # UUID generated
        assert wave["released_at"] is None
        assert wave["task_ids"] == []

    def test_node_zone_mapping(self):
        engine = WaveEngine(SIMPLE_WAREHOUSE)
        assert engine.get_zone_for_node("S_11") == "Storage"
        assert engine.get_zone_for_node("S_12") == "Storage"
        assert engine.get_zone_for_node("DOCK_1") == "Charging"
        assert engine.get_zone_for_node("PICK_1") == "Operations"
        assert engine.get_zone_for_node("NONEXISTENT") == "unknown"

    def test_add_rule(self):
        engine = WaveEngine(SIMPLE_WAREHOUSE)
        rule = engine.add_rule({
            "name": "Storage Batch",
            "conditions": {"zone": "Storage", "batch_size": 2},
            "action": {"max_robots": 3},
        })
        assert rule["name"] == "Storage Batch"
        assert rule["conditions"]["zone"] == "Storage"
        assert rule["conditions"]["batch_size"] == 2
        assert rule["action"]["max_robots"] == 3
        assert rule["enabled"] is True
        assert rule["rule_id"]

    def test_get_rules(self):
        engine = WaveEngine(SIMPLE_WAREHOUSE)
        engine.add_rule({"name": "Rule A"})
        engine.add_rule({"name": "Rule B"})
        assert len(engine.get_rules()) == 2

    def test_auto_wave_by_zone(self):
        engine = WaveEngine(SIMPLE_WAREHOUSE)
        engine.add_rule({
            "name": "Storage Batch",
            "conditions": {"zone": "Storage", "batch_size": 2},
            "action": {"max_robots": 3},
        })

        orders = [
            make_order("o1", "S_11", "DROP_1"),
            make_order("o2", "S_12", "DROP_1"),
            make_order("o3", "PICK_1", "DROP_1"),  # Operations zone, not Storage
        ]

        waves = engine.auto_wave(orders)
        assert len(waves) == 1
        assert set(waves[0]["order_ids"]) == {"o1", "o2"}
        assert waves[0]["zone_affinity"] == "Storage"
        assert waves[0]["max_robots"] == 3

    def test_auto_wave_batch_size_threshold(self):
        """Orders below batch_size threshold should not form a wave."""
        engine = WaveEngine(SIMPLE_WAREHOUSE)
        engine.add_rule({
            "name": "Big Batch",
            "conditions": {"zone": "Storage", "batch_size": 5},
        })

        orders = [
            make_order("o1", "S_11", "DROP_1"),
            make_order("o2", "S_12", "DROP_1"),
        ]

        waves = engine.auto_wave(orders)
        assert len(waves) == 0  # Only 2 orders, need 5

    def test_auto_wave_priority_filter(self):
        engine = WaveEngine(SIMPLE_WAREHOUSE)
        engine.add_rule({
            "name": "High Priority",
            "conditions": {"zone": "Storage", "min_priority": 7, "batch_size": 1},
        })

        orders = [
            make_order("o1", "S_11", "DROP_1", priority=8),
            make_order("o2", "S_12", "DROP_1", priority=3),  # Below min
        ]

        waves = engine.auto_wave(orders)
        assert len(waves) == 1
        assert waves[0]["order_ids"] == ["o1"]

    def test_auto_wave_disabled_rule_skipped(self):
        engine = WaveEngine(SIMPLE_WAREHOUSE)
        engine.add_rule({
            "name": "Disabled",
            "conditions": {"zone": "Storage", "batch_size": 1},
            "enabled": False,
        })

        orders = [make_order("o1", "S_11", "DROP_1")]
        waves = engine.auto_wave(orders)
        assert len(waves) == 0

    def test_auto_wave_no_double_assignment(self):
        """An order matched by Rule A should not be matched again by Rule B."""
        engine = WaveEngine(SIMPLE_WAREHOUSE)
        engine.add_rule({
            "name": "Rule A",
            "conditions": {"zone": "Storage", "batch_size": 1},
        })
        engine.add_rule({
            "name": "Rule B",
            "conditions": {"batch_size": 1},  # No zone filter
        })

        orders = [make_order("o1", "S_11", "DROP_1")]
        waves = engine.auto_wave(orders)
        # o1 matched by Rule A — Rule B should not re-match it
        assert len(waves) == 1
        assert waves[0]["order_ids"] == ["o1"]

    def test_release_wave(self):
        engine = WaveEngine(SIMPLE_WAREHOUSE)
        task_gen = TaskGenerator()

        orders = [
            make_order("o1", "S_11", "DROP_1"),
            make_order("o2", "S_12", "DROP_1"),
        ]

        wave = engine.create_wave(order_ids=["o1", "o2"])
        updated_wave, tasks = engine.release_wave(wave, orders, task_gen)

        assert updated_wave["status"] == "active"
        assert updated_wave["released_at"] is not None
        assert len(tasks) == 2  # 2 pick_and_drop orders → 2 tasks
        assert len(updated_wave["task_ids"]) == 2

        # Task details correct
        for task in tasks:
            assert task["status"] == "pending"
            assert task["order_id"] in ("o1", "o2")

    def test_release_already_active_raises(self):
        engine = WaveEngine(SIMPLE_WAREHOUSE)
        wave = engine.create_wave(order_ids=["o1"])
        wave["status"] = "active"

        with pytest.raises(ValueError, match="Cannot release"):
            engine.release_wave(wave, [], TaskGenerator())

    def test_auto_wave_empty_orders(self):
        engine = WaveEngine(SIMPLE_WAREHOUSE)
        engine.add_rule({"name": "Any", "conditions": {"batch_size": 1}})
        waves = engine.auto_wave([])
        assert len(waves) == 0

    def test_auto_wave_no_rules(self):
        engine = WaveEngine(SIMPLE_WAREHOUSE)
        orders = [make_order("o1", "S_11", "DROP_1")]
        waves = engine.auto_wave(orders)
        assert len(waves) == 0


# ── REST endpoint tests ──────────────────────────────────


class TestWaveRoutes:
    async def test_list_waves_empty(self, client: AsyncClient):
        resp = await client.get("/api/wes/waves")
        assert resp.status_code == 200
        data = resp.json()
        assert "waves" in data
        assert "count" in data
        assert "summary" in data
        assert isinstance(data["waves"], list)

    async def test_list_wave_rules_empty(self, client: AsyncClient):
        resp = await client.get("/api/wes/wave-rules")
        assert resp.status_code == 200
        data = resp.json()
        assert "rules" in data
        assert isinstance(data["rules"], list)

    async def test_create_wave_rule(self, client: AsyncClient):
        resp = await client.post("/api/wes/wave-rules", json={
            "name": "Test Rule",
            "conditions": {"zone": "Storage", "batch_size": 2},
            "action": {"max_robots": 3},
            "enabled": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "rule" in data
        assert data["rule"]["name"] == "Test Rule"
        assert data["rule"]["conditions"]["zone"] == "Storage"

    async def test_create_manual_wave(self, client: AsyncClient):
        resp = await client.post("/api/wes/waves", json={
            "order_ids": ["test-order-1", "test-order-2"],
            "zone_affinity": "Storage",
            "max_robots": 3,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "manual"
        assert "wave" in data
        assert data["wave"]["status"] == "pending"
        assert len(data["wave"]["order_ids"]) == 2

    async def test_auto_wave_returns_mode(self, client: AsyncClient):
        resp = await client.post("/api/wes/waves", content=b"null",
                                  headers={"content-type": "application/json"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "auto"

    async def test_release_nonexistent_wave_404(self, client: AsyncClient):
        resp = await client.post("/api/wes/waves/nonexistent-id/release")
        assert resp.status_code == 404

    async def test_wave_rule_requires_name(self, client: AsyncClient):
        resp = await client.post("/api/wes/wave-rules", json={
            "conditions": {},
        })
        assert resp.status_code == 422  # Missing required 'name'

    async def test_summary_counts(self, client: AsyncClient):
        resp = await client.get("/api/wes/waves")
        summary = resp.json()["summary"]
        assert "pending" in summary
        assert "active" in summary
        assert "completed" in summary
        assert isinstance(summary["pending"], int)

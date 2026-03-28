"""
Test ALL 34 API endpoints with real assertions.

Tests run against the FastAPI app via httpx AsyncClient.
MongoDB may or may not be available — tests verify correct response shapes
either way (graceful degradation: empty data with 200 when DB unavailable).
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app, lifespan


@pytest_asyncio.fixture
async def client():
    """Async test client with lifespan."""
    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c


# ─── 1. Root + Health (2 endpoints) ───


class TestRootAndHealth:
    async def test_root(self, client: AsyncClient):
        """GET / — returns service info."""
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "Robotic Digital Twin API"
        assert data["version"] == "0.1.0"
        assert "docs" in data
        assert data["endpoints"] == 34

    async def test_health(self, client: AsyncClient):
        """GET /health — returns actual service status booleans."""
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert isinstance(data["mongodb_ok"], bool)
        assert isinstance(data["redis_ok"], bool)
        assert isinstance(data["influxdb_ok"], bool)
        assert isinstance(data["rabbitmq_ok"], bool)
        assert isinstance(data["warehouse_loaded"], bool)
        assert isinstance(data["robot_loaded"], bool)
        assert isinstance(data["check_duration_ms"], (int, float))
        # Warehouse and robot configs should always load (they're on disk)
        assert data["warehouse_loaded"] is True
        assert data["robot_loaded"] is True


# ─── 2. Fleet (1 endpoint) ───


class TestFleet:
    async def test_fleet_status(self, client: AsyncClient):
        """GET /api/fleet/status — returns fleet overview."""
        resp = await client.get("/api/fleet/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_robots" in data
        assert "status_counts" in data
        assert "active_tasks" in data
        assert "completed_tasks" in data
        assert "failed_tasks" in data
        assert "utilisation_pct" in data
        assert isinstance(data["total_robots"], int)
        assert isinstance(data["utilisation_pct"], (int, float))


# ─── 3. Robots (3 endpoints) ───


class TestRobots:
    async def test_list_robots(self, client: AsyncClient):
        """GET /api/robots — returns list."""
        resp = await client.get("/api/robots")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    async def test_get_robot_not_found(self, client: AsyncClient):
        """GET /api/robots/{id} — 404 or 503 for nonexistent robot."""
        resp = await client.get("/api/robots/nonexistent_robot_999")
        # 404 if DB is available, 503 if not
        assert resp.status_code in (404, 503)

    async def test_send_command_not_found(self, client: AsyncClient):
        """POST /api/robots/{id}/command — 404 or 503 for nonexistent robot."""
        resp = await client.post(
            "/api/robots/nonexistent_robot_999/command",
            json={"action": "move", "target_node": "N_01"},
        )
        assert resp.status_code in (404, 503)


# ─── 4. Tasks (5 endpoints) ───


class TestTasks:
    async def test_list_tasks(self, client: AsyncClient):
        """GET /api/tasks — returns list."""
        resp = await client.get("/api/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    async def test_create_task(self, client: AsyncClient):
        """POST /api/tasks — creates a task or returns 503."""
        resp = await client.post("/api/tasks", json={
            "source_node": "PICK_1",
            "destination_node": "DROP_1",
            "priority": 5,
            "payload_kg": 2.5,
        })
        # 200 if DB available, 503 if not
        assert resp.status_code in (200, 503)
        if resp.status_code == 200:
            data = resp.json()
            assert "task_id" in data
            assert data["status"] == "pending"
            assert data["source_node"] == "PICK_1"
            assert data["destination_node"] == "DROP_1"
            assert data["priority"] == 5

    async def test_get_task_not_found(self, client: AsyncClient):
        """GET /api/tasks/{id} — 404 or 503."""
        resp = await client.get("/api/tasks/nonexistent_task_999")
        assert resp.status_code in (404, 503)

    async def test_delete_task_not_found(self, client: AsyncClient):
        """DELETE /api/tasks/{id} — 404 or 503."""
        resp = await client.delete("/api/tasks/nonexistent_task_999")
        assert resp.status_code in (404, 503)

    async def test_cancel_task_not_found(self, client: AsyncClient):
        """POST /api/tasks/{id}/cancel — 404 or 503."""
        resp = await client.post("/api/tasks/nonexistent_task_999/cancel")
        assert resp.status_code in (404, 503)


# ─── 5. Map (4 endpoints) ───


class TestMap:
    async def test_get_map(self, client: AsyncClient):
        """GET /api/map — returns full warehouse map."""
        resp = await client.get("/api/map")
        assert resp.status_code == 200
        data = resp.json()
        assert "name" in data
        assert "nodes" in data
        assert "edges" in data
        assert "zones" in data
        assert data["name"] == "Simple 5x5 Grid"
        assert len(data["nodes"]) == 25
        assert len(data["edges"]) == 40
        assert len(data["zones"]) == 3

    async def test_list_nodes(self, client: AsyncClient):
        """GET /api/map/nodes — returns all nodes."""
        resp = await client.get("/api/map/nodes")
        assert resp.status_code == 200
        nodes = resp.json()
        assert isinstance(nodes, list)
        assert len(nodes) == 25
        node_names = [n["name"] for n in nodes]
        assert "DOCK_1" in node_names
        assert "HUB" in node_names
        assert "DROP_1" in node_names

    async def test_get_path(self, client: AsyncClient):
        """GET /api/map/path — computes A* path."""
        resp = await client.get("/api/map/path", params={"start": "DOCK_1", "end": "DROP_1"})
        assert resp.status_code == 200
        data = resp.json()
        assert "path" in data
        assert isinstance(data["path"], list)
        assert len(data["path"]) > 0
        assert data["path"][0] == "DOCK_1"
        assert data["path"][-1] == "DROP_1"
        assert "distance" in data
        assert data["distance"] > 0

    async def test_get_path_invalid_node(self, client: AsyncClient):
        """GET /api/map/path — error for invalid node."""
        resp = await client.get("/api/map/path", params={"start": "NONEXISTENT", "end": "DROP_1"})
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data

    async def test_list_zones(self, client: AsyncClient):
        """GET /api/map/zones — returns zones."""
        resp = await client.get("/api/map/zones")
        assert resp.status_code == 200
        zones = resp.json()
        assert isinstance(zones, list)
        assert len(zones) == 3
        zone_names = [z["name"] for z in zones]
        assert "Charging" in zone_names
        assert "Storage" in zone_names
        assert "Operations" in zone_names


# ─── 6. io-gita (3 endpoints) ───


class TestIoGita:
    async def test_iogita_status(self, client: AsyncClient):
        """GET /api/iogita/status — returns intelligence layer status."""
        resp = await client.get("/api/iogita/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["engine"] == "io-gita"
        assert isinstance(data["zone_identifier_loaded"], bool)
        assert isinstance(data["cold_start_loaded"], bool)
        assert data["zone_identifier_loaded"] is True
        assert data["cold_start_loaded"] is True

    async def test_iogita_zones(self, client: AsyncClient):
        """GET /api/iogita/zones — returns zone identification results."""
        resp = await client.get("/api/iogita/zones")
        assert resp.status_code == 200
        data = resp.json()
        assert "zones" in data
        assert "engine" in data
        assert isinstance(data["zones"], list)

    async def test_iogita_cold_start(self, client: AsyncClient):
        """POST /api/iogita/cold-start/{id} — triggers cold start recovery."""
        resp = await client.post("/api/iogita/cold-start/robot_001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["robot_id"] == "robot_001"
        assert "recovery_hints" in data
        assert data["cold_start_engine"] == "io-gita"
        hints = data["recovery_hints"]
        assert "steps" in hints
        assert isinstance(hints["steps"], list)
        assert len(hints["steps"]) > 0


# ─── 7. Telemetry (1 endpoint) ───


class TestTelemetry:
    async def test_get_telemetry(self, client: AsyncClient):
        """GET /api/telemetry/{id} — returns telemetry points."""
        resp = await client.get("/api/telemetry/robot_001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["robot_id"] == "robot_001"
        assert "points" in data
        assert isinstance(data["points"], list)


# ─── 8. Analytics (3 endpoints) ───


class TestAnalytics:
    async def test_fleet_analytics(self, client: AsyncClient):
        """GET /api/analytics/fleet — returns fleet analytics."""
        resp = await client.get("/api/analytics/fleet")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_tasks" in data
        assert "completed_tasks" in data
        assert "failed_tasks" in data
        assert "avg_task_time_s" in data
        assert "total_robots" in data
        assert "avg_battery_pct" in data
        assert "throughput_tasks_per_hour" in data

    async def test_sg_predictions(self, client: AsyncClient):
        """GET /api/analytics/predictions — returns SG predictions."""
        resp = await client.get("/api/analytics/predictions")
        assert resp.status_code == 200
        data = resp.json()
        assert "predictions" in data
        assert "engine" in data

    async def test_ab_comparison(self, client: AsyncClient):
        """GET /api/analytics/ab-comparison — returns A/B comparison."""
        resp = await client.get("/api/analytics/ab-comparison")
        assert resp.status_code == 200
        data = resp.json()
        assert "comparisons" in data
        assert "strategies" in data
        assert isinstance(data["strategies"], list)
        assert "fifo" in data["strategies"]


# ─── 9. Events (1 endpoint) ───


class TestEvents:
    async def test_list_events(self, client: AsyncClient):
        """GET /api/events — returns event list."""
        resp = await client.get("/api/events")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


# ─── 10. WCS (2 endpoints) ───


class TestWCS:
    async def test_list_conveyors(self, client: AsyncClient):
        """GET /api/wcs/conveyors — returns conveyor list."""
        resp = await client.get("/api/wcs/conveyors")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    async def test_list_lanes(self, client: AsyncClient):
        """GET /api/wcs/lanes — returns lane list."""
        resp = await client.get("/api/wcs/lanes")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


# ─── 11. WES (2 endpoints) ───


class TestWES:
    async def test_inject_orders(self, client: AsyncClient):
        """POST /api/wes/inject-orders — injects orders."""
        resp = await client.post("/api/wes/inject-orders", json={"num_orders": 3})
        assert resp.status_code == 200
        data = resp.json()
        assert "injected" in data
        # If WES is loaded, should inject 3 orders
        if data["injected"] > 0:
            assert data["injected"] == 3
            assert "orders" in data
            assert len(data["orders"]) == 3
            for order in data["orders"]:
                assert "order_id" in order
                assert "source_node" in order
                assert "destination_node" in order

    async def test_wes_kpi(self, client: AsyncClient):
        """GET /api/wes/kpi — returns KPI metrics."""
        resp = await client.get("/api/wes/kpi")
        assert resp.status_code == 200
        data = resp.json()
        assert "orders_per_hour" in data
        assert "pick_accuracy_pct" in data
        assert "throughput_items_per_hour" in data
        assert "avg_order_cycle_time_s" in data
        assert "pending_orders" in data
        assert "completed_orders" in data


# ─── 12. Simulation (4 endpoints) ───


class TestSimulation:
    async def test_simulation_status(self, client: AsyncClient):
        """GET /api/simulation/status — returns simulation state."""
        resp = await client.get("/api/simulation/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "running" in data
        assert isinstance(data["running"], bool)
        assert "tick_count" in data
        assert "elapsed_s" in data

    async def test_simulation_start(self, client: AsyncClient):
        """POST /api/simulation/start — starts simulation."""
        resp = await client.post("/api/simulation/start")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("started", "already_running")
        assert "started_at" in data

    async def test_simulation_stop(self, client: AsyncClient):
        """POST /api/simulation/stop — stops simulation."""
        # Start first
        await client.post("/api/simulation/start")
        resp = await client.post("/api/simulation/stop")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("stopped", "already_stopped")

    async def test_inject_fault(self, client: AsyncClient):
        """POST /api/simulation/inject-fault — injects a fault."""
        resp = await client.post("/api/simulation/inject-fault", json={
            "fault_type": "battery_drain",
            "robot_id": "robot_001",
            "duration_s": 5.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "fault_injected"
        assert "fault" in data
        assert data["fault"]["fault_type"] == "battery_drain"
        assert data["fault"]["robot_id"] == "robot_001"


# ─── 13. Config (1 endpoint) ───


class TestConfig:
    async def test_robot_config(self, client: AsyncClient):
        """GET /api/config/robots — returns YAML robot config."""
        resp = await client.get("/api/config/robots")
        assert resp.status_code == 200
        data = resp.json()
        assert "config" in data
        assert data["source"] == "yaml"
        # Config should be loaded from differential_drive.yaml
        config = data["config"]
        assert isinstance(config, dict)
        assert len(config) > 0


# ─── 14. Stats (1 endpoint) ───


class TestStats:
    async def test_throughput(self, client: AsyncClient):
        """GET /api/stats/throughput — returns throughput stats."""
        resp = await client.get("/api/stats/throughput")
        assert resp.status_code == 200
        data = resp.json()
        assert "window_s" in data
        assert "tasks_completed" in data
        assert "tasks_per_hour" in data
        assert "by_type" in data
        assert isinstance(data["tasks_completed"], int)


# ─── 15. Reservations (1 endpoint) ───


class TestReservations:
    async def test_active_reservations(self, client: AsyncClient):
        """GET /api/reservations/active — returns active reservations."""
        resp = await client.get("/api/reservations/active")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


# ─── Endpoint count verification ───


class TestEndpointCount:
    async def test_all_34_endpoints_exist(self, client: AsyncClient):
        """Verify all 34 contracted endpoints respond (not 404/405)."""
        endpoints = [
            # Root + Health (2)
            ("GET", "/"),
            ("GET", "/health"),
            # Fleet (1)
            ("GET", "/api/fleet/status"),
            # Robots (3)
            ("GET", "/api/robots"),
            ("GET", "/api/robots/test_id"),
            ("POST", "/api/robots/test_id/command"),
            # Tasks (5)
            ("GET", "/api/tasks"),
            ("POST", "/api/tasks"),
            ("GET", "/api/tasks/test_id"),
            ("DELETE", "/api/tasks/test_id"),
            ("POST", "/api/tasks/test_id/cancel"),
            # Map (4)
            ("GET", "/api/map"),
            ("GET", "/api/map/nodes"),
            ("GET", "/api/map/path"),
            ("GET", "/api/map/zones"),
            # io-gita (3)
            ("GET", "/api/iogita/status"),
            ("GET", "/api/iogita/zones"),
            ("POST", "/api/iogita/cold-start/test_id"),
            # Telemetry (1)
            ("GET", "/api/telemetry/test_id"),
            # Analytics (3)
            ("GET", "/api/analytics/fleet"),
            ("GET", "/api/analytics/predictions"),
            ("GET", "/api/analytics/ab-comparison"),
            # Events (1)
            ("GET", "/api/events"),
            # WCS (2)
            ("GET", "/api/wcs/conveyors"),
            ("GET", "/api/wcs/lanes"),
            # WES (2)
            ("POST", "/api/wes/inject-orders"),
            ("GET", "/api/wes/kpi"),
            # Simulation (4)
            ("GET", "/api/simulation/status"),
            ("POST", "/api/simulation/start"),
            ("POST", "/api/simulation/stop"),
            ("POST", "/api/simulation/inject-fault"),
            # Config (1)
            ("GET", "/api/config/robots"),
            # Stats (1)
            ("GET", "/api/stats/throughput"),
            # Reservations (1)
            ("GET", "/api/reservations/active"),
        ]

        assert len(endpoints) == 34, f"Expected 34 endpoints, got {len(endpoints)}"

        for method, path in endpoints:
            if method == "GET":
                if "path" in path and "?" not in path and path == "/api/map/path":
                    resp = await client.get(path, params={"start": "DOCK_1", "end": "DROP_1"})
                else:
                    resp = await client.get(path)
            elif method == "POST":
                # POST endpoints need bodies
                if "command" in path:
                    resp = await client.post(path, json={"action": "test"})
                elif "tasks" in path and path.endswith("/cancel"):
                    resp = await client.post(path)
                elif path == "/api/tasks":
                    resp = await client.post(path, json={"source_node": "A", "destination_node": "B"})
                elif "inject-orders" in path:
                    resp = await client.post(path, json={"num_orders": 1})
                elif "inject-fault" in path:
                    resp = await client.post(path, json={"fault_type": "test"})
                elif "cold-start" in path:
                    resp = await client.post(path)
                else:
                    resp = await client.post(path)
            elif method == "DELETE":
                resp = await client.delete(path)

            # Must not be 404 (route not found) or 405 (method not allowed)
            assert resp.status_code not in (404, 405), (
                f"{method} {path} returned {resp.status_code} — endpoint missing"
            )

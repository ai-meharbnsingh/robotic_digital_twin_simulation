"""
Integration tests for Phase 11 — verifies the full stack works together.

TEST: All 30 API endpoints return 200 (or expected error for missing resources)
TEST: WebSocket connects and receives events
TEST: Config loads both warehouse formats (simple_grid, botvalley)
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client():
    """Async test client with lifespan."""
    import os
    os.environ["WAREHOUSE_CONFIG"] = "simple_grid"
    os.environ["ROBOT_CONFIG"] = "differential_drive"
    os.environ["MONGODB_URL"] = "mongodb://localhost:27017"
    os.environ["REDIS_URL"] = "redis://localhost:6379"
    os.environ["INFLUXDB_URL"] = "http://localhost:8086"

    from app.main import app, lifespan
    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c


# ── TEST: All 30 API endpoints return expected status ──────────────────

class TestAllEndpoints:
    """Verify all 30 API endpoints respond correctly."""

    async def test_root(self, client):
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "Robotic Digital Twin API"
        assert data["endpoints"] == 32

    async def test_health(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "mongodb_ok" in data
        assert "warehouse_loaded" in data
        assert data["warehouse_loaded"] is True
        assert data["robot_loaded"] is True

    async def test_fleet_status(self, client):
        resp = await client.get("/api/fleet/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_robots" in data
        assert "utilisation_pct" in data

    async def test_list_robots(self, client):
        resp = await client.get("/api/robots")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_get_robot_not_found(self, client):
        resp = await client.get("/api/robots/nonexistent_robot_99")
        # 404 or 503 (if MongoDB not available)
        assert resp.status_code in (404, 503)

    async def test_send_command_not_found(self, client):
        resp = await client.post(
            "/api/robots/nonexistent_robot_99/command",
            json={"action": "move", "target_node": "DOCK_1"},
        )
        assert resp.status_code in (404, 503)

    async def test_list_tasks(self, client):
        resp = await client.get("/api/tasks")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_create_task(self, client):
        resp = await client.post("/api/tasks", json={
            "task_type": "pick_and_drop",
            "source_node": "PICK_1",
            "destination_node": "DROP_1",
            "priority": 5,
            "payload_kg": 10.0,
        })
        # 200 or 503 (if MongoDB unavailable)
        assert resp.status_code in (200, 503)

    async def test_get_task_not_found(self, client):
        resp = await client.get("/api/tasks/nonexistent_task_99")
        assert resp.status_code in (404, 503)

    async def test_delete_task_not_found(self, client):
        resp = await client.delete("/api/tasks/nonexistent_task_99")
        assert resp.status_code in (404, 503)

    async def test_cancel_task_not_found(self, client):
        resp = await client.post("/api/tasks/nonexistent_task_99/cancel")
        assert resp.status_code in (404, 503)

    async def test_get_map(self, client):
        resp = await client.get("/api/map")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Simple 5x5 Grid"
        assert len(data["nodes"]) == 25
        assert len(data["edges"]) == 40
        assert len(data["zones"]) == 8

    async def test_list_nodes(self, client):
        resp = await client.get("/api/map/nodes")
        assert resp.status_code == 200
        nodes = resp.json()
        assert len(nodes) == 25
        assert nodes[0]["name"] == "DOCK_1"

    async def test_get_path(self, client):
        resp = await client.get("/api/map/path?start=DOCK_1&end=DROP_1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["path"]) > 0
        assert data["path"][0] == "DOCK_1"
        assert data["path"][-1] == "DROP_1"
        assert data["hops"] > 0
        assert data["distance"] > 0

    async def test_get_path_invalid_node(self, client):
        resp = await client.get("/api/map/path?start=FAKE&end=DROP_1")
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data

    async def test_list_zones(self, client):
        resp = await client.get("/api/map/zones")
        assert resp.status_code == 200
        zones = resp.json()
        assert len(zones) == 8
        zone_names = {z["name"] for z in zones}
        assert "Charging" in zone_names
        assert "Storage" in zone_names
        assert "Operations" in zone_names

    async def test_analytics_fleet(self, client):
        resp = await client.get("/api/analytics/fleet")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_tasks" in data
        assert "avg_battery_pct" in data

    async def test_analytics_ab_comparison(self, client):
        resp = await client.get("/api/analytics/ab-comparison")
        assert resp.status_code == 200
        data = resp.json()
        assert "strategies" in data
        assert "fifo" in data["strategies"]

    async def test_telemetry(self, client):
        resp = await client.get("/api/telemetry/robot_01?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["robot_id"] == "robot_01"
        assert "points" in data

    async def test_events(self, client):
        resp = await client.get("/api/events?limit=5")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_simulation_status(self, client):
        resp = await client.get("/api/simulation/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "running" in data
        assert data["running"] is False

    async def test_simulation_start(self, client):
        resp = await client.post("/api/simulation/start")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("started", "already_running")

    async def test_simulation_stop(self, client):
        # Start first to ensure we can stop
        await client.post("/api/simulation/start")
        resp = await client.post("/api/simulation/stop")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("stopped", "already_stopped")

    async def test_inject_fault(self, client):
        resp = await client.post("/api/simulation/inject-fault", json={
            "fault_type": "battery_drain",
            "robot_id": "robot_01",
            "duration_s": 5.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "fault_injected"
        assert data["fault"]["fault_type"] == "battery_drain"

    async def test_wes_inject_orders(self, client):
        resp = await client.post("/api/wes/inject-orders", json={
            "num_orders": 3,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["injected"] == 3
        assert len(data["orders"]) == 3

    async def test_wes_kpi(self, client):
        resp = await client.get("/api/wes/kpi")
        assert resp.status_code == 200
        data = resp.json()
        assert "orders_per_hour" in data

    async def test_wcs_conveyors(self, client):
        resp = await client.get("/api/wcs/conveyors")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_wcs_lanes(self, client):
        resp = await client.get("/api/wcs/lanes")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_config_robots(self, client):
        resp = await client.get("/api/config/robots")
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "yaml"
        assert data["config"]["name"] == "DiffDrive_AMR"
        assert data["config"]["type"] == "differential_drive"
        assert data["config"]["motion"]["max_linear_velocity"] == 2.0

    async def test_stats_throughput(self, client):
        resp = await client.get("/api/stats/throughput?window_s=3600")
        assert resp.status_code == 200
        data = resp.json()
        assert data["window_s"] == 3600
        assert "tasks_per_hour" in data

    async def test_reservations_active(self, client):
        resp = await client.get("/api/reservations/active")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ── TEST: WebSocket connects and receives events ──────────────────────

class TestWebSocket:
    """Verify WebSocket connection and event handling."""

    async def test_websocket_connect(self, client):
        """WebSocket connects and receives the connected confirmation."""
        from app.main import app
        from httpx import ASGITransport
        import websockets.client

        # Use the ASGI test client to test WebSocket
        # FastAPI TestClient supports WebSocket via starlette
        from starlette.testclient import TestClient

        sync_client = TestClient(app)
        with sync_client.websocket_connect("/ws/fleet") as ws:
            data = ws.receive_json()
            assert data["type"] == "connected"
            assert "active_connections" in data

    async def test_websocket_ping_pong(self, client):
        """WebSocket responds to ping with pong."""
        from app.main import app
        from starlette.testclient import TestClient

        sync_client = TestClient(app)
        with sync_client.websocket_connect("/ws/fleet") as ws:
            # Receive initial connected message
            ws.receive_json()

            # Send ping
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"
            assert "ts" in data


# ── TEST: Config loads both warehouse formats ──────────────────────────

class TestConfigLoading:
    """Verify config loaders work with both warehouse formats."""

    def test_load_simple_grid(self):
        """Load simple_grid warehouse config."""
        from app.config import load_warehouse_config
        config = load_warehouse_config("simple_grid")
        assert config["name"] == "Simple 5x5 Grid"
        assert len(config["nodes"]) == 25
        assert len(config["edges"]) == 40
        assert len(config["zones"]) == 8

    def test_load_botvalley(self):
        """Load botvalley warehouse config."""
        from app.config import load_warehouse_config
        config = load_warehouse_config("botvalley")
        assert "edges" in config
        assert len(config["edges"]) > 0
        # BotValley has 63 nodes
        nodes = config.get("nodes", [])
        if nodes:
            assert len(nodes) >= 60

    def test_load_differential_drive(self):
        """Load differential drive robot config."""
        from app.config import load_robot_config
        config = load_robot_config("differential_drive")
        assert config["name"] == "DiffDrive_AMR"
        assert config["type"] == "differential_drive"
        assert config["motion"]["max_linear_velocity"] == 2.0
        assert config["battery"]["charge_duration_s"] == 600

    def test_load_unidirectional(self):
        """Load unidirectional robot config."""
        from app.config import load_robot_config
        config = load_robot_config("unidirectional")
        assert config["name"] == "Uni_AGV"
        assert config["type"] == "unidirectional"
        assert config["motion"]["max_linear_velocity"] == 1.4

    def test_load_nonexistent_warehouse_raises(self):
        """Loading a nonexistent warehouse raises FileNotFoundError."""
        from app.config import load_warehouse_config
        with pytest.raises(FileNotFoundError):
            load_warehouse_config("nonexistent_warehouse_xyz")



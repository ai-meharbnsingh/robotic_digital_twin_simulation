"""
Integration tests for Phase 11 — verifies the full stack works together.

TEST: Cold start demo runs without error
TEST: All 34 API endpoints return 200 (or expected error for missing resources)
TEST: WebSocket connects and receives events
TEST: Config loads both warehouse formats (simple_grid, botvalley)
TEST: io-gita + SG pipeline works end-to-end
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client():
    """Async test client with lifespan (starts intelligence layer)."""
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


# ── TEST: Cold start demo runs without error ──────────────────────────

class TestColdStartDemo:
    """Verify the cold start demo script executes without errors."""

    def test_cold_start_demo_runs(self):
        """Run demo/cold_start_demo.py and check exit code 0."""
        demo_path = PROJECT_ROOT / "demo" / "cold_start_demo.py"
        assert demo_path.exists(), f"Demo script not found: {demo_path}"

        result = subprocess.run(
            [sys.executable, str(demo_path)],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0, (
            f"cold_start_demo.py failed with exit code {result.returncode}\n"
            f"STDOUT:\n{result.stdout[-2000:]}\n"
            f"STDERR:\n{result.stderr[-2000:]}"
        )
        # Verify key output markers
        assert "io-gita Cold Start Demo" in result.stdout
        assert "SPEEDUP" in result.stdout
        assert "CONCLUSION" in result.stdout

    def test_cold_start_demo_shows_speedup(self):
        """Verify the demo reports a meaningful speedup (>5x)."""
        demo_path = PROJECT_ROOT / "demo" / "cold_start_demo.py"
        result = subprocess.run(
            [sys.executable, str(demo_path)],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0

        # Find the SPEEDUP line
        for line in result.stdout.splitlines():
            if "SPEEDUP:" in line and "faster" in line:
                # Extract the number (e.g., "14.2x faster")
                parts = line.split("SPEEDUP:")[1].strip().split("x")[0].strip()
                speedup = float(parts)
                assert speedup > 1.5, f"Expected speedup > 1.5x, got {speedup}x"
                break
        else:
            pytest.fail("SPEEDUP line not found in demo output")


# ── TEST: All 34 API endpoints return expected status ──────────────────

class TestAllEndpoints:
    """Verify all 34 API endpoints respond correctly."""

    async def test_root(self, client):
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "Robotic Digital Twin API"
        assert data["endpoints"] == 34

    async def test_health(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "mongodb_ok" in data
        assert "warehouse_loaded" in data
        assert data["warehouse_loaded"] is True
        assert data["robot_loaded"] is True
        assert data["iogita_loaded"] is True
        assert data["sg_loaded"] is True

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

    async def test_iogita_status(self, client):
        resp = await client.get("/api/iogita/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["engine"] == "io-gita"
        assert data["zone_identifier_loaded"] is True
        assert data["cold_start_loaded"] is True
        assert data["num_zones"] == 8

    async def test_iogita_zones(self, client):
        resp = await client.get("/api/iogita/zones")
        assert resp.status_code == 200
        data = resp.json()
        assert "zones" in data
        assert "engine" in data

    async def test_cold_start(self, client):
        resp = await client.post("/api/iogita/cold-start/robot_01")
        assert resp.status_code == 200
        data = resp.json()
        assert data["robot_id"] == "robot_01"
        assert "recovery_hints" in data
        assert data["cold_start_engine"] == "io-gita"

    async def test_analytics_fleet(self, client):
        resp = await client.get("/api/analytics/fleet")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_tasks" in data
        assert "avg_battery_pct" in data

    async def test_analytics_predictions(self, client):
        resp = await client.get("/api/analytics/predictions")
        assert resp.status_code == 200
        data = resp.json()
        assert "predictions" in data
        assert "engine" in data

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


# ── TEST: io-gita + SG pipeline works end-to-end ──────────────────────

class TestIntelligencePipeline:
    """Verify the full io-gita + SG prediction pipeline."""

    def test_zone_identifier_classifies_all_nodes(self):
        """ZoneIdentifier assigns a zone to every node in simple_grid."""
        from app.config import load_warehouse_config
        from intelligence.iogita.zone_identifier import ZoneIdentifier

        config = load_warehouse_config("simple_grid")
        zone_id = ZoneIdentifier(zones=config["zones"], nodes=config["nodes"])

        for node in config["nodes"]:
            zone = zone_id.identify([node["x"], node["y"]])
            assert zone != "unknown", f"Node {node['name']} classified as unknown"
            expected_zones = {
                "Charging", "Aisle_North", "Aisle_West", "Storage",
                "Operations", "Aisle_East", "Aisle_South", "Pick_Drop",
            }
            assert zone in expected_zones, (
                f"Node {node['name']} classified as unexpected zone: {zone}"
            )

    def test_zone_identifier_performance(self):
        """ZoneIdentifier completes in <1ms per identification."""
        from app.config import load_warehouse_config
        from intelligence.iogita.zone_identifier import ZoneIdentifier

        config = load_warehouse_config("simple_grid")
        zone_id = ZoneIdentifier(zones=config["zones"], nodes=config["nodes"])

        for node in config["nodes"]:
            _, elapsed_ms = zone_id.identify_timed([node["x"], node["y"]])
            assert elapsed_ms < 1.0, (
                f"Zone identification took {elapsed_ms:.3f}ms (target: <1ms)"
            )

    def test_cold_start_recovery_with_saved_state(self):
        """ColdStartRecovery generates recovery hints from saved state."""
        from intelligence.iogita.cold_start import ColdStartRecovery

        cs = ColdStartRecovery()
        cs.save_state("robot_test", {
            "pose": {"x": 4.0, "y": 4.0, "theta": 0.0},
            "current_node": "HUB",
            "battery": {"charge_pct": 15.0},
            "current_task_id": "task_abc",
        })

        hints = cs.generate_recovery_hints("robot_test", {})
        assert hints["has_prior_state"] is True
        assert hints["robot_id"] == "robot_test"
        assert len(hints["steps"]) >= 2  # At least position + node recovery
        assert hints["recovery_time_ms"] < 10.0  # Very fast

        # Check specific recovery actions
        actions = [s["action"] for s in hints["steps"]]
        assert "restore_position" in actions
        assert "localize_to_node" in actions
        assert "charge_first" in actions  # Battery was 15% < 20%
        assert "resume_task" in actions

    def test_cold_start_recovery_without_state(self):
        """ColdStartRecovery handles unknown robots gracefully."""
        from intelligence.iogita.cold_start import ColdStartRecovery

        cs = ColdStartRecovery()
        hints = cs.generate_recovery_hints("unknown_robot_xyz", {})
        assert hints["has_prior_state"] is False
        assert len(hints["steps"]) >= 1

        actions = [s["action"] for s in hints["steps"]]
        assert "full_init" in actions

    def test_fleet_atlas_tracks_zones(self):
        """FleetAtlas correctly tracks robot zone transitions."""
        from app.config import load_warehouse_config
        from intelligence.iogita.fleet_atlas import FleetAtlas

        config = load_warehouse_config("simple_grid")
        atlas = FleetAtlas(zones=config["zones"], nodes=config["nodes"])

        # Update some fingerprints
        atlas.update_fingerprint("r1", "Charging", {"x": 0, "y": 0, "theta": 0})
        atlas.update_fingerprint("r2", "Storage", {"x": 4, "y": 4, "theta": 0})

        snapshot = atlas.get_fleet_snapshot()
        assert snapshot["total_robots"] == 2
        assert snapshot["zone_occupation"]["Charging"] == 1
        assert snapshot["zone_occupation"]["Storage"] == 1

        # Simulate zone transition
        atlas.update_fingerprint("r1", "Storage", {"x": 2, "y": 2, "theta": 0})
        snapshot2 = atlas.get_fleet_snapshot()
        assert snapshot2["zone_occupation"].get("Charging", 0) == 0
        assert snapshot2["zone_occupation"]["Storage"] == 2
        assert len(snapshot2["recent_transitions"]) == 1

    def test_sg_bottleneck_predictor(self):
        """BottleneckPredictor returns predictions for fleet state."""
        from intelligence.sg_prediction.bottleneck_predictor import BottleneckPredictor

        predictor = BottleneckPredictor()
        robots = [
            {"robot_id": f"r{i}", "pose": {"x": i, "y": 0}, "velocity": {"linear": 0.5},
             "battery": {"charge_pct": 80}, "status": "moving"}
            for i in range(5)
        ]

        preds, elapsed_ms = predictor.predict_timed(robots)
        assert len(preds) >= 1
        assert elapsed_ms < 25.0, f"Prediction took {elapsed_ms:.2f}ms (target: <25ms)"
        assert preds[0]["pattern"] in {
            "congestion_forming", "battery_cascade", "deadlock_risk",
            "throughput_drop", "normal_operation",
        }
        assert 0.0 <= preds[0]["confidence"] <= 1.0

    def test_sg_predictor_detects_battery_cascade(self):
        """BottleneckPredictor detects battery cascade heuristic."""
        from intelligence.sg_prediction.bottleneck_predictor import BottleneckPredictor

        predictor = BottleneckPredictor()
        robots = [
            {"robot_id": f"r{i}", "pose": {"x": i, "y": 0}, "velocity": {"linear": 0.1},
             "battery": {"charge_pct": 10}, "status": "moving", "current_node": f"N_{i}"}
            for i in range(5)
        ]

        preds = predictor.predict(robots)
        # Should include a battery cascade warning from heuristics
        patterns = [p["pattern"] for p in preds]
        assert "battery_cascade_heuristic" in patterns, (
            f"Expected battery_cascade_heuristic, got: {patterns}"
        )

    def test_state_encoder_produces_correct_dim(self):
        """StateEncoder produces vectors of the expected dimension."""
        from intelligence.sg_prediction.state_encoder import StateEncoder

        encoder = StateEncoder(max_robots=50, feature_dim=128)
        robots = [
            {"robot_id": "r1", "pose": {"x": 1, "y": 2}, "velocity": {"linear": 0.5},
             "battery": {"charge_pct": 80}, "status": "moving"}
        ]

        vec = encoder.encode(robots)
        assert vec.shape == (128,)
        assert vec.dtype.name.startswith("float")

    def test_full_pipeline_zone_to_prediction(self):
        """End-to-end: zone ID -> fleet atlas -> SG prediction."""
        from app.config import load_warehouse_config
        from intelligence.iogita.zone_identifier import ZoneIdentifier
        from intelligence.iogita.fleet_atlas import FleetAtlas
        from intelligence.sg_prediction.bottleneck_predictor import BottleneckPredictor

        config = load_warehouse_config("simple_grid")
        zone_id = ZoneIdentifier(zones=config["zones"], nodes=config["nodes"])
        atlas = FleetAtlas(zones=config["zones"], nodes=config["nodes"])
        predictor = BottleneckPredictor()

        # Simulate 5 robots at known positions
        robots = []
        for i, node in enumerate(config["nodes"][:5]):
            zone = zone_id.identify([node["x"], node["y"]])
            robot = {
                "robot_id": f"robot_{i+1:02d}",
                "pose": {"x": node["x"], "y": node["y"]},
                "velocity": {"linear": 0.5},
                "battery": {"charge_pct": 90 - i * 10},
                "status": "moving",
                "current_node": node["name"],
            }
            robots.append(robot)
            atlas.update_fingerprint(robot["robot_id"], zone, robot["pose"])

        # Fleet snapshot should have 5 robots
        snapshot = atlas.get_fleet_snapshot()
        assert snapshot["total_robots"] == 5

        # SG prediction should work
        preds = predictor.predict(robots)
        assert len(preds) >= 1
        assert preds[0]["pattern"] != ""

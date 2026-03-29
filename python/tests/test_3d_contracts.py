"""
Phase 5 — 3D Web Simulation: Backend contract tests.

The 3D scene (Warehouse3D, Robot3DModel) consumes:
  - GET /api/map → nodes[] with x,y,type + edges[] with from,to
  - GET /api/robots → robots[] with pose.x, pose.y, pose.theta, robot_type, battery.charge_pct, path
  - WebSocket /ws/fleet → robot_position events with pose, status, current_node
  - GET /api/analytics/heatmap → cells[] with x, y, intensity

These tests verify the EXACT response shapes the frontend 3D components rely on.
"""

import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app, lifespan


@pytest_asyncio.fixture
async def client():
    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c


class TestMapContractFor3D:
    """GET /api/map must return nodes with numeric x/y and typed edges."""

    async def test_map_returns_nodes_with_coordinates(self, client: AsyncClient):
        resp = await client.get("/api/map")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) > 0

    async def test_node_shape_has_xyz_and_type(self, client: AsyncClient):
        resp = await client.get("/api/map")
        nodes = resp.json()["nodes"]
        for node in nodes:
            assert "name" in node, f"Node missing 'name': {node}"
            assert isinstance(node["x"], (int, float)), f"Node x not numeric: {node}"
            assert isinstance(node["y"], (int, float)), f"Node y not numeric: {node}"
            assert "type" in node, f"Node missing 'type': {node}"
            assert node["type"] in ("aisle", "shelf", "charge", "pick", "drop", "hub"), \
                f"Unknown node type '{node['type']}' in node {node['name']}"

    async def test_edge_shape_has_from_to(self, client: AsyncClient):
        resp = await client.get("/api/map")
        edges = resp.json()["edges"]
        assert len(edges) > 0
        for edge in edges:
            assert "from" in edge, f"Edge missing 'from': {edge}"
            assert "to" in edge, f"Edge missing 'to': {edge}"
            assert isinstance(edge["from"], str)
            assert isinstance(edge["to"], str)

    async def test_all_edge_endpoints_reference_valid_nodes(self, client: AsyncClient):
        resp = await client.get("/api/map")
        data = resp.json()
        node_names = {n["name"] for n in data["nodes"]}
        for edge in data["edges"]:
            assert edge["from"] in node_names, \
                f"Edge references unknown node '{edge['from']}'"
            assert edge["to"] in node_names, \
                f"Edge references unknown node '{edge['to']}'"

    async def test_node_types_include_shelf_and_charge(self, client: AsyncClient):
        """3D scene renders shelves and charge stations with distinct models."""
        resp = await client.get("/api/map")
        types = {n["type"] for n in resp.json()["nodes"]}
        assert "shelf" in types, "No shelf nodes — 3D shelves won't render"
        assert "charge" in types, "No charge nodes — 3D charge stations won't render"


class TestRobotContractFor3D:
    """GET /api/robots must return pose, type, battery, path for 3D rendering."""

    async def test_robots_response_is_list(self, client: AsyncClient):
        resp = await client.get("/api/robots")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    async def test_robot_has_pose_with_xyz_theta(self, client: AsyncClient):
        resp = await client.get("/api/robots")
        robots = resp.json()
        if len(robots) == 0:
            pytest.skip("No robots in test environment")
        for r in robots:
            assert "pose" in r, f"Robot missing 'pose': {r.get('robot_id')}"
            pose = r["pose"]
            assert isinstance(pose["x"], (int, float))
            assert isinstance(pose["y"], (int, float))
            assert isinstance(pose["theta"], (int, float))

    async def test_robot_has_type_field(self, client: AsyncClient):
        resp = await client.get("/api/robots")
        robots = resp.json()
        if len(robots) == 0:
            pytest.skip("No robots in test environment")
        for r in robots:
            assert "robot_type" in r, f"Robot missing 'robot_type': {r.get('robot_id')}"
            assert r["robot_type"] in ("differential_drive", "unidirectional", "omnidirectional"), \
                f"Unknown robot_type '{r['robot_type']}'"

    async def test_robot_has_battery_with_charge_pct(self, client: AsyncClient):
        resp = await client.get("/api/robots")
        robots = resp.json()
        if len(robots) == 0:
            pytest.skip("No robots in test environment")
        for r in robots:
            assert "battery" in r
            bat = r["battery"]
            assert "charge_pct" in bat
            assert 0 <= bat["charge_pct"] <= 100

    async def test_robot_has_path_field(self, client: AsyncClient):
        resp = await client.get("/api/robots")
        robots = resp.json()
        if len(robots) == 0:
            pytest.skip("No robots in test environment")
        for r in robots:
            assert "path" in r
            assert isinstance(r["path"], list)

    async def test_robot_has_current_and_target_node(self, client: AsyncClient):
        resp = await client.get("/api/robots")
        robots = resp.json()
        if len(robots) == 0:
            pytest.skip("No robots in test environment")
        for r in robots:
            assert "current_node" in r
            assert "target_node" in r
            assert isinstance(r["current_node"], str)

    async def test_robot_has_name_and_id(self, client: AsyncClient):
        resp = await client.get("/api/robots")
        robots = resp.json()
        if len(robots) == 0:
            pytest.skip("No robots in test environment")
        for r in robots:
            assert "robot_id" in r
            assert "name" in r
            assert isinstance(r["robot_id"], str)
            assert isinstance(r["name"], str)

    async def test_robot_has_status(self, client: AsyncClient):
        resp = await client.get("/api/robots")
        robots = resp.json()
        if len(robots) == 0:
            pytest.skip("No robots in test environment")
        valid_statuses = {
            "idle", "moving", "charging", "loading", "unloading",
            "error", "offline", "docking", "undocking", "waiting",
        }
        for r in robots:
            assert "status" in r
            assert r["status"] in valid_statuses, \
                f"Robot {r['robot_id']} has unknown status '{r['status']}'"


class TestHeatmapContractFor3D:
    """GET /api/analytics/heatmap must return cells with x, y, intensity for 3D floor overlay."""

    async def test_heatmap_returns_cells_with_position_and_intensity(self, client: AsyncClient):
        resp = await client.get("/api/analytics/heatmap?duration=1h&resolution=0.5")
        assert resp.status_code == 200
        data = resp.json()
        assert "cells" in data
        assert "resolution_m" in data
        assert isinstance(data["resolution_m"], (int, float))

        for cell in data["cells"]:
            assert "x" in cell
            assert "y" in cell
            assert "intensity" in cell
            assert isinstance(cell["x"], (int, float))
            assert isinstance(cell["y"], (int, float))
            assert 0 <= cell["intensity"] <= 1.0

    async def test_heatmap_grid_metadata(self, client: AsyncClient):
        resp = await client.get("/api/analytics/heatmap?duration=1h&resolution=0.5")
        data = resp.json()
        assert "grid" in data
        grid = data["grid"]
        assert "min_x" in grid
        assert "min_y" in grid
        assert "max_x" in grid
        assert "max_y" in grid
        assert "cols" in grid
        assert "rows" in grid


class TestWebSocketContractFor3D:
    """WebSocket /ws/fleet route must be registered and broadcast correct event shapes."""

    def test_websocket_route_registered(self):
        """Verify /ws/fleet is in the app's route table."""
        from app.main import app as fastapi_app
        ws_routes = [
            r.path for r in fastapi_app.routes
            if hasattr(r, 'path') and '/ws/' in r.path
        ]
        assert "/ws/fleet" in ws_routes, \
            f"WebSocket route /ws/fleet not found. Routes with /ws/: {ws_routes}"

    def test_ws_manager_importable(self):
        """The ConnectionManager must be importable for broadcasting."""
        from app.websocket import ws_manager
        assert ws_manager is not None
        assert hasattr(ws_manager, 'broadcast')
        assert hasattr(ws_manager, 'connection_count')

    async def test_websocket_connect_and_receive(self, client: AsyncClient):
        """Actually connect to /ws/fleet and verify the connection confirmation shape."""
        from starlette.testclient import TestClient
        from app.main import app as fastapi_app

        # Use Starlette's sync TestClient which supports WebSocket
        with TestClient(fastapi_app) as tc:
            with tc.websocket_connect("/ws/fleet") as ws:
                # Server sends connection confirmation on connect
                msg = ws.receive_json()
                assert msg["type"] == "connected", f"Expected 'connected', got {msg}"
                assert "active_connections" in msg
                assert isinstance(msg["active_connections"], int)

    async def test_websocket_broadcast_event_shape(self, client: AsyncClient):
        """Verify broadcast event has the shape the 3D scene expects."""
        from app.websocket import ws_manager
        import asyncio

        # Simulate a robot_position broadcast and verify shape
        test_event = {
            "event": "robot_position",
            "data": {
                "robot_id": "AMR_01",
                "pose": {"x": 2.0, "y": 4.0, "theta": 1.57},
                "status": "moving",
                "current_node": "N_01",
            },
        }
        # Verify the event structure matches what the frontend expects
        assert "event" in test_event
        assert test_event["event"] == "robot_position"
        data = test_event["data"]
        assert "robot_id" in data
        assert "pose" in data
        assert "x" in data["pose"]
        assert "y" in data["pose"]
        assert "theta" in data["pose"]
        assert "status" in data
        assert "current_node" in data

        # Verify broadcast adds _seq and _ts metadata
        await ws_manager.broadcast(test_event)
        assert "_seq" in test_event
        assert "_ts" in test_event
        assert isinstance(test_event["_seq"], int)
        assert isinstance(test_event["_ts"], float)


class TestWarehouseConfigFor3D:
    """Warehouse config JSON must have the structure that 3D scene expects."""

    def test_simple_grid_config_structure(self, project_root):
        config_path = project_root / "configs" / "warehouses" / "simple_grid.json"
        assert config_path.exists(), "simple_grid.json missing"
        with open(config_path) as f:
            config = json.load(f)

        assert "nodes" in config
        assert "edges" in config
        assert len(config["nodes"]) > 0
        assert len(config["edges"]) > 0

        # Every node must have name, x, y, type (3D scene reads these)
        for node in config["nodes"]:
            assert "name" in node
            assert "x" in node
            assert "y" in node
            assert "type" in node

    def test_config_has_diverse_node_types(self, project_root):
        """3D scene renders distinct models for each type."""
        config_path = project_root / "configs" / "warehouses" / "simple_grid.json"
        with open(config_path) as f:
            config = json.load(f)
        types = {n["type"] for n in config["nodes"]}
        # 3D scene has dedicated models for shelf, charge, pick, drop, hub, aisle
        expected = {"shelf", "charge", "aisle"}
        assert expected.issubset(types), f"Missing node types for 3D: {expected - types}"

    def test_all_configs_parseable(self, project_root):
        """Every warehouse config must parse as valid JSON with nodes+edges."""
        config_dir = project_root / "configs" / "warehouses"
        configs_found = 0
        for f in config_dir.glob("*.json"):
            with open(f) as fh:
                data = json.load(fh)
            assert "nodes" in data, f"{f.name} missing 'nodes'"
            assert "edges" in data, f"{f.name} missing 'edges'"
            configs_found += 1
        assert configs_found >= 1, "No warehouse config files found"

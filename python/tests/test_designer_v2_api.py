"""
API tests for Phase 15 — Warehouse Designer v2 endpoints.

Endpoints under test:
  POST /api/designer/import             — import warehouse JSON into editor format
  POST /api/designer/validate-3d        — validate 3D layout with conveyor paths
  POST /api/designer/export-all         — export warehouse + conveyor + fleet
  GET  /api/designer/templates/categories — list template categories

15+ tests with AsyncClient via ASGI transport.
Tests actual status codes, response structure, and Pydantic validation.
"""

import json
import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from app.main import app, lifespan


@pytest_asyncio.fixture
async def client():
    """Async test client with lifespan."""
    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def simple_grid_config(project_root) -> dict:
    """Load simple_grid.json as a reference valid config."""
    config_path = project_root / "configs" / "warehouses" / "simple_grid.json"
    with open(config_path) as f:
        return json.load(f)


@pytest.fixture
def minimal_valid_config() -> dict:
    """Minimal valid warehouse config (3 nodes, 2 edges)."""
    return {
        "name": "Minimal",
        "nodes": [
            {"name": "DOCK_1", "x": 0, "y": 0, "type": "charge"},
            {"name": "PICK_1", "x": 2, "y": 0, "type": "pick"},
            {"name": "DROP_1", "x": 4, "y": 0, "type": "drop"},
        ],
        "edges": [
            {"from": "DOCK_1", "to": "PICK_1"},
            {"from": "PICK_1", "to": "DROP_1"},
        ],
        "zones": [],
        "grid_spacing_m": 2.0,
    }


@pytest.fixture
def conveyor_waypoints() -> list:
    """Simple 3-point conveyor path."""
    return [
        {"x": 0, "y": 0},
        {"x": 5, "y": 0},
        {"x": 10, "y": 0},
    ]


# ══════════════════════════════════════════════════════════════════
# GET /api/designer/templates/categories
# ══════════════════════════════════════════════════════════════════


class TestTemplateCategoriesEndpoint:
    """GET /api/designer/templates/categories — list template categories."""

    async def test_returns_categories(self, client: AsyncClient):
        resp = await client.get("/api/designer/templates/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # Should have small, medium, large, addverb categories
        category_names = {c["category"] for c in data}
        assert "small" in category_names
        assert "medium" in category_names
        assert "large" in category_names
        assert "addverb" in category_names

    async def test_categories_have_labels(self, client: AsyncClient):
        resp = await client.get("/api/designer/templates/categories")
        data = resp.json()
        for cat in data:
            assert "label" in cat
            assert "templates" in cat
            assert isinstance(cat["templates"], list)

    async def test_templates_have_node_counts(self, client: AsyncClient):
        resp = await client.get("/api/designer/templates/categories")
        data = resp.json()
        for cat in data:
            for tpl in cat["templates"]:
                assert "name" in tpl
                assert "node_count" in tpl
                assert isinstance(tpl["node_count"], int)

    async def test_addverb_category_has_addverb_template(self, client: AsyncClient):
        resp = await client.get("/api/designer/templates/categories")
        data = resp.json()
        addverb_cat = next(c for c in data if c["category"] == "addverb")
        names = [t["name"] for t in addverb_cat["templates"]]
        assert any("addverb" in n.lower() for n in names)


# ══════════════════════════════════════════════════════════════════
# POST /api/designer/import
# ══════════════════════════════════════════════════════════════════


class TestImportEndpoint:
    """POST /api/designer/import — import warehouse JSON into editor format."""

    async def test_import_valid_config(self, client: AsyncClient, simple_grid_config):
        resp = await client.post(
            "/api/designer/import",
            json={"config": simple_grid_config},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == simple_grid_config["name"]
        assert len(data["nodes"]) == 25
        assert len(data["edges"]) == 40
        assert "validation" in data
        assert data["validation"]["valid"] is True
        assert "connectivity" in data
        assert data["connectivity"]["connected"] is True
        assert "metrics" in data
        assert data["metrics"]["total_nodes"] == 25

    async def test_import_auto_detects_zones(self, client: AsyncClient, minimal_valid_config):
        # Remove zones from config
        minimal_valid_config["zones"] = []
        resp = await client.post(
            "/api/designer/import",
            json={"config": minimal_valid_config},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Auto-detected zones should be present
        assert len(data["zones"]) >= 1

    async def test_import_empty_config_rejected(self, client: AsyncClient):
        resp = await client.post(
            "/api/designer/import",
            json={"config": {"nodes": [], "edges": []}},
        )
        assert resp.status_code == 400

    async def test_import_too_many_nodes_rejected(self, client: AsyncClient):
        nodes = [
            {"name": f"N_{i}", "x": i % 50, "y": i // 50, "type": "aisle"}
            for i in range(501)
        ]
        resp = await client.post(
            "/api/designer/import",
            json={"config": {"nodes": nodes, "edges": []}},
        )
        assert resp.status_code == 400

    async def test_import_returns_metrics(self, client: AsyncClient, simple_grid_config):
        resp = await client.post(
            "/api/designer/import",
            json={"config": simple_grid_config},
        )
        data = resp.json()
        metrics = data["metrics"]
        assert metrics["total_nodes"] == 25
        assert metrics["total_edges"] == 40
        assert metrics["charge_station_count"] == 2
        assert metrics["total_area_m2"] == 64.0


# ══════════════════════════════════════════════════════════════════
# POST /api/designer/validate-3d
# ══════════════════════════════════════════════════════════════════


class TestValidate3DEndpoint:
    """POST /api/designer/validate-3d — validate 3D layout with conveyor paths."""

    async def test_validate_3d_valid_config(
        self, client: AsyncClient, simple_grid_config, conveyor_waypoints
    ):
        resp = await client.post(
            "/api/designer/validate-3d",
            json={
                "config": simple_grid_config,
                "conveyor_waypoints": conveyor_waypoints,
                "fleet_size": 5,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["warehouse_validation"]["valid"] is True
        assert data["connectivity"]["connected"] is True
        assert data["conveyor_validation"]["valid"] is True
        assert data["charge_suggestions"]["recommended_count"] == 2
        assert data["metrics"]["total_nodes"] == 25

    async def test_validate_3d_no_conveyor(self, client: AsyncClient, simple_grid_config):
        resp = await client.post(
            "/api/designer/validate-3d",
            json={
                "config": simple_grid_config,
                "conveyor_waypoints": [],
                "fleet_size": 3,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["conveyor_validation"]["valid"] is True  # no conveyor = valid

    async def test_validate_3d_invalid_warehouse(self, client: AsyncClient):
        bad_config = {
            "name": "Bad",
            "nodes": [{"name": "A", "x": 0, "y": 0, "type": "aisle"}],
            "edges": [],
        }
        resp = await client.post(
            "/api/designer/validate-3d",
            json={"config": bad_config, "fleet_size": 2},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert data["warehouse_validation"]["valid"] is False

    async def test_validate_3d_too_many_nodes(self, client: AsyncClient):
        nodes = [
            {"name": f"N_{i}", "x": i, "y": 0, "type": "aisle"}
            for i in range(501)
        ]
        resp = await client.post(
            "/api/designer/validate-3d",
            json={"config": {"nodes": nodes, "edges": []}, "fleet_size": 1},
        )
        assert resp.status_code == 400


# ══════════════════════════════════════════════════════════════════
# POST /api/designer/export-all
# ══════════════════════════════════════════════════════════════════


class TestExportAllEndpoint:
    """POST /api/designer/export-all — export combined package."""

    async def test_export_all_saves_files(
        self, client: AsyncClient, project_root, simple_grid_config, conveyor_waypoints
    ):
        export_name = "test_export_all_v2"
        resp = await client.post(
            "/api/designer/export-all",
            json={
                "name": export_name,
                "config": simple_grid_config,
                "conveyor_waypoints": conveyor_waypoints,
                "fleet_size": 5,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["saved"] is True
        assert len(data["files"]) == 3  # warehouse + conveyor + fleet
        assert data["node_count"] == 25
        assert data["conveyor_segments"] == 2  # 3 waypoints -> 2 segments
        assert data["fleet_size"] == 5

        # Verify files exist
        wh_path = project_root / "configs" / "warehouses" / f"{export_name}.json"
        conv_path = project_root / "configs" / "wcs" / f"{export_name}_conveyor.yaml"
        fleet_path = project_root / "configs" / "fleet" / f"{export_name}_fleet.json"

        assert wh_path.exists()
        assert conv_path.exists()
        assert fleet_path.exists()

        # Verify content
        with open(wh_path) as f:
            saved_wh = json.load(f)
        assert len(saved_wh["nodes"]) == 25

        with open(fleet_path) as f:
            saved_fleet = json.load(f)
        assert saved_fleet["fleet_size"] == 5

        # Cleanup: move to trash
        trash_dir = project_root / "configs" / "warehouses" / "_trash"
        trash_dir.mkdir(exist_ok=True)
        wh_path.rename(trash_dir / f"{export_name}.json")

        trash_wcs = project_root / "configs" / "wcs" / "_trash"
        trash_wcs.mkdir(exist_ok=True)
        conv_path.rename(trash_wcs / f"{export_name}_conveyor.yaml")

        trash_fleet = project_root / "configs" / "fleet" / "_trash"
        trash_fleet.mkdir(exist_ok=True)
        fleet_path.rename(trash_fleet / f"{export_name}_fleet.json")

    async def test_export_all_invalid_name_rejected(
        self, client: AsyncClient, simple_grid_config
    ):
        resp = await client.post(
            "/api/designer/export-all",
            json={
                "name": "bad name with spaces!",
                "config": simple_grid_config,
                "fleet_size": 3,
            },
        )
        assert resp.status_code == 400

    async def test_export_all_invalid_config_rejected(self, client: AsyncClient):
        bad_config = {
            "name": "Bad",
            "nodes": [{"name": "A", "x": 0, "y": 0, "type": "aisle"}],
            "edges": [],
        }
        resp = await client.post(
            "/api/designer/export-all",
            json={"name": "bad_config_test", "config": bad_config, "fleet_size": 1},
        )
        assert resp.status_code == 400

    async def test_export_all_requires_auth_when_enabled(
        self, client: AsyncClient, simple_grid_config, monkeypatch
    ):
        monkeypatch.setenv("API_KEY", "secret-key-456")
        resp = await client.post(
            "/api/designer/export-all",
            json={
                "name": "auth_test_v2",
                "config": simple_grid_config,
                "fleet_size": 2,
            },
        )
        assert resp.status_code == 403

    async def test_export_all_no_conveyor_saves_two_files(
        self, client: AsyncClient, project_root, simple_grid_config
    ):
        export_name = "test_export_noconv"
        resp = await client.post(
            "/api/designer/export-all",
            json={
                "name": export_name,
                "config": simple_grid_config,
                "conveyor_waypoints": [],
                "fleet_size": 3,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["saved"] is True
        # No conveyor waypoints -> only warehouse + fleet = 2 files
        assert len(data["files"]) == 2
        assert data["conveyor_segments"] == 0

        # Cleanup
        wh_path = project_root / "configs" / "warehouses" / f"{export_name}.json"
        fleet_path = project_root / "configs" / "fleet" / f"{export_name}_fleet.json"

        trash_dir = project_root / "configs" / "warehouses" / "_trash"
        trash_dir.mkdir(exist_ok=True)
        if wh_path.exists():
            wh_path.rename(trash_dir / f"{export_name}.json")

        trash_fleet = project_root / "configs" / "fleet" / "_trash"
        trash_fleet.mkdir(exist_ok=True)
        if fleet_path.exists():
            fleet_path.rename(trash_fleet / f"{export_name}_fleet.json")


# ══════════════════════════════════════════════════════════════════
# UPDATED ENDPOINT COUNT
# ══════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════
# POST /api/designer/auto-edges
# ══════════════════════════════════════════════════════════════════


class TestAutoEdgesEndpoint:
    """POST /api/designer/auto-edges — auto-generate edges between nearby nodes."""

    async def test_auto_edges_basic(self, client: AsyncClient):
        nodes = [
            {"name": "A", "x": 0, "y": 0},
            {"name": "B", "x": 2, "y": 0},
            {"name": "C", "x": 10, "y": 10},
        ]
        resp = await client.post(
            "/api/designer/auto-edges",
            json={"nodes": nodes, "max_distance": 3.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["edge_count"] == 1  # only A-B within 3m
        assert data["node_count"] == 3
        assert data["max_distance"] == 3.0
        assert len(data["edges"]) == 1
        assert data["edges"][0]["from"] == "A"
        assert data["edges"][0]["to"] == "B"

    async def test_auto_edges_all_connected(self, client: AsyncClient):
        nodes = [
            {"name": "A", "x": 0, "y": 0},
            {"name": "B", "x": 1, "y": 0},
            {"name": "C", "x": 2, "y": 0},
        ]
        resp = await client.post(
            "/api/designer/auto-edges",
            json={"nodes": nodes, "max_distance": 5.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["edge_count"] == 3  # all 3 pairs

    async def test_auto_edges_too_many_nodes(self, client: AsyncClient):
        nodes = [{"name": f"N_{i}", "x": i, "y": 0} for i in range(501)]
        resp = await client.post(
            "/api/designer/auto-edges",
            json={"nodes": nodes, "max_distance": 2.0},
        )
        assert resp.status_code == 400

    async def test_auto_edges_invalid_max_distance(self, client: AsyncClient):
        nodes = [{"name": "A", "x": 0, "y": 0}]
        resp = await client.post(
            "/api/designer/auto-edges",
            json={"nodes": nodes, "max_distance": -1.0},
        )
        assert resp.status_code == 422  # Pydantic validation: gt=0

    async def test_auto_edges_empty_nodes(self, client: AsyncClient):
        resp = await client.post(
            "/api/designer/auto-edges",
            json={"nodes": [], "max_distance": 5.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["edge_count"] == 0
        assert data["edges"] == []


# ══════════════════════════════════════════════════════════════════
# POST /api/designer/template/scale
# ══════════════════════════════════════════════════════════════════


class TestTemplateScaleEndpoint:
    """POST /api/designer/template/scale — scale template up/down."""

    async def test_scale_simple_grid(self, client: AsyncClient):
        resp = await client.post(
            "/api/designer/template/scale",
            json={"template_name": "simple_grid", "scale_factor": 2.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["template_name"] == "simple_grid"
        assert data["scale_factor"] == 2.0
        assert data["node_count"] == 25
        # Check that coordinates are doubled
        config = data["config"]
        node_map = {n["name"]: n for n in config["nodes"]}
        # HUB is at (4,4) originally, should be (8,8) at 2x
        assert node_map["HUB"]["x"] == 8.0
        assert node_map["HUB"]["y"] == 8.0

    async def test_scale_down(self, client: AsyncClient):
        resp = await client.post(
            "/api/designer/template/scale",
            json={"template_name": "simple_grid", "scale_factor": 0.5},
        )
        assert resp.status_code == 200
        data = resp.json()
        config = data["config"]
        node_map = {n["name"]: n for n in config["nodes"]}
        # HUB at (4,4) -> (2,2) at 0.5x
        assert node_map["HUB"]["x"] == 2.0
        assert node_map["HUB"]["y"] == 2.0

    async def test_scale_nonexistent_template(self, client: AsyncClient):
        resp = await client.post(
            "/api/designer/template/scale",
            json={"template_name": "nonexistent_template_xyz", "scale_factor": 1.0},
        )
        assert resp.status_code == 404

    async def test_scale_invalid_name(self, client: AsyncClient):
        resp = await client.post(
            "/api/designer/template/scale",
            json={"template_name": "bad name!", "scale_factor": 1.0},
        )
        assert resp.status_code == 400

    async def test_scale_invalid_factor(self, client: AsyncClient):
        resp = await client.post(
            "/api/designer/template/scale",
            json={"template_name": "simple_grid", "scale_factor": -1.0},
        )
        assert resp.status_code == 422  # Pydantic: gt=0


class TestUpdatedEndpointCount:
    """Root endpoint reflects the updated endpoint count (Phase 15 adds 4 + 2 new)."""

    async def test_endpoint_count_updated(self, client: AsyncClient):
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["endpoints"] == 118  # 112 + 4 Phase 15 + 2 audit fixes

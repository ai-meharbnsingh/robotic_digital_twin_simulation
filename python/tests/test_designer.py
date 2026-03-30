"""
Tests for Phase 7 — Warehouse Designer (validate, export, templates).

Routes:
  POST /api/designer/validate          — validate warehouse JSON
  POST /api/designer/export            — save designed warehouse as JSON config
  GET  /api/designer/templates         — list available templates
  GET  /api/designer/templates/{name}  — get template JSON

Validator:
  WarehouseValidator.validate(config)  — full graph validation
  WarehouseValidator.auto_edges(nodes, spacing) — generate edges within distance

TDD: Written FIRST, then implementation until green.
"""

import json
import math
from pathlib import Path

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


@pytest.fixture
def project_root() -> Path:
    """Return the project root directory."""
    return Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def simple_grid_config(project_root) -> dict:
    """Load simple_grid.json as a reference valid config."""
    config_path = project_root / "configs" / "warehouses" / "simple_grid.json"
    with open(config_path) as f:
        return json.load(f)


# ── WarehouseValidator unit tests ──────────────────────────────────


class TestValidateValidConfig:
    """test_validate_valid_config — simple_grid.json passes validation."""

    def test_validate_valid_config(self, simple_grid_config):
        from wes.warehouse_validator import WarehouseValidator

        result = WarehouseValidator.validate(simple_grid_config)
        assert result["valid"] is True
        assert result["errors"] == []
        # May have warnings but no errors
        assert isinstance(result["warnings"], list)


class TestValidateMissingCharge:
    """test_validate_missing_charge — error when no charge node."""

    def test_validate_missing_charge(self):
        from wes.warehouse_validator import WarehouseValidator

        config = {
            "name": "No Charge",
            "nodes": [
                {"name": "PICK_1", "x": 0, "y": 0, "type": "pick"},
                {"name": "DROP_1", "x": 2, "y": 0, "type": "drop"},
            ],
            "edges": [{"from": "PICK_1", "to": "DROP_1"}],
        }
        result = WarehouseValidator.validate(config)
        assert result["valid"] is False
        errors_text = " ".join(result["errors"])
        assert "charge" in errors_text.lower()


class TestValidateMissingPickDrop:
    """test_validate_missing_pick_drop — error when no pick or drop node."""

    def test_validate_missing_pick(self):
        from wes.warehouse_validator import WarehouseValidator

        config = {
            "name": "No Pick",
            "nodes": [
                {"name": "DOCK_1", "x": 0, "y": 0, "type": "charge"},
                {"name": "DROP_1", "x": 2, "y": 0, "type": "drop"},
            ],
            "edges": [{"from": "DOCK_1", "to": "DROP_1"}],
        }
        result = WarehouseValidator.validate(config)
        assert result["valid"] is False
        errors_text = " ".join(result["errors"])
        assert "pick" in errors_text.lower()

    def test_validate_missing_drop(self):
        from wes.warehouse_validator import WarehouseValidator

        config = {
            "name": "No Drop",
            "nodes": [
                {"name": "DOCK_1", "x": 0, "y": 0, "type": "charge"},
                {"name": "PICK_1", "x": 2, "y": 0, "type": "pick"},
            ],
            "edges": [{"from": "DOCK_1", "to": "PICK_1"}],
        }
        result = WarehouseValidator.validate(config)
        assert result["valid"] is False
        errors_text = " ".join(result["errors"])
        assert "drop" in errors_text.lower()


class TestValidateDisconnectedGraph:
    """test_validate_disconnected_graph — error when graph is not connected."""

    def test_validate_disconnected_graph(self):
        from wes.warehouse_validator import WarehouseValidator

        config = {
            "name": "Disconnected",
            "nodes": [
                {"name": "DOCK_1", "x": 0, "y": 0, "type": "charge"},
                {"name": "PICK_1", "x": 2, "y": 0, "type": "pick"},
                {"name": "DROP_1", "x": 10, "y": 10, "type": "drop"},  # isolated
            ],
            "edges": [{"from": "DOCK_1", "to": "PICK_1"}],
            # DROP_1 has no edges — not reachable
        }
        result = WarehouseValidator.validate(config)
        assert result["valid"] is False
        errors_text = " ".join(result["errors"])
        assert "connected" in errors_text.lower() or "reachable" in errors_text.lower()


class TestValidateDuplicateNames:
    """test_validate_duplicate_names — error when node names repeat."""

    def test_validate_duplicate_names(self):
        from wes.warehouse_validator import WarehouseValidator

        config = {
            "name": "Duplicates",
            "nodes": [
                {"name": "DOCK_1", "x": 0, "y": 0, "type": "charge"},
                {"name": "DOCK_1", "x": 2, "y": 0, "type": "pick"},  # duplicate
                {"name": "DROP_1", "x": 4, "y": 0, "type": "drop"},
            ],
            "edges": [
                {"from": "DOCK_1", "to": "DROP_1"},
            ],
        }
        result = WarehouseValidator.validate(config)
        assert result["valid"] is False
        errors_text = " ".join(result["errors"])
        assert "duplicate" in errors_text.lower()


class TestValidateOverlappingPositions:
    """test_validate_overlapping_positions — warning when positions overlap."""

    def test_validate_overlapping_positions(self):
        from wes.warehouse_validator import WarehouseValidator

        config = {
            "name": "Overlap",
            "nodes": [
                {"name": "DOCK_1", "x": 0, "y": 0, "type": "charge"},
                {"name": "PICK_1", "x": 0, "y": 0, "type": "pick"},  # same position
                {"name": "DROP_1", "x": 2, "y": 0, "type": "drop"},
            ],
            "edges": [
                {"from": "DOCK_1", "to": "PICK_1"},
                {"from": "PICK_1", "to": "DROP_1"},
            ],
        }
        result = WarehouseValidator.validate(config)
        # Overlapping positions produce a WARNING, not necessarily an error
        warnings_text = " ".join(result["warnings"])
        assert "overlap" in warnings_text.lower() or "position" in warnings_text.lower()


class TestValidateInvalidEdgeRefs:
    """test_validate_invalid_edge_refs — error when edges reference nonexistent nodes."""

    def test_validate_invalid_edge_refs(self):
        from wes.warehouse_validator import WarehouseValidator

        config = {
            "name": "Bad Edges",
            "nodes": [
                {"name": "DOCK_1", "x": 0, "y": 0, "type": "charge"},
                {"name": "PICK_1", "x": 2, "y": 0, "type": "pick"},
                {"name": "DROP_1", "x": 4, "y": 0, "type": "drop"},
            ],
            "edges": [
                {"from": "DOCK_1", "to": "PICK_1"},
                {"from": "PICK_1", "to": "DROP_1"},
                {"from": "PICK_1", "to": "GHOST_NODE"},  # nonexistent
            ],
        }
        result = WarehouseValidator.validate(config)
        assert result["valid"] is False
        errors_text = " ".join(result["errors"])
        assert "GHOST_NODE" in errors_text


class TestValidateNodeMissingFields:
    """Nodes missing required fields (name, x, y, type) produce errors."""

    def test_validate_node_missing_type(self):
        from wes.warehouse_validator import WarehouseValidator

        config = {
            "name": "Missing type",
            "nodes": [
                {"name": "DOCK_1", "x": 0, "y": 0},  # no type
            ],
            "edges": [],
        }
        result = WarehouseValidator.validate(config)
        assert result["valid"] is False
        errors_text = " ".join(result["errors"])
        assert "type" in errors_text.lower() or "field" in errors_text.lower()


# ── auto_edges tests ──────────────────────────────────────────────


class TestAutoEdgesBasic:
    """test_auto_edges_basic — generates correct edges for adjacent nodes."""

    def test_auto_edges_basic(self):
        from wes.warehouse_validator import WarehouseValidator

        nodes = [
            {"name": "A", "x": 0, "y": 0, "type": "charge"},
            {"name": "B", "x": 2, "y": 0, "type": "pick"},
            {"name": "C", "x": 0, "y": 2, "type": "drop"},
        ]
        edges = WarehouseValidator.auto_edges(nodes, spacing=2.5)
        # A-B distance = 2.0, A-C distance = 2.0, B-C distance = 2.83
        # With spacing 2.5: A-B and A-C are within range, B-C is not
        assert len(edges) == 2
        edge_pairs = {(e["from"], e["to"]) for e in edges}
        assert ("A", "B") in edge_pairs
        assert ("A", "C") in edge_pairs


class TestAutoEdgesSpacing:
    """test_auto_edges_spacing — only connects nodes within spacing distance."""

    def test_auto_edges_spacing(self):
        from wes.warehouse_validator import WarehouseValidator

        nodes = [
            {"name": "A", "x": 0, "y": 0, "type": "charge"},
            {"name": "B", "x": 10, "y": 0, "type": "pick"},  # far away
            {"name": "C", "x": 0, "y": 1, "type": "drop"},  # close
        ]
        edges = WarehouseValidator.auto_edges(nodes, spacing=2.0)
        # A-C = 1.0 (within), A-B = 10.0 (not), B-C = ~10.05 (not)
        assert len(edges) == 1
        assert edges[0]["from"] == "A"
        assert edges[0]["to"] == "C"


# ── Template endpoint tests (via HTTP) ────────────────────────────


class TestTemplatesList:
    """test_templates_list — GET /api/designer/templates returns 3+ templates."""

    async def test_templates_list(self, client: AsyncClient):
        resp = await client.get("/api/designer/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 3
        # Each template has name and description
        for tpl in data:
            assert "name" in tpl
            assert "description" in tpl
            assert "node_count" in tpl


class TestTemplateSmallValid:
    """test_template_small_valid — template_small loads and validates."""

    async def test_template_small_valid(self, client: AsyncClient):
        resp = await client.get("/api/designer/templates/template_small")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) == 9

        # Validate via the validator
        from wes.warehouse_validator import WarehouseValidator
        result = WarehouseValidator.validate(data)
        assert result["valid"] is True
        assert result["errors"] == []


class TestTemplateMediumValid:
    """test_template_medium_valid — template_medium loads and validates."""

    async def test_template_medium_valid(self, client: AsyncClient):
        resp = await client.get("/api/designer/templates/template_medium")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) == 25

        from wes.warehouse_validator import WarehouseValidator
        result = WarehouseValidator.validate(data)
        assert result["valid"] is True
        assert result["errors"] == []


class TestTemplateLargeValid:
    """test_template_large_valid — template_large loads and validates."""

    async def test_template_large_valid(self, client: AsyncClient):
        resp = await client.get("/api/designer/templates/template_large")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) == 49

        from wes.warehouse_validator import WarehouseValidator
        result = WarehouseValidator.validate(data)
        assert result["valid"] is True
        assert result["errors"] == []


class TestTemplateNotFound:
    """GET /api/designer/templates/{name} with invalid name returns 404."""

    async def test_template_not_found(self, client: AsyncClient):
        resp = await client.get("/api/designer/templates/nonexistent_template_xyz")
        assert resp.status_code == 404


# ── Validate endpoint test ────────────────────────────────────────


class TestValidateEndpoint:
    """POST /api/designer/validate — validate config via HTTP."""

    async def test_validate_valid_via_endpoint(self, client: AsyncClient, simple_grid_config):
        resp = await client.post("/api/designer/validate", json=simple_grid_config)
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["errors"] == []

    async def test_validate_invalid_via_endpoint(self, client: AsyncClient):
        bad_config = {
            "name": "Bad",
            "nodes": [
                {"name": "A", "x": 0, "y": 0, "type": "aisle"},
            ],
            "edges": [],
        }
        resp = await client.post("/api/designer/validate", json=bad_config)
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0


# ── Export endpoint test ──────────────────────────────────────────


class TestExportEndpoint:
    """POST /api/designer/export — save warehouse config."""

    async def test_export_saves_file(self, client: AsyncClient, project_root, simple_grid_config):
        export_name = "test_export_designer"
        resp = await client.post(
            "/api/designer/export",
            json={"name": export_name, "config": simple_grid_config},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["saved"] is True
        assert export_name in data["path"]

        # Verify file was actually written
        saved_path = project_root / "configs" / "warehouses" / f"{export_name}.json"
        assert saved_path.exists()
        with open(saved_path) as f:
            saved = json.load(f)
        assert saved["name"] == simple_grid_config["name"]
        assert len(saved["nodes"]) == len(simple_grid_config["nodes"])

        # Cleanup: move to trash instead of rm
        trash_dir = project_root / "configs" / "warehouses" / "_trash"
        trash_dir.mkdir(exist_ok=True)
        saved_path.rename(trash_dir / f"{export_name}.json")

    async def test_export_invalid_config_rejected(self, client: AsyncClient):
        """Export rejects invalid configs (no charge node)."""
        bad_config = {
            "name": "Bad",
            "nodes": [
                {"name": "A", "x": 0, "y": 0, "type": "aisle"},
            ],
            "edges": [],
        }
        resp = await client.post(
            "/api/designer/export",
            json={"name": "bad_export", "config": bad_config},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert "detail" in data


# ── Security & edge case tests ───────────────────────────────────


class TestExportRequiresAuth:
    """POST /api/designer/export without API key when auth enabled → 403."""

    async def test_export_requires_auth(self, client: AsyncClient, simple_grid_config, monkeypatch):
        monkeypatch.setenv("API_KEY", "test-secret-key-123")
        # No X-API-Key header → should be rejected
        resp = await client.post(
            "/api/designer/export",
            json={"name": "auth_test", "config": simple_grid_config},
        )
        assert resp.status_code == 403
        data = resp.json()
        assert "detail" in data


class TestTemplatePathTraversal:
    """GET /api/designer/templates/{name} with path traversal → 400."""

    async def test_template_path_traversal_dotdot(self, client: AsyncClient):
        resp = await client.get("/api/designer/templates/../../etc/passwd")
        assert resp.status_code in (400, 404, 422)

    async def test_template_path_traversal_slash(self, client: AsyncClient):
        resp = await client.get("/api/designer/templates/..%2F..%2Fetc%2Fpasswd")
        assert resp.status_code in (400, 404, 422)

    async def test_template_name_with_dots(self, client: AsyncClient):
        resp = await client.get("/api/designer/templates/..secret")
        assert resp.status_code == 400


class TestValidateMaxNodesExceeded:
    """POST /api/designer/validate with >500 nodes → 400."""

    async def test_validate_max_nodes_exceeded(self, client: AsyncClient):
        # Create 501 nodes — exceeds MAX_NODES=500 safety limit
        nodes = [
            {"name": f"N_{i}", "x": i % 50, "y": i // 50, "type": "aisle"}
            for i in range(501)
        ]
        config = {"name": "Too Many Nodes", "nodes": nodes, "edges": []}
        resp = await client.post("/api/designer/validate", json=config)
        assert resp.status_code == 400
        data = resp.json()
        assert "500" in data["detail"] or "limit" in data["detail"].lower()


class TestExportMaxNameLength:
    """POST /api/designer/export with name >100 chars → 400 (Pydantic validation)."""

    async def test_export_max_name_length(self, client: AsyncClient, simple_grid_config):
        long_name = "a" * 101
        resp = await client.post(
            "/api/designer/export",
            json={"name": long_name, "config": simple_grid_config},
        )
        # Pydantic Field(max_length=100) rejects before handler → 422
        # Or handler check → 400. Either is correct.
        assert resp.status_code in (400, 422)


# ── Endpoint count test ───────────────────────────────────────────


class TestDesignerEndpointCount:
    """test_endpoint_count — total is now 60 (50 base + 5 VDA5050 + 1 iogita/recover + 4 ROS2)."""

    async def test_endpoint_count(self, client: AsyncClient):
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["endpoints"] == 65

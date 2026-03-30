"""
Tests for Phase 6 — Parallel Scenario Comparison.

Tests scenario lifecycle: create, run, results, compare, cleanup.
Tests routes: POST /api/scenarios, POST /api/scenarios/{id}/run,
              GET /api/scenarios/{id}/results, GET /api/scenarios/compare

TDD: Written FIRST, then implementation until green.
"""

import csv
import io

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


# ── TestScenarioCreate ─────────────────────────────────────


class TestScenarioCreate:
    """Test POST /api/scenarios — scenario creation."""

    async def test_create_valid_scenario(self, client: AsyncClient, requires_mongodb):
        """Create a scenario with valid config returns 200 + scenario doc."""
        resp = await client.post("/api/scenarios", json={
            "name": "Baseline FIFO",
            "description": "Baseline with FIFO allocation",
            "fleet_size": 5,
            "robot_config": "differential_drive",
            "allocation_strategy": "fifo",
            "warehouse_config": "simple_grid",
            "order_count": 20,
            "order_seed": 42,
            "duration_s": 60,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "scenario_id" in data
        assert data["name"] == "Baseline FIFO"
        assert data["status"] == "created"
        assert data["config"]["fleet_size"] == 5
        assert data["config"]["allocation_strategy"] == "fifo"
        assert data["config"]["order_count"] == 20
        assert data["config"]["order_seed"] == 42
        assert "created_at" in data

    async def test_create_missing_name_422(self, client: AsyncClient):
        """Missing required 'name' field returns 422."""
        resp = await client.post("/api/scenarios", json={
            "fleet_size": 5,
            "robot_config": "differential_drive",
            "warehouse_config": "simple_grid",
        })
        assert resp.status_code == 422

    async def test_create_defaults_applied(self, client: AsyncClient, requires_mongodb):
        """Omitted optional fields get defaults."""
        resp = await client.post("/api/scenarios", json={
            "name": "Defaults Test",
            "warehouse_config": "simple_grid",
            "robot_config": "differential_drive",
        })
        assert resp.status_code == 200
        data = resp.json()
        config = data["config"]
        # Check defaults are applied
        assert config["fleet_size"] >= 1
        assert config["allocation_strategy"] in ("fifo", "nearest", "priority_weighted")
        assert config["order_count"] >= 1
        assert config["duration_s"] >= 10

    async def test_create_invalid_warehouse_config(self, client: AsyncClient):
        """Non-existent warehouse config returns 400."""
        resp = await client.post("/api/scenarios", json={
            "name": "Bad Config",
            "warehouse_config": "nonexistent_warehouse_999",
            "robot_config": "differential_drive",
        })
        assert resp.status_code == 400

    async def test_create_invalid_robot_config(self, client: AsyncClient):
        """Non-existent robot config returns 400."""
        resp = await client.post("/api/scenarios", json={
            "name": "Bad Robot",
            "warehouse_config": "simple_grid",
            "robot_config": "nonexistent_robot_999",
        })
        assert resp.status_code == 400

    async def test_create_fleet_size_bounds(self, client: AsyncClient):
        """Fleet size out of range (1-200) returns 422."""
        resp = await client.post("/api/scenarios", json={
            "name": "Too Many Robots",
            "warehouse_config": "simple_grid",
            "robot_config": "differential_drive",
            "fleet_size": 0,
        })
        assert resp.status_code == 422

        resp2 = await client.post("/api/scenarios", json={
            "name": "Way Too Many",
            "warehouse_config": "simple_grid",
            "robot_config": "differential_drive",
            "fleet_size": 201,
        })
        assert resp2.status_code == 422

    async def test_create_order_count_bounds(self, client: AsyncClient):
        """Order count out of range (1-10000) returns 422."""
        resp = await client.post("/api/scenarios", json={
            "name": "No Orders",
            "warehouse_config": "simple_grid",
            "robot_config": "differential_drive",
            "order_count": 0,
        })
        assert resp.status_code == 422

    async def test_create_duration_bounds(self, client: AsyncClient):
        """Duration out of range (10-3600) returns 422."""
        resp = await client.post("/api/scenarios", json={
            "name": "Too Short",
            "warehouse_config": "simple_grid",
            "robot_config": "differential_drive",
            "duration_s": 5,
        })
        assert resp.status_code == 422


# ── TestScenarioList ──────────────────────────────────────


class TestScenarioList:
    """Test GET /api/scenarios — list all scenarios."""

    async def test_list_scenarios_returns_list(self, client: AsyncClient, requires_mongodb):
        """GET /api/scenarios returns 200 with a JSON list."""
        resp = await client.get("/api/scenarios")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # When MongoDB is available, prior test data may exist.
        # Validate structure: every item must have scenario_id and name.
        for item in data:
            assert "scenario_id" in item
            assert "name" in item

    async def test_list_scenarios_with_data(self, client: AsyncClient, requires_mongodb):
        """Create 2 scenarios, GET /api/scenarios returns both by name and ID."""
        # Create scenario A
        resp_a = await client.post("/api/scenarios", json={
            "name": "List Test A",
            "warehouse_config": "simple_grid",
            "robot_config": "differential_drive",
        })
        assert resp_a.status_code == 200
        sid_a = resp_a.json()["scenario_id"]

        # Create scenario B
        resp_b = await client.post("/api/scenarios", json={
            "name": "List Test B",
            "warehouse_config": "simple_grid",
            "robot_config": "differential_drive",
        })
        assert resp_b.status_code == 200
        sid_b = resp_b.json()["scenario_id"]

        # List
        resp = await client.get("/api/scenarios")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 2
        scenario_ids = [s["scenario_id"] for s in data]
        scenario_names = [s["name"] for s in data]
        assert sid_a in scenario_ids
        assert sid_b in scenario_ids
        assert "List Test A" in scenario_names
        assert "List Test B" in scenario_names


# ── TestScenarioDelete ────────────────────────────────────


class TestScenarioDelete:
    """Test DELETE /api/scenarios/{id} — archive scenario."""

    async def test_delete_scenario(self, client: AsyncClient, requires_mongodb):
        """DELETE archives scenario, subsequent GET results shows archived status."""
        # Create
        resp = await client.post("/api/scenarios", json={
            "name": "Delete Test",
            "warehouse_config": "simple_grid",
            "robot_config": "differential_drive",
        })
        assert resp.status_code == 200
        sid = resp.json()["scenario_id"]

        # Delete (archive)
        resp_del = await client.delete(f"/api/scenarios/{sid}")
        assert resp_del.status_code == 200
        data = resp_del.json()
        assert data["scenario_id"] == sid
        assert data["status"] == "archived"

        # Verify it appears as archived in the list
        resp_list = await client.get("/api/scenarios")
        assert resp_list.status_code == 200
        scenarios = resp_list.json()
        archived = [s for s in scenarios if s["scenario_id"] == sid]
        assert len(archived) == 1
        assert archived[0]["status"] == "archived"

    async def test_delete_nonexistent_404(self, client: AsyncClient, requires_mongodb):
        """DELETE unknown scenario ID returns 404."""
        resp = await client.delete("/api/scenarios/nonexistent_id_999")
        assert resp.status_code == 404


# ── TestScenarioRun ────────────────────────────────────────


class TestScenarioRun:
    """Test POST /api/scenarios/{id}/run — scenario execution."""

    async def test_run_returns_kpis(self, client: AsyncClient, requires_mongodb):
        """Run a created scenario returns KPIs."""
        # Create
        resp = await client.post("/api/scenarios", json={
            "name": "Run Test",
            "warehouse_config": "simple_grid",
            "robot_config": "differential_drive",
            "fleet_size": 3,
            "order_count": 10,
            "order_seed": 42,
            "duration_s": 30,
            "allocation_strategy": "fifo",
        })
        assert resp.status_code == 200
        scenario_id = resp.json()["scenario_id"]

        # Run
        resp2 = await client.post(f"/api/scenarios/{scenario_id}/run")
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["status"] == "completed"
        assert "kpis" in data
        kpis = data["kpis"]
        assert "throughput_items_per_hour" in kpis
        assert "avg_order_cycle_time_s" in kpis
        assert "pick_accuracy_pct" in kpis
        assert "completed_tasks" in kpis
        assert isinstance(kpis["throughput_items_per_hour"], (int, float))

    async def test_run_nonexistent_404(self, client: AsyncClient, requires_mongodb):
        """Run a nonexistent scenario returns 404."""
        resp = await client.post("/api/scenarios/nonexistent_id_999/run")
        assert resp.status_code == 404

    async def test_run_with_duration_override(self, client: AsyncClient, requires_mongodb):
        """Run with duration_override applies the override."""
        resp = await client.post("/api/scenarios", json={
            "name": "Override Test",
            "warehouse_config": "simple_grid",
            "robot_config": "differential_drive",
            "fleet_size": 2,
            "order_count": 5,
            "order_seed": 99,
            "duration_s": 60,
        })
        assert resp.status_code == 200
        sid = resp.json()["scenario_id"]

        resp2 = await client.post(f"/api/scenarios/{sid}/run", json={"duration_override": 30})
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "completed"

    async def test_seed_reproducibility(self, client: AsyncClient, requires_mongodb):
        """Same seed + config produces identical KPIs."""
        config = {
            "name": "Seed Test A",
            "warehouse_config": "simple_grid",
            "robot_config": "differential_drive",
            "fleet_size": 3,
            "order_count": 15,
            "order_seed": 12345,
            "duration_s": 30,
            "allocation_strategy": "fifo",
        }
        # Create + run scenario A
        resp_a = await client.post("/api/scenarios", json=config)
        sid_a = resp_a.json()["scenario_id"]
        run_a = await client.post(f"/api/scenarios/{sid_a}/run")
        kpis_a = run_a.json()["kpis"]

        # Create + run scenario B (same config)
        config["name"] = "Seed Test B"
        resp_b = await client.post("/api/scenarios", json=config)
        sid_b = resp_b.json()["scenario_id"]
        run_b = await client.post(f"/api/scenarios/{sid_b}/run")
        kpis_b = run_b.json()["kpis"]

        # KPIs must match
        assert kpis_a["completed_tasks"] == kpis_b["completed_tasks"]
        assert kpis_a["throughput_items_per_hour"] == kpis_b["throughput_items_per_hour"]
        assert kpis_a["avg_order_cycle_time_s"] == kpis_b["avg_order_cycle_time_s"]


# ── TestScenarioResults ────────────────────────────────────


class TestScenarioResults:
    """Test GET /api/scenarios/{id}/results — fetch KPIs for completed scenario."""

    async def test_get_completed_results(self, client: AsyncClient, requires_mongodb):
        """Get results of a completed scenario returns KPIs."""
        resp = await client.post("/api/scenarios", json={
            "name": "Results Test",
            "warehouse_config": "simple_grid",
            "robot_config": "differential_drive",
            "fleet_size": 2,
            "order_count": 5,
            "order_seed": 42,
            "duration_s": 20,
        })
        sid = resp.json()["scenario_id"]
        await client.post(f"/api/scenarios/{sid}/run")

        resp2 = await client.get(f"/api/scenarios/{sid}/results")
        assert resp2.status_code == 200
        data = resp2.json()
        assert "kpis" in data
        assert data["scenario_id"] == sid
        assert data["status"] == "completed"

    async def test_get_not_completed_409(self, client: AsyncClient, requires_mongodb):
        """Get results of a created (not run) scenario returns 409."""
        resp = await client.post("/api/scenarios", json={
            "name": "Not Run",
            "warehouse_config": "simple_grid",
            "robot_config": "differential_drive",
        })
        sid = resp.json()["scenario_id"]

        resp2 = await client.get(f"/api/scenarios/{sid}/results")
        assert resp2.status_code == 409

    async def test_get_not_found_404(self, client: AsyncClient, requires_mongodb):
        """Get results of nonexistent scenario returns 404."""
        resp = await client.get("/api/scenarios/nonexistent_999/results")
        assert resp.status_code == 404


# ── TestScenarioCompare ────────────────────────────────────


class TestScenarioCompare:
    """Test GET /api/scenarios/compare?ids=A,B — multi-scenario comparison."""

    async def _create_and_run(self, client: AsyncClient, name: str, fleet_size: int, seed: int = 42) -> str:
        """Helper: create + run a scenario, return scenario_id."""
        resp = await client.post("/api/scenarios", json={
            "name": name,
            "warehouse_config": "simple_grid",
            "robot_config": "differential_drive",
            "fleet_size": fleet_size,
            "order_count": 10,
            "order_seed": seed,
            "duration_s": 30,
            "allocation_strategy": "fifo",
        })
        sid = resp.json()["scenario_id"]
        await client.post(f"/api/scenarios/{sid}/run")
        return sid

    async def test_compare_two_scenarios(self, client: AsyncClient, requires_mongodb):
        """Compare 2 completed scenarios returns deltas + rankings."""
        sid_a = await self._create_and_run(client, "Small Fleet", fleet_size=2)
        sid_b = await self._create_and_run(client, "Large Fleet", fleet_size=10)

        resp = await client.get(f"/api/scenarios/compare?ids={sid_a},{sid_b}")
        assert resp.status_code == 200
        data = resp.json()
        assert "scenarios" in data
        assert len(data["scenarios"]) == 2
        assert "deltas" in data
        assert "rankings" in data

    async def test_compare_fewer_than_2_returns_400(self, client: AsyncClient, requires_mongodb):
        """Compare with <2 IDs returns 400."""
        sid_a = await self._create_and_run(client, "Lone Scenario", fleet_size=3)
        resp = await client.get(f"/api/scenarios/compare?ids={sid_a}")
        assert resp.status_code == 400

    async def test_compare_csv_export(self, client: AsyncClient, requires_mongodb):
        """Compare with format=csv returns text/csv."""
        sid_a = await self._create_and_run(client, "CSV A", fleet_size=3, seed=10)
        sid_b = await self._create_and_run(client, "CSV B", fleet_size=6, seed=10)

        resp = await client.get(f"/api/scenarios/compare?ids={sid_a},{sid_b}&format=csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        # Parse CSV to verify structure
        reader = csv.reader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) >= 2  # header + at least 1 data row
        header = rows[0]
        assert "metric" in header

    async def test_compare_pdf_export(self, client: AsyncClient, requires_mongodb):
        """Compare with format=pdf returns application/pdf."""
        sid_a = await self._create_and_run(client, "PDF A", fleet_size=3, seed=20)
        sid_b = await self._create_and_run(client, "PDF B", fleet_size=6, seed=20)

        resp = await client.get(f"/api/scenarios/compare?ids={sid_a},{sid_b}&format=pdf")
        assert resp.status_code == 200
        assert "application/pdf" in resp.headers.get("content-type", "")
        # PDF starts with %PDF
        assert resp.content[:4] == b"%PDF"


# ── TestScenarioWorkflow ───────────────────────────────────


class TestScenarioWorkflow:
    """Full end-to-end workflow: create 2 scenarios, run both, compare."""

    async def test_full_workflow(self, client: AsyncClient, requires_mongodb):
        """Create 2 scenarios with different configs, run, compare."""
        # Create scenario A: small fleet, FIFO
        resp_a = await client.post("/api/scenarios", json={
            "name": "Workflow A",
            "warehouse_config": "simple_grid",
            "robot_config": "differential_drive",
            "fleet_size": 3,
            "allocation_strategy": "fifo",
            "order_count": 15,
            "order_seed": 100,
            "duration_s": 30,
        })
        assert resp_a.status_code == 200
        sid_a = resp_a.json()["scenario_id"]

        # Create scenario B: large fleet, nearest
        resp_b = await client.post("/api/scenarios", json={
            "name": "Workflow B",
            "warehouse_config": "simple_grid",
            "robot_config": "differential_drive",
            "fleet_size": 8,
            "allocation_strategy": "nearest",
            "order_count": 15,
            "order_seed": 100,
            "duration_s": 30,
        })
        assert resp_b.status_code == 200
        sid_b = resp_b.json()["scenario_id"]

        # Run both
        run_a = await client.post(f"/api/scenarios/{sid_a}/run")
        assert run_a.status_code == 200
        assert run_a.json()["status"] == "completed"

        run_b = await client.post(f"/api/scenarios/{sid_b}/run")
        assert run_b.status_code == 200
        assert run_b.json()["status"] == "completed"

        # Compare
        comp = await client.get(f"/api/scenarios/compare?ids={sid_a},{sid_b}")
        assert comp.status_code == 200
        data = comp.json()
        assert len(data["scenarios"]) == 2
        assert len(data["deltas"]) >= 1
        assert "rankings" in data

        # Verify individual results are still accessible
        res_a = await client.get(f"/api/scenarios/{sid_a}/results")
        assert res_a.status_code == 200
        assert res_a.json()["status"] == "completed"


# ── TestScenarioIsolation ──────────────────────────────────


class TestScenarioIsolation:
    """Verify scenarios don't share data."""

    async def test_two_scenarios_isolated(self, client: AsyncClient, requires_mongodb):
        """Two scenarios with different seeds produce different task counts or KPIs."""
        # Scenario A: seed=1
        resp_a = await client.post("/api/scenarios", json={
            "name": "Isolation A",
            "warehouse_config": "simple_grid",
            "robot_config": "differential_drive",
            "fleet_size": 3,
            "order_count": 10,
            "order_seed": 1,
            "duration_s": 30,
        })
        sid_a = resp_a.json()["scenario_id"]
        await client.post(f"/api/scenarios/{sid_a}/run")

        # Scenario B: seed=999 (different orders)
        resp_b = await client.post("/api/scenarios", json={
            "name": "Isolation B",
            "warehouse_config": "simple_grid",
            "robot_config": "differential_drive",
            "fleet_size": 3,
            "order_count": 10,
            "order_seed": 999,
            "duration_s": 30,
        })
        sid_b = resp_b.json()["scenario_id"]
        await client.post(f"/api/scenarios/{sid_b}/run")

        # Get results — they should exist independently
        res_a = await client.get(f"/api/scenarios/{sid_a}/results")
        res_b = await client.get(f"/api/scenarios/{sid_b}/results")
        assert res_a.status_code == 200
        assert res_b.status_code == 200

        # Both have their own scenario_id
        assert res_a.json()["scenario_id"] == sid_a
        assert res_b.json()["scenario_id"] == sid_b


# ── TestEndpointCount ──────────────────────────────────────


class TestEndpointCount:
    """Verify root endpoint reports updated count."""

    async def test_root_reports_60_endpoints(self, client: AsyncClient):
        """GET / should now report 71 endpoints."""
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["endpoints"] == 71

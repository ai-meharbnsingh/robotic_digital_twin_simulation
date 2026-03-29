"""
Phase 3: Heat Map Visualization — tests for GET /api/analytics/heatmap.

Tests verify:
- Endpoint returns correct response shape (cells, grid, zones)
- Grid cells have valid coordinates and intensity values
- Zone congestion scores are computed and sorted
- Duration parameter works (1h, 4h, 8h, 24h)
- Resolution parameter affects grid granularity
- Graceful degradation (simulated data when no DB)
- Performance: response under 500ms
"""

import time

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


# ── Response shape tests ─────────────────────────────────


class TestHeatmapResponseShape:
    async def test_returns_200(self, client: AsyncClient):
        resp = await client.get("/api/analytics/heatmap")
        assert resp.status_code == 200

    async def test_has_required_top_level_fields(self, client: AsyncClient):
        resp = await client.get("/api/analytics/heatmap")
        data = resp.json()
        assert "duration" in data
        assert "resolution_m" in data
        assert "data_source" in data
        assert "grid" in data
        assert "cells" in data
        assert "total_positions" in data
        assert "cell_count" in data
        assert "zones" in data
        assert "query_ms" in data

    async def test_grid_has_bounds(self, client: AsyncClient):
        resp = await client.get("/api/analytics/heatmap")
        grid = resp.json()["grid"]
        assert "min_x" in grid
        assert "min_y" in grid
        assert "max_x" in grid
        assert "max_y" in grid
        assert "cols" in grid
        assert "rows" in grid
        assert grid["max_x"] > grid["min_x"]
        assert grid["max_y"] > grid["min_y"]
        assert grid["cols"] > 0
        assert grid["rows"] > 0

    async def test_cells_have_required_fields(self, client: AsyncClient):
        resp = await client.get("/api/analytics/heatmap")
        cells = resp.json()["cells"]
        assert len(cells) > 0, "Expected at least one heat map cell"

        cell = cells[0]
        assert "x" in cell
        assert "y" in cell
        assert "col" in cell
        assert "row" in cell
        assert "visit_count" in cell
        assert "avg_dwell_time_s" in cell
        assert "intensity" in cell

    async def test_cell_intensity_range(self, client: AsyncClient):
        resp = await client.get("/api/analytics/heatmap")
        cells = resp.json()["cells"]

        for cell in cells:
            assert 0.0 <= cell["intensity"] <= 1.0, (
                f"Intensity {cell['intensity']} out of range for cell ({cell['col']}, {cell['row']})"
            )

    async def test_cells_sorted_by_intensity_descending(self, client: AsyncClient):
        resp = await client.get("/api/analytics/heatmap")
        cells = resp.json()["cells"]

        if len(cells) > 1:
            intensities = [c["intensity"] for c in cells]
            assert intensities == sorted(intensities, reverse=True), (
                "Cells should be sorted by intensity (highest first)"
            )


# ── Zone congestion tests ────────────────────────────────


class TestZoneCongestion:
    async def test_zones_present(self, client: AsyncClient):
        resp = await client.get("/api/analytics/heatmap")
        zones = resp.json()["zones"]
        assert isinstance(zones, list)
        assert len(zones) > 0, "Expected at least one zone congestion score"

    async def test_zone_has_required_fields(self, client: AsyncClient):
        resp = await client.get("/api/analytics/heatmap")
        zones = resp.json()["zones"]
        zone = zones[0]

        assert "zone_name" in zone
        assert "zone_type" in zone
        assert "node_count" in zone
        assert "total_visits" in zone
        assert "avg_visits_per_node" in zone
        assert "avg_dwell_time_s" in zone
        assert "congestion_score" in zone

    async def test_zones_sorted_by_congestion_descending(self, client: AsyncClient):
        resp = await client.get("/api/analytics/heatmap")
        zones = resp.json()["zones"]

        if len(zones) > 1:
            scores = [z["congestion_score"] for z in zones]
            assert scores == sorted(scores, reverse=True), (
                "Zones should be sorted by congestion score (highest first)"
            )

    async def test_zone_node_counts_positive(self, client: AsyncClient):
        resp = await client.get("/api/analytics/heatmap")
        zones = resp.json()["zones"]

        for zone in zones:
            assert zone["node_count"] >= 1, (
                f"Zone '{zone['zone_name']}' has 0 nodes"
            )


# ── Duration parameter tests ─────────────────────────────


class TestDurationParam:
    @pytest.mark.parametrize("duration", ["1h", "4h", "8h", "24h"])
    async def test_valid_durations(self, client: AsyncClient, duration: str):
        resp = await client.get(f"/api/analytics/heatmap?duration={duration}")
        assert resp.status_code == 200
        assert resp.json()["duration"] == duration

    async def test_invalid_duration_rejected(self, client: AsyncClient):
        resp = await client.get("/api/analytics/heatmap?duration=2h")
        assert resp.status_code == 422  # Validation error

    async def test_default_duration_is_1h(self, client: AsyncClient):
        resp = await client.get("/api/analytics/heatmap")
        assert resp.json()["duration"] == "1h"


# ── Resolution parameter tests ───────────────────────────


class TestResolutionParam:
    async def test_default_resolution(self, client: AsyncClient):
        resp = await client.get("/api/analytics/heatmap")
        assert resp.json()["resolution_m"] == 0.5

    async def test_custom_resolution(self, client: AsyncClient):
        resp = await client.get("/api/analytics/heatmap?resolution=1.0")
        data = resp.json()
        assert data["resolution_m"] == 1.0

    async def test_higher_resolution_fewer_cells(self, client: AsyncClient):
        resp_fine = await client.get("/api/analytics/heatmap?resolution=0.5")
        resp_coarse = await client.get("/api/analytics/heatmap?resolution=2.0")

        fine_cells = resp_fine.json()["cell_count"]
        coarse_cells = resp_coarse.json()["cell_count"]

        assert fine_cells >= coarse_cells, (
            f"Finer resolution (0.5m → {fine_cells} cells) should produce "
            f">= cells than coarser (2.0m → {coarse_cells} cells)"
        )

    async def test_resolution_too_small_rejected(self, client: AsyncClient):
        resp = await client.get("/api/analytics/heatmap?resolution=0.01")
        assert resp.status_code == 422

    async def test_resolution_too_large_rejected(self, client: AsyncClient):
        resp = await client.get("/api/analytics/heatmap?resolution=10.0")
        assert resp.status_code == 422


# ── Data source tests ────────────────────────────────────


class TestDataSource:
    async def test_data_source_reported(self, client: AsyncClient):
        resp = await client.get("/api/analytics/heatmap")
        data_source = resp.json()["data_source"]
        assert data_source in ("influxdb", "mongodb", "simulated")

    async def test_simulated_data_has_positions(self, client: AsyncClient):
        """Without InfluxDB/MongoDB, should fall back to simulated data."""
        resp = await client.get("/api/analytics/heatmap")
        data = resp.json()
        assert data["total_positions"] > 0


# ── Performance tests ────────────────────────────────────


class TestPerformance:
    async def test_response_under_500ms(self, client: AsyncClient):
        """Heatmap API must respond in <500ms for any duration."""
        for duration in ["1h", "4h", "8h", "24h"]:
            start = time.monotonic()
            resp = await client.get(f"/api/analytics/heatmap?duration={duration}")
            elapsed_ms = (time.monotonic() - start) * 1000

            assert resp.status_code == 200
            assert elapsed_ms < 500, (
                f"Heatmap for {duration} took {elapsed_ms:.1f}ms (limit: 500ms)"
            )

    async def test_query_ms_reported(self, client: AsyncClient):
        resp = await client.get("/api/analytics/heatmap")
        query_ms = resp.json()["query_ms"]
        assert isinstance(query_ms, (int, float))
        assert query_ms >= 0


# ── Spatial correctness tests ─────────────────────────────


class TestSpatialCorrectness:
    async def test_cells_within_grid_bounds(self, client: AsyncClient):
        resp = await client.get("/api/analytics/heatmap?resolution=1.0")
        data = resp.json()
        grid = data["grid"]

        for cell in data["cells"]:
            assert cell["x"] >= grid["min_x"], (
                f"Cell x={cell['x']} below grid min_x={grid['min_x']}"
            )
            assert cell["x"] <= grid["max_x"] + 1.0, (
                f"Cell x={cell['x']} above grid max_x={grid['max_x']}"
            )
            assert cell["y"] >= grid["min_y"], (
                f"Cell y={cell['y']} below grid min_y={grid['min_y']}"
            )
            assert cell["y"] <= grid["max_y"] + 1.0, (
                f"Cell y={cell['y']} above grid max_y={grid['max_y']}"
            )

    async def test_visit_counts_positive(self, client: AsyncClient):
        resp = await client.get("/api/analytics/heatmap")
        cells = resp.json()["cells"]

        for cell in cells:
            assert cell["visit_count"] >= 1, (
                f"Cell ({cell['col']}, {cell['row']}) has 0 visits"
            )

    async def test_dwell_times_positive(self, client: AsyncClient):
        resp = await client.get("/api/analytics/heatmap")
        cells = resp.json()["cells"]

        for cell in cells:
            assert cell["avg_dwell_time_s"] > 0, (
                f"Cell ({cell['col']}, {cell['row']}) has 0 dwell time"
            )

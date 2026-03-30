"""
Phase 5 — 3D Backend Performance Budget.

Verifies the BACKEND data pipeline can support 50 robots within the frame budget:
  - API response times (map, robots, heatmap)
  - WebSocket broadcast overhead (event creation + serialization, 0 clients)
  - JSON payload size
  - Shared geometry patterns in frontend source (static analysis)

This does NOT measure browser-side FPS. Actual 30fps@50-robot rendering requires
a Playwright E2E test with GPU-enabled browser, which is not part of this suite.
The 30fps acceptance criterion in ROADMAP.md is honestly marked as unproven.
"""

import json
import time

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


class TestPerformanceBudget:
    """Verify the data pipeline can support 50 robots at 30fps (33ms frame budget)."""

    async def test_map_api_under_100ms(self, client: AsyncClient):
        """GET /api/map must respond within 100ms init budget for 3D scene."""
        start = time.perf_counter()
        resp = await client.get("/api/map")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert resp.status_code == 200
        assert elapsed_ms < 100, f"Map API took {elapsed_ms:.1f}ms (budget: <100ms for init)"

    async def test_robots_api_under_200ms(self, client: AsyncClient, requires_mongodb):
        """GET /api/robots must respond within 200ms budget for 3s polling cycle.

        Requires MongoDB: measures actual query latency, not connection timeout.
        Skipped when MongoDB is unavailable (no point measuring timeout duration).
        """
        # Warm the MongoDB connection
        await client.get("/api/robots")
        # Measure steady-state latency
        start = time.perf_counter()
        resp = await client.get("/api/robots")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert resp.status_code == 200
        assert elapsed_ms < 200, f"Robots API took {elapsed_ms:.1f}ms (budget: <200ms for 3s polling)"

    async def test_heatmap_api_under_500ms(self, client: AsyncClient):
        """GET /api/analytics/heatmap must respond within 3D overlay budget."""
        start = time.perf_counter()
        resp = await client.get("/api/analytics/heatmap?duration=1h&resolution=0.5")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert resp.status_code == 200
        assert elapsed_ms < 500, f"Heatmap API took {elapsed_ms:.1f}ms (budget: <500ms)"

    def test_websocket_broadcast_overhead(self):
        """WebSocket broadcast overhead: 50 events creation+serialize in <100ms (0 connected clients)."""
        from app.websocket import ConnectionManager
        import asyncio

        manager = ConnectionManager()
        events = []
        for i in range(50):
            events.append({
                "event": "robot_position",
                "data": {
                    "robot_id": f"ROBOT_{i:02d}",
                    "pose": {"x": float(i), "y": float(i * 0.5), "theta": 0.0},
                    "status": "moving",
                    "current_node": f"N_{i:02d}",
                },
            })

        async def broadcast_all():
            start = time.perf_counter()
            for ev in events:
                await manager.broadcast(ev)
            return (time.perf_counter() - start) * 1000

        loop = asyncio.new_event_loop()
        elapsed_ms = loop.run_until_complete(broadcast_all())
        loop.close()

        # 0 connected clients — tests event creation + serialization overhead only.
        # Actual fanout latency depends on client count and is IO-bound.
        # Full broadcast-under-load requires Playwright E2E with connected WS clients.
        assert elapsed_ms < 100, f"Broadcasting 50 events took {elapsed_ms:.1f}ms (overhead budget: <100ms)"
        assert manager.message_count == 50

    def test_50_robot_json_serialization_under_10ms(self):
        """50-robot REST response must serialize within 10ms budget."""
        robots = []
        for i in range(50):
            robots.append({
                "robot_id": f"ROBOT_{i:02d}",
                "name": f"Robot {i}",
                "robot_type": "differential_drive" if i % 2 == 0 else "unidirectional",
                "status": "moving",
                "pose": {"x": float(i * 2), "y": float(i), "theta": 1.57},
                "velocity": {"linear": 0.5, "angular": 0.0},
                "battery": {"charge_pct": 80 - i, "is_charging": False, "voltage": 24.0, "current": 1.5, "temperature_c": 35.0},
                "current_node": f"N_{i:02d}",
                "target_node": f"N_{i + 1:02d}",
                "current_task_id": f"TASK_{i:03d}" if i < 25 else None,
                "path": [f"N_{j:02d}" for j in range(i, min(i + 5, 50))],
                "path_index": 0,
                "errors": [],
                "last_seen": "2026-03-30T12:00:00Z",
                "action_code": 1,
                "response_code": 0,
            })

        start = time.perf_counter()
        payload = json.dumps(robots)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 10, f"Serializing 50 robots took {elapsed_ms:.1f}ms (budget: <10ms)"
        assert len(robots) == 50
        # Verify payload size is reasonable for network transfer
        payload_kb = len(payload) / 1024
        assert payload_kb < 100, f"50-robot payload is {payload_kb:.1f}KB (budget: <100KB)"

    def test_shared_geometry_count(self):
        """Verify the 3D scene uses shared geometries, not per-instance."""
        # Read the Warehouse3D source and verify useMemo geometry patterns
        from pathlib import Path
        scene_path = Path(__file__).resolve().parent.parent.parent / "frontend" / "src" / "components" / "Warehouse3D.tsx"
        robot_path = Path(__file__).resolve().parent.parent.parent / "frontend" / "src" / "components" / "Robot3DModel.tsx"

        scene_src = scene_path.read_text()
        robot_src = robot_path.read_text()

        # NodeMarkers should use shared geometries via useMemo
        assert "useMemo(() => new THREE.BoxGeometry" in scene_src, \
            "NodeMarkers should use shared BoxGeometry via useMemo"
        assert "useMemo(() => new THREE.CylinderGeometry" in scene_src, \
            "NodeMarkers should use shared CylinderGeometry via useMemo"

        # Robot3DModel should accept a geometry pool, not create inline geometries
        assert "geoPool" in robot_src, \
            "Robot3DModel should use shared geometry pool, not inline geometries"
        assert "<boxGeometry" not in robot_src, \
            "Robot3DModel should NOT have inline <boxGeometry> — use shared pool"
        assert "<cylinderGeometry" not in robot_src, \
            "Robot3DModel should NOT have inline <cylinderGeometry> — use shared pool"

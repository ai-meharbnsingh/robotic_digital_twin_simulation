"""
Tests for Phase 11 — Scale to 100+ Robots (MAPF).

Tests CBS solver, PIBT solver, congestion tracker, and MAPF REST endpoints.
Tests graph building from warehouse configs (simple_grid, addverb_noida).

TDD: Written FIRST, then implementation until green.
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


# ── Helper: build a simple grid graph ─────────────────────────

def _simple_4x4_graph() -> dict:
    """4x4 grid graph (16 nodes, bidirectional edges).

    Layout:
        0,0 — 1,0 — 2,0 — 3,0
         |     |     |     |
        0,1 — 1,1 — 2,1 — 3,1
         |     |     |     |
        0,2 — 1,2 — 2,2 — 3,2
         |     |     |     |
        0,3 — 1,3 — 2,3 — 3,3
    """
    graph = {}
    for x in range(4):
        for y in range(4):
            node = f"{x},{y}"
            neighbors = []
            for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                nx_, ny_ = x + dx, y + dy
                if 0 <= nx_ < 4 and 0 <= ny_ < 4:
                    neighbors.append((f"{nx_},{ny_}", 1.0))
            graph[node] = neighbors
    return graph


def _corridor_with_bypass_graph() -> dict:
    """Corridor with a bypass siding for head-on conflict resolution.

    Layout:
        A — B — C — D
            |
            S  (siding / bypass)

    R1 at A → D and R2 at D → A can resolve:
      R1 waits at S while R2 passes through B.
    """
    return {
        "A": [("B", 1.0)],
        "B": [("A", 1.0), ("C", 1.0), ("S", 1.0)],
        "C": [("B", 1.0), ("D", 1.0)],
        "D": [("C", 1.0)],
        "S": [("B", 1.0)],
    }


def _large_grid_graph(size: int) -> dict:
    """NxN grid graph for stress tests."""
    graph = {}
    for x in range(size):
        for y in range(size):
            node = f"{x},{y}"
            neighbors = []
            for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                nx_, ny_ = x + dx, y + dy
                if 0 <= nx_ < size and 0 <= ny_ < size:
                    neighbors.append((f"{nx_},{ny_}", 1.0))
            graph[node] = neighbors
    return graph


# ═══════════════════════════════════════════════════════════════
# CBS Solver Tests
# ═══════════════════════════════════════════════════════════════


class TestCBSSolver:
    """Test Conflict-Based Search (CBS) solver."""

    def test_cbs_2_agents_no_conflict(self):
        """Two agents with non-overlapping paths — zero conflicts resolved."""
        from wes.mapf_solver import CBSSolver

        graph = _simple_4x4_graph()
        solver = CBSSolver(graph=graph, max_agents=10, time_limit_s=5.0)

        agents = [
            {"agent_id": "R1", "start": "0,0", "goal": "3,0"},
            {"agent_id": "R2", "start": "0,3", "goal": "3,3"},
        ]
        result = solver.solve(agents)

        assert result["success"] is True
        assert "R1" in result["paths"]
        assert "R2" in result["paths"]
        # Both reach their goals
        assert result["paths"]["R1"][-1] == "3,0"
        assert result["paths"]["R2"][-1] == "3,3"
        assert result["cost"] > 0
        assert isinstance(result["solve_time_ms"], float)
        assert result["solve_time_ms"] >= 0

    def test_cbs_2_agents_head_on(self):
        """Two agents in a corridor with bypass going opposite directions — resolved via siding."""
        from wes.mapf_solver import CBSSolver

        graph = _corridor_with_bypass_graph()
        solver = CBSSolver(graph=graph, max_agents=10, time_limit_s=5.0)

        agents = [
            {"agent_id": "R1", "start": "A", "goal": "D"},
            {"agent_id": "R2", "start": "D", "goal": "A"},
        ]
        result = solver.solve(agents)

        assert result["success"] is True
        assert result["paths"]["R1"][-1] == "D"
        assert result["paths"]["R2"][-1] == "A"
        # Must have resolved at least 1 conflict
        assert result["conflicts_resolved"] >= 1

        # Verify no vertex conflicts: no two agents at same node at same timestep
        paths = result["paths"]
        max_t = max(len(p) for p in paths.values())
        for t in range(max_t):
            occupied = []
            for aid, path in paths.items():
                pos = path[t] if t < len(path) else path[-1]
                occupied.append(pos)
            assert len(occupied) == len(set(occupied)), f"Vertex conflict at timestep {t}: {occupied}"

    def test_cbs_10_agents_grid(self):
        """10 agents on a 10x10 grid (non-crossing paths) — all reach their goals.

        Uses a large grid with parallel paths (start on left, goal on right,
        different rows) so CBS can find optimal paths without excessive branching.
        """
        from wes.mapf_solver import CBSSolver

        graph = _large_grid_graph(10)
        solver = CBSSolver(graph=graph, max_agents=20, time_limit_s=10.0)

        # 10 agents, each on its own row — minimal conflicts
        agents = [
            {"agent_id": f"R{i}", "start": f"0,{i}", "goal": f"9,{i}"}
            for i in range(10)
        ]
        result = solver.solve(agents)

        assert result["success"] is True
        for agent in agents:
            aid = agent["agent_id"]
            assert aid in result["paths"]
            assert result["paths"][aid][-1] == agent["goal"]

    def test_cbs_100_agents_stress(self):
        """100 agents on a 20x20 grid — completes within 5s time limit."""
        from wes.mapf_solver import CBSSolver

        graph = _large_grid_graph(20)
        solver = CBSSolver(graph=graph, max_agents=200, time_limit_s=5.0)

        agents = []
        for i in range(100):
            row = i // 20
            col = i % 20
            # Start on left, goal on right (spread across rows)
            agents.append({
                "agent_id": f"R{i:03d}",
                "start": f"0,{i % 20}",
                "goal": f"19,{(i + 5) % 20}",
            })
        result = solver.solve(agents)

        # Must complete (success=True or partial via time limit)
        assert result["solve_time_ms"] <= 6000  # 5s + margin
        assert isinstance(result["paths"], dict)
        assert len(result["paths"]) == 100
        # Verify cost is computed
        assert result["cost"] >= 0

    def test_cbs_time_limit(self):
        """CBS returns best-effort paths after time limit expires."""
        from wes.mapf_solver import CBSSolver

        graph = _large_grid_graph(10)
        # Very short time limit — will timeout
        solver = CBSSolver(graph=graph, max_agents=200, time_limit_s=0.001)

        agents = [
            {"agent_id": f"R{i}", "start": f"0,{i % 10}", "goal": f"9,{(i + 3) % 10}"}
            for i in range(50)
        ]
        result = solver.solve(agents)

        # Should still return paths (best-effort from initial solution)
        assert isinstance(result["paths"], dict)
        assert len(result["paths"]) == 50
        assert result["solve_time_ms"] >= 0

    def test_cbs_single_agent(self):
        """Single agent — trivial case, just A*."""
        from wes.mapf_solver import CBSSolver

        graph = _simple_4x4_graph()
        solver = CBSSolver(graph=graph, max_agents=10, time_limit_s=5.0)

        agents = [{"agent_id": "R1", "start": "0,0", "goal": "3,3"}]
        result = solver.solve(agents)

        assert result["success"] is True
        assert result["paths"]["R1"][0] == "0,0"
        assert result["paths"]["R1"][-1] == "3,3"
        assert result["conflicts_resolved"] == 0
        # Shortest path on 4x4 grid from (0,0) to (3,3) is 6 steps
        assert len(result["paths"]["R1"]) == 7  # 7 nodes = 6 edges

    def test_cbs_agent_already_at_goal(self):
        """Agent starts at goal — path is just [start]."""
        from wes.mapf_solver import CBSSolver

        graph = _simple_4x4_graph()
        solver = CBSSolver(graph=graph, max_agents=10, time_limit_s=5.0)

        agents = [{"agent_id": "R1", "start": "2,2", "goal": "2,2"}]
        result = solver.solve(agents)

        assert result["success"] is True
        assert result["paths"]["R1"] == ["2,2"]
        assert result["cost"] == 0


# ═══════════════════════════════════════════════════════════════
# Graph Building Tests
# ═══════════════════════════════════════════════════════════════


class TestGraphBuilding:
    """Test CBS.build_graph_from_warehouse."""

    def test_build_graph_from_simple_grid(self):
        """simple_grid warehouse → correct adjacency dict."""
        import json
        from pathlib import Path
        from wes.mapf_solver import CBSSolver

        config_path = Path(__file__).resolve().parent.parent.parent / "configs" / "warehouses" / "simple_grid.json"
        with open(config_path) as f:
            warehouse = json.load(f)

        graph = CBSSolver.build_graph_from_warehouse(warehouse)

        # 25 nodes in simple_grid
        assert len(graph) == 25
        # DOCK_1 connects to N_01 and N_10
        assert "DOCK_1" in graph
        dock1_neighbors = [n for n, _ in graph["DOCK_1"]]
        assert "N_01" in dock1_neighbors
        assert "N_10" in dock1_neighbors
        # HUB is a central node with 4 connections
        hub_neighbors = [n for n, _ in graph["HUB"]]
        assert len(hub_neighbors) == 4

    def test_build_graph_from_addverb_noida(self):
        """addverb_noida warehouse → 49 nodes in adjacency dict."""
        import json
        from pathlib import Path
        from wes.mapf_solver import CBSSolver

        config_path = Path(__file__).resolve().parent.parent.parent / "configs" / "warehouses" / "addverb_noida.json"
        with open(config_path) as f:
            warehouse = json.load(f)

        graph = CBSSolver.build_graph_from_warehouse(warehouse)

        assert len(graph) == 49
        # Every node should have at least 1 neighbor
        for node, neighbors in graph.items():
            assert len(neighbors) >= 1, f"Node {node} has no neighbors"

    def test_build_graph_edges_are_bidirectional(self):
        """Edges are bidirectional: if A→B exists, B→A must too."""
        import json
        from pathlib import Path
        from wes.mapf_solver import CBSSolver

        config_path = Path(__file__).resolve().parent.parent.parent / "configs" / "warehouses" / "simple_grid.json"
        with open(config_path) as f:
            warehouse = json.load(f)

        graph = CBSSolver.build_graph_from_warehouse(warehouse)

        for node, neighbors in graph.items():
            for neighbor, cost in neighbors:
                # Check reverse edge exists
                reverse_neighbors = [n for n, _ in graph[neighbor]]
                assert node in reverse_neighbors, f"Edge {node}→{neighbor} exists but {neighbor}→{node} does not"


# ═══════════════════════════════════════════════════════════════
# PIBT Solver Tests
# ═══════════════════════════════════════════════════════════════


class TestPIBTSolver:
    """Test Priority Inheritance with Backtracking (PIBT) solver."""

    def test_pibt_single_step(self):
        """Single agent takes one step toward goal."""
        from wes.pibt_solver import PIBTSolver

        graph = _simple_4x4_graph()
        solver = PIBTSolver()

        agents = [
            {"agent_id": "R1", "position": "0,0", "goal": "3,0", "priority": 1, "wait_time": 0},
        ]
        result = solver.step(agents, graph)

        assert result["success"] is True
        assert "R1" in result["moves"]
        # Must move closer to goal (to 1,0)
        assert result["moves"]["R1"] == "1,0"

    def test_pibt_10_agents_no_collisions(self):
        """10 agents over 50 steps — no two agents at the same node."""
        from wes.pibt_solver import PIBTSolver

        graph = _large_grid_graph(5)
        solver = PIBTSolver()

        # Spread 10 agents across 5x5 grid with UNIQUE start positions
        agents = [
            {"agent_id": "R0", "position": "0,0", "goal": "4,4", "priority": 0, "wait_time": 0},
            {"agent_id": "R1", "position": "1,0", "goal": "3,4", "priority": 1, "wait_time": 0},
            {"agent_id": "R2", "position": "2,0", "goal": "2,4", "priority": 2, "wait_time": 0},
            {"agent_id": "R3", "position": "3,0", "goal": "1,4", "priority": 3, "wait_time": 0},
            {"agent_id": "R4", "position": "4,0", "goal": "0,4", "priority": 4, "wait_time": 0},
            {"agent_id": "R5", "position": "0,1", "goal": "4,3", "priority": 5, "wait_time": 0},
            {"agent_id": "R6", "position": "1,1", "goal": "3,3", "priority": 6, "wait_time": 0},
            {"agent_id": "R7", "position": "2,1", "goal": "2,3", "priority": 7, "wait_time": 0},
            {"agent_id": "R8", "position": "3,1", "goal": "1,3", "priority": 8, "wait_time": 0},
            {"agent_id": "R9", "position": "4,1", "goal": "0,3", "priority": 9, "wait_time": 0},
        ]

        for step_num in range(50):
            result = solver.step(agents, graph)
            assert result["success"] is True

            # Check no collisions
            positions = list(result["moves"].values())
            assert len(positions) == len(set(positions)), \
                f"Collision at step {step_num}: {positions}"

            # Update agent positions for next step
            for agent in agents:
                agent["position"] = result["moves"][agent["agent_id"]]

    def test_pibt_100_agents_stress(self):
        """100 agents on 20x20 grid — single step completes in <67ms (15Hz)."""
        from wes.pibt_solver import PIBTSolver

        graph = _large_grid_graph(20)
        solver = PIBTSolver()

        agents = [
            {"agent_id": f"R{i:03d}", "position": f"{i % 20},{i // 20}",
             "goal": f"{19 - i % 20},{19 - i // 20}",
             "priority": i, "wait_time": 0}
            for i in range(100)
        ]

        start = time.monotonic()
        result = solver.step(agents, graph)
        elapsed_ms = (time.monotonic() - start) * 1000

        assert result["success"] is True
        assert len(result["moves"]) == 100
        # Must complete within 67ms for 15Hz FMS loop
        assert elapsed_ms < 67, f"PIBT step took {elapsed_ms:.1f}ms — too slow for 15Hz"

    def test_pibt_priority_inheritance(self):
        """Higher-priority agent gets the contested path node."""
        from wes.pibt_solver import PIBTSolver

        # Corridor: A — B — C
        graph = {
            "A": [("B", 1.0)],
            "B": [("A", 1.0), ("C", 1.0)],
            "C": [("B", 1.0)],
        }
        solver = PIBTSolver()

        # R1 (high priority) wants B. R2 (low priority) at B wants C.
        agents = [
            {"agent_id": "R1", "position": "A", "goal": "C", "priority": 10, "wait_time": 5},
            {"agent_id": "R2", "position": "B", "goal": "C", "priority": 1, "wait_time": 0},
        ]
        result = solver.step(agents, graph)

        assert result["success"] is True
        # R1 should get B (higher priority), R2 should move out of the way
        assert result["moves"]["R1"] == "B"
        # R2 must not be at B (moved to A or C)
        assert result["moves"]["R2"] != "B"

    def test_pibt_agent_at_goal_stays(self):
        """Agent already at goal stays there."""
        from wes.pibt_solver import PIBTSolver

        graph = _simple_4x4_graph()
        solver = PIBTSolver()

        agents = [
            {"agent_id": "R1", "position": "2,2", "goal": "2,2", "priority": 1, "wait_time": 0},
        ]
        result = solver.step(agents, graph)

        assert result["success"] is True
        assert result["moves"]["R1"] == "2,2"


# ═══════════════════════════════════════════════════════════════
# Congestion Tracker Tests
# ═══════════════════════════════════════════════════════════════


class TestCongestionTracker:
    """Test congestion tracking and bottleneck detection."""

    def test_update_occupancy(self):
        """Update with robot positions increments node occupancy."""
        from wes.congestion_tracker import CongestionTracker

        tracker = CongestionTracker()

        # 3 robots at HUB, 1 at DOCK_1
        tracker.update({"R1": "HUB", "R2": "HUB", "R3": "HUB", "R4": "DOCK_1"})
        tracker.update({"R1": "HUB", "R2": "S_11", "R3": "HUB", "R4": "DOCK_1"})

        cmap = tracker.get_congestion_map()
        assert "HUB" in cmap
        assert cmap["HUB"]["occupancy"] == 5  # 3 + 2
        assert cmap["DOCK_1"]["occupancy"] == 2
        assert cmap["S_11"]["occupancy"] == 1

    def test_congestion_bottlenecks(self):
        """Top N bottlenecks returns correct order."""
        from wes.congestion_tracker import CongestionTracker

        tracker = CongestionTracker()

        # Create distinct occupancy levels
        for _ in range(10):
            tracker.update({"R1": "HUB", "R2": "HUB", "R3": "HUB"})
        for _ in range(5):
            tracker.update({"R1": "N_01", "R2": "N_01"})
        for _ in range(2):
            tracker.update({"R1": "DOCK_1"})

        bottlenecks = tracker.get_bottlenecks(top_n=3)
        assert len(bottlenecks) == 3
        # HUB should be #1 (30 occupancy), N_01 #2 (10), DOCK_1 #3 (2)
        assert bottlenecks[0]["node_id"] == "HUB"
        assert bottlenecks[0]["occupancy"] == 30
        assert bottlenecks[1]["node_id"] == "N_01"
        assert bottlenecks[1]["occupancy"] == 10
        assert bottlenecks[2]["node_id"] == "DOCK_1"
        assert bottlenecks[2]["occupancy"] == 2

    def test_congestion_wait_time_avg(self):
        """Congestion map tracks average wait time (consecutive occupancy)."""
        from wes.congestion_tracker import CongestionTracker

        tracker = CongestionTracker()

        # Robot R1 stays at HUB for 4 ticks
        for _ in range(4):
            tracker.update({"R1": "HUB"})

        cmap = tracker.get_congestion_map()
        assert cmap["HUB"]["wait_time_avg"] > 0

    def test_congestion_throughput(self):
        """Congestion map tracks throughput (unique robots passing through)."""
        from wes.congestion_tracker import CongestionTracker

        tracker = CongestionTracker()

        # 3 different robots pass through HUB
        tracker.update({"R1": "HUB"})
        tracker.update({"R2": "HUB"})
        tracker.update({"R3": "HUB"})

        cmap = tracker.get_congestion_map()
        assert cmap["HUB"]["throughput"] == 3  # 3 unique robots

    def test_congestion_empty(self):
        """Empty tracker returns empty map and bottlenecks."""
        from wes.congestion_tracker import CongestionTracker

        tracker = CongestionTracker()
        assert tracker.get_congestion_map() == {}
        assert tracker.get_bottlenecks(top_n=5) == []

    def test_bottlenecks_fewer_than_top_n(self):
        """If fewer nodes than top_n, return all of them."""
        from wes.congestion_tracker import CongestionTracker

        tracker = CongestionTracker()
        tracker.update({"R1": "HUB"})

        bottlenecks = tracker.get_bottlenecks(top_n=10)
        assert len(bottlenecks) == 1
        assert bottlenecks[0]["node_id"] == "HUB"


# ═══════════════════════════════════════════════════════════════
# MAPF REST Endpoint Tests
# ═══════════════════════════════════════════════════════════════


class TestMAPFEndpoints:
    """Test MAPF REST API endpoints."""

    async def test_mapf_solve_cbs(self, client: AsyncClient):
        """POST /api/mapf/solve with CBS returns conflict-free paths."""
        resp = await client.post("/api/mapf/solve", json={
            "solver": "cbs",
            "agents": [
                {"agent_id": "R1", "start": "DOCK_1", "goal": "DROP_1"},
                {"agent_id": "R2", "start": "DROP_1", "goal": "DOCK_1"},
            ],
            "time_limit_s": 5.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "R1" in data["paths"]
        assert "R2" in data["paths"]
        assert data["paths"]["R1"][-1] == "DROP_1"
        assert data["paths"]["R2"][-1] == "DOCK_1"
        assert isinstance(data["solve_time_ms"], float)
        assert isinstance(data["conflicts_resolved"], int)

    async def test_mapf_solve_pibt(self, client: AsyncClient):
        """POST /api/mapf/solve with PIBT returns next positions."""
        resp = await client.post("/api/mapf/solve", json={
            "solver": "pibt",
            "agents": [
                {"agent_id": "R1", "start": "DOCK_1", "goal": "DROP_1"},
                {"agent_id": "R2", "start": "DROP_1", "goal": "DOCK_1"},
            ],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "R1" in data["moves"]
        assert "R2" in data["moves"]

    async def test_mapf_solve_invalid_solver(self, client: AsyncClient):
        """POST /api/mapf/solve with unknown solver returns 400."""
        resp = await client.post("/api/mapf/solve", json={
            "solver": "unknown_solver",
            "agents": [
                {"agent_id": "R1", "start": "DOCK_1", "goal": "DROP_1"},
            ],
        })
        assert resp.status_code == 400

    async def test_mapf_status(self, client: AsyncClient):
        """GET /api/mapf/status returns solver status."""
        resp = await client.get("/api/mapf/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "last_solve_time_ms" in data
        assert "last_conflicts_resolved" in data
        assert "total_solves" in data

    async def test_mapf_step(self, client: AsyncClient):
        """POST /api/mapf/step runs a single PIBT step."""
        resp = await client.post("/api/mapf/step", json={
            "agents": [
                {"agent_id": "R1", "position": "DOCK_1", "goal": "DROP_1",
                 "priority": 1, "wait_time": 0},
            ],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "R1" in data["moves"]

    async def test_mapf_benchmarks(self, client: AsyncClient):
        """GET /api/mapf/benchmarks returns performance metrics."""
        # Run a solve first so benchmarks have data
        await client.post("/api/mapf/solve", json={
            "solver": "cbs",
            "agents": [
                {"agent_id": "R1", "start": "DOCK_1", "goal": "DROP_1"},
            ],
            "time_limit_s": 5.0,
        })

        resp = await client.get("/api/mapf/benchmarks")
        assert resp.status_code == 200
        data = resp.json()
        assert "solves" in data
        assert isinstance(data["solves"], list)
        assert len(data["solves"]) >= 1
        assert "agent_count" in data["solves"][0]
        assert "solve_time_ms" in data["solves"][0]
        assert "solver" in data["solves"][0]

    async def test_mapf_congestion(self, client: AsyncClient):
        """GET /api/mapf/congestion returns congestion data after a solve."""
        # Run a solve to populate congestion tracker
        await client.post("/api/mapf/solve", json={
            "solver": "cbs",
            "agents": [
                {"agent_id": "R1", "start": "DOCK_1", "goal": "DROP_1"},
                {"agent_id": "R2", "start": "DROP_1", "goal": "DOCK_1"},
            ],
            "time_limit_s": 5.0,
        })

        resp = await client.get("/api/mapf/congestion")
        assert resp.status_code == 200
        data = resp.json()
        assert "congestion_map" in data
        assert "bottlenecks" in data
        assert "total_nodes_tracked" in data
        assert isinstance(data["bottlenecks"], list)
        assert data["total_nodes_tracked"] >= 0

    async def test_mapf_invalid_node_ids(self, client: AsyncClient):
        """POST /api/mapf/solve with invalid node IDs returns 400."""
        resp = await client.post("/api/mapf/solve", json={
            "solver": "cbs",
            "agents": [
                {"agent_id": "R1", "start": "NONEXISTENT_NODE", "goal": "DROP_1"},
            ],
            "time_limit_s": 5.0,
        })
        assert resp.status_code == 400
        assert "NONEXISTENT_NODE" in resp.json()["detail"]

    async def test_mapf_duplicate_agent_ids(self, client: AsyncClient):
        """POST /api/mapf/solve with duplicate agent_ids returns 400."""
        resp = await client.post("/api/mapf/solve", json={
            "solver": "cbs",
            "agents": [
                {"agent_id": "R1", "start": "DOCK_1", "goal": "DROP_1"},
                {"agent_id": "R1", "start": "DROP_1", "goal": "DOCK_1"},
            ],
            "time_limit_s": 5.0,
        })
        assert resp.status_code == 400
        assert "Duplicate" in resp.json()["detail"]

    async def test_mapf_step_duplicate_agent_ids(self, client: AsyncClient):
        """POST /api/mapf/step with duplicate agent_ids returns 400."""
        resp = await client.post("/api/mapf/step", json={
            "agents": [
                {"agent_id": "R1", "position": "DOCK_1", "goal": "DROP_1",
                 "priority": 1, "wait_time": 0},
                {"agent_id": "R1", "position": "DROP_1", "goal": "DOCK_1",
                 "priority": 2, "wait_time": 0},
            ],
        })
        assert resp.status_code == 400
        assert "Duplicate" in resp.json()["detail"]

    async def test_mapf_step_invalid_node_ids(self, client: AsyncClient):
        """POST /api/mapf/step with invalid node IDs returns 400."""
        resp = await client.post("/api/mapf/step", json={
            "agents": [
                {"agent_id": "R1", "position": "FAKE_NODE", "goal": "DROP_1",
                 "priority": 1, "wait_time": 0},
            ],
        })
        assert resp.status_code == 400
        assert "FAKE_NODE" in resp.json()["detail"]


# ═══════════════════════════════════════════════════════════════
# CBS Validation Tests (Unit-level)
# ═══════════════════════════════════════════════════════════════


class TestCBSValidation:
    """Test CBS solver input validation at the solver level."""

    def test_unreachable_goal_returns_failure(self):
        """CBS returns success=False when a goal is unreachable."""
        from wes.mapf_solver import CBSSolver

        # Disconnected graph: island_A and island_B have no path between them
        graph = {
            "island_A": [("A2", 1.0)],
            "A2": [("island_A", 1.0)],
            "island_B": [("B2", 1.0)],
            "B2": [("island_B", 1.0)],
        }
        solver = CBSSolver(graph=graph, max_agents=10, time_limit_s=5.0)

        agents = [{"agent_id": "R1", "start": "island_A", "goal": "island_B"}]
        result = solver.solve(agents)

        assert result["success"] is False
        # Path should be [start] since goal unreachable
        assert result["paths"]["R1"][0] == "island_A"

    def test_max_agents_exceeded_raises(self):
        """CBS raises ValueError when agent count exceeds max_agents."""
        from wes.mapf_solver import CBSSolver

        graph = _simple_4x4_graph()
        solver = CBSSolver(graph=graph, max_agents=2, time_limit_s=5.0)

        agents = [
            {"agent_id": f"R{i}", "start": f"{i},0", "goal": f"{i},3"}
            for i in range(3)
        ]
        with pytest.raises(ValueError, match="Too many agents"):
            solver.solve(agents)

    def test_duplicate_agent_ids_raises(self):
        """CBS raises ValueError on duplicate agent IDs."""
        from wes.mapf_solver import CBSSolver

        graph = _simple_4x4_graph()
        solver = CBSSolver(graph=graph, max_agents=10, time_limit_s=5.0)

        agents = [
            {"agent_id": "R1", "start": "0,0", "goal": "3,0"},
            {"agent_id": "R1", "start": "0,1", "goal": "3,1"},
        ]
        with pytest.raises(ValueError, match="Duplicate agent_id"):
            solver.solve(agents)


class TestPIBTValidation:
    """Test PIBT solver input validation."""

    def test_duplicate_agent_ids_raises(self):
        """PIBT raises ValueError on duplicate agent IDs."""
        from wes.pibt_solver import PIBTSolver

        graph = _simple_4x4_graph()
        solver = PIBTSolver()

        agents = [
            {"agent_id": "R1", "position": "0,0", "goal": "3,0", "priority": 1, "wait_time": 0},
            {"agent_id": "R1", "position": "1,0", "goal": "3,1", "priority": 2, "wait_time": 0},
        ]
        with pytest.raises(ValueError, match="Duplicate agent_id"):
            solver.step(agents, graph)


# ═══════════════════════════════════════════════════════════════
# Endpoint Count Test
# ═══════════════════════════════════════════════════════════════


class TestEndpointCountPhase11:
    """Verify root endpoint reports updated count after Phase 11."""

    async def test_root_reports_65_endpoints(self, client: AsyncClient):
        """GET / should now report 71 endpoints (60 base + 4 MAPF + 1 congestion + 6 WMS)."""
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["endpoints"] == 71

"""
Conflict-Based Search (CBS) for Multi-Agent Path Finding.

CBS is a two-level algorithm:
  - High level: search over conflicts (constraint tree)
  - Low level: single-agent A* with time-space constraints

Handles 100+ robots on warehouse graphs.

Phase 11: Scale to 100+ Robots.
"""

import heapq
import math
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(order=True)
class _CTNode:
    """Constraint Tree node for CBS high-level search."""

    cost: int
    id: int = field(compare=False)
    constraints: dict = field(compare=False, default_factory=dict)
    paths: dict = field(compare=False, default_factory=dict)


class CBSSolver:
    """Conflict-Based Search for Multi-Agent Path Finding.

    CBS is a two-level algorithm:
    - High level: search over conflicts (constraint tree)
    - Low level: single-agent A* with constraints

    Handles 100+ robots on warehouse graphs.
    """

    def __init__(
        self,
        graph: dict[str, list[tuple[str, float]]],
        max_agents: int = 200,
        time_limit_s: float = 5.0,
    ):
        """
        Args:
            graph: {node_id: [(neighbor_id, cost), ...]}
            max_agents: Maximum agents to plan for.
            time_limit_s: Time limit for the CBS search.
        """
        self._graph = graph
        self._max_agents = max_agents
        self._time_limit = time_limit_s

    def solve(self, agents: list[dict]) -> dict:
        """
        Find conflict-free paths for all agents.

        Args:
            agents: [{agent_id, start, goal}]

        Returns:
            {
                paths: {agent_id: [node_id, ...]},
                cost: total path cost,
                conflicts_resolved: int,
                solve_time_ms: float,
                success: bool
            }

        Raises:
            ValueError: If agent count exceeds max_agents or duplicate agent_ids.
        """
        # Guard: max agents
        if len(agents) > self._max_agents:
            raise ValueError(
                f"Too many agents: {len(agents)} exceeds max_agents={self._max_agents}"
            )

        # Guard: duplicate agent IDs
        agent_ids = [a["agent_id"] for a in agents]
        if len(agent_ids) != len(set(agent_ids)):
            seen: set[str] = set()
            for aid in agent_ids:
                if aid in seen:
                    raise ValueError(f"Duplicate agent_id: {aid}")
                seen.add(aid)

        start_time = time.monotonic()

        # 1. Find initial paths (independent A* per agent)
        root_paths = {}
        has_unreachable = False
        for agent in agents:
            path = self._low_level_astar(agent["start"], agent["goal"], [], [])
            if path is None:
                path = [agent["start"]]
                # Agent couldn't reach goal — mark as unreachable
                if agent["start"] != agent["goal"]:
                    has_unreachable = True
            root_paths[agent["agent_id"]] = path

        root_cost = sum(max(0, len(p) - 1) for p in root_paths.values())
        node_counter = 0
        root_node = _CTNode(
            cost=root_cost,
            id=node_counter,
            # Each agent has vertex_constraints and edge_constraints
            constraints={aid: {"vertex": [], "edge": []} for aid in agent_ids},
            paths=root_paths,
        )

        open_list: list[_CTNode] = []
        heapq.heappush(open_list, root_node)

        best_node = root_node
        conflicts_resolved = 0

        while open_list:
            elapsed = time.monotonic() - start_time
            if elapsed >= self._time_limit:
                break

            current = heapq.heappop(open_list)

            conflict = self._find_first_conflict(current.paths)
            if conflict is None:
                best_node = current
                break

            if current.cost <= best_node.cost:
                best_node = current

            conflicts_resolved += 1

            # Branch: for each agent involved in the conflict, add a constraint
            for agent_id in [conflict["agent_i"], conflict["agent_j"]]:
                node_counter += 1

                # Deep copy constraints
                new_constraints = {
                    aid: {"vertex": list(c["vertex"]), "edge": list(c["edge"])}
                    for aid, c in current.constraints.items()
                }

                if conflict["type"] == "vertex":
                    # Vertex constraint: agent cannot be at node at timestep
                    new_constraints[agent_id]["vertex"].append({
                        "node": conflict["node"],
                        "timestep": conflict["timestep"],
                    })
                else:
                    # Edge constraint: agent cannot traverse from→to at timestep
                    # For agent_i: cannot move from its prev position to conflict node
                    # For agent_j: cannot move from its prev position to conflict node
                    # We determine which edge to block based on which agent we're constraining
                    if agent_id == conflict["agent_i"]:
                        new_constraints[agent_id]["edge"].append({
                            "from": conflict["ai_from"],
                            "to": conflict["ai_to"],
                            "timestep": conflict["timestep"],
                        })
                    else:
                        new_constraints[agent_id]["edge"].append({
                            "from": conflict["aj_from"],
                            "to": conflict["aj_to"],
                            "timestep": conflict["timestep"],
                        })

                agent_info = next(a for a in agents if a["agent_id"] == agent_id)
                new_path = self._low_level_astar(
                    agent_info["start"],
                    agent_info["goal"],
                    new_constraints[agent_id]["vertex"],
                    new_constraints[agent_id]["edge"],
                )

                if new_path is None:
                    # No valid path exists with these constraints — skip this branch
                    continue

                new_paths = dict(current.paths)
                new_paths[agent_id] = new_path

                new_cost = sum(max(0, len(p) - 1) for p in new_paths.values())
                child = _CTNode(
                    cost=new_cost,
                    id=node_counter,
                    constraints=new_constraints,
                    paths=new_paths,
                )
                heapq.heappush(open_list, child)

        elapsed_ms = (time.monotonic() - start_time) * 1000.0

        # Pad paths to same length (agents wait at goal)
        paths = dict(best_node.paths)
        if paths:
            max_len = max(len(p) for p in paths.values())
            for aid in paths:
                while len(paths[aid]) < max_len:
                    paths[aid].append(paths[aid][-1])

        final_cost = sum(max(0, len(p) - 1) for p in paths.values())

        conflict = self._find_first_conflict(paths)
        # Success requires: no conflicts AND every agent reached its goal
        success = conflict is None and not has_unreachable
        # Also verify each agent's final position matches its goal
        if success:
            for agent in agents:
                aid = agent["agent_id"]
                if paths[aid][-1] != agent["goal"]:
                    success = False
                    break

        return {
            "paths": paths,
            "cost": final_cost,
            "conflicts_resolved": conflicts_resolved,
            "solve_time_ms": round(elapsed_ms, 3),
            "success": success,
        }

    def _low_level_astar(
        self,
        start: str,
        goal: str,
        vertex_constraints: list[dict],
        edge_constraints: list[dict],
    ) -> list[str] | None:
        """A* with time-space constraints.

        Vertex constraints: (node, timestep) — agent cannot be at node at time t.
        Edge constraints: (from, to, timestep) — agent cannot move from→to at time t.

        Returns the path as a list of node IDs, or None if no path exists.
        """
        if start == goal:
            blocked = any(c["node"] == start and c["timestep"] == 0 for c in vertex_constraints)
            if not blocked:
                return [start]

        # Build fast lookups
        vertex_set: set[tuple[str, int]] = set()
        max_constraint_t = 0
        for c in vertex_constraints:
            t = c["timestep"]
            vertex_set.add((c["node"], t))
            if t > max_constraint_t:
                max_constraint_t = t

        edge_set: set[tuple[str, str, int]] = set()
        for c in edge_constraints:
            t = c["timestep"]
            edge_set.add((c["from"], c["to"], t))
            if t > max_constraint_t:
                max_constraint_t = t

        n_nodes = len(self._graph)
        max_timestep = max(n_nodes * 4, max_constraint_t + n_nodes * 3, 40)

        open_set: list[tuple[float, int, str, int]] = []
        counter = 0
        h_start = self._heuristic(start, goal)
        heapq.heappush(open_set, (h_start, counter, start, 0))

        g_score: dict[tuple[str, int], float] = {(start, 0): 0}
        came_from: dict[tuple[str, int], tuple[str, int] | None] = {(start, 0): None}

        while open_set:
            f, _, current_node, current_t = heapq.heappop(open_set)

            if current_node == goal and current_t >= max_constraint_t:
                path = []
                state: tuple[str, int] | None = (current_node, current_t)
                while state is not None:
                    path.append(state[0])
                    state = came_from.get(state)
                path.reverse()
                return path

            if current_t >= max_timestep:
                continue

            next_t = current_t + 1

            neighbors = [(n, c) for n, c in self._graph.get(current_node, [])]
            neighbors.append((current_node, 0.0))  # Wait action (zero cost)

            for neighbor, edge_cost in neighbors:
                # Check vertex constraint
                if (neighbor, next_t) in vertex_set:
                    continue

                # Check edge constraint
                if (current_node, neighbor, next_t) in edge_set:
                    continue

                # Use actual edge cost from graph (wait = 0.0, move = real distance)
                # Minimum cost of 1.0 for moves to ensure timestep consistency
                move_cost = max(edge_cost, 1.0) if neighbor != current_node else 1.0
                new_g = g_score[(current_node, current_t)] + move_cost
                state_key = (neighbor, next_t)

                if state_key not in g_score or new_g < g_score[state_key]:
                    g_score[state_key] = new_g
                    h = self._heuristic(neighbor, goal)
                    f_val = new_g + h
                    counter += 1
                    heapq.heappush(open_set, (f_val, counter, neighbor, next_t))
                    came_from[state_key] = (current_node, current_t)

        return None

    def _heuristic(self, node: str, goal: str) -> float:
        """Admissible heuristic: 0 if same node, 1 if neighbor, else 2+.
        
        Uses graph distance estimation based on adjacency.
        This is admissible (never overestimates) for unweighted graphs.
        """
        if node == goal:
            return 0.0
        # Check if goal is directly reachable
        neighbors = self._graph.get(node, [])
        if any(n == goal for n, _ in neighbors):
            return 1.0
        # Conservative estimate: at least 2 steps needed
        return 2.0

    def _find_first_conflict(self, paths: dict[str, list[str]]) -> dict | None:
        """Find first vertex or edge conflict between any two agents.

        Vertex conflict: two agents at the same node at the same timestep.
        Edge conflict: two agents swap positions between consecutive timesteps.
        """
        agent_ids = list(paths.keys())
        if len(agent_ids) < 2:
            return None

        max_t = max(len(p) for p in paths.values())

        def _pos(aid: str, t: int) -> str:
            p = paths[aid]
            return p[t] if t < len(p) else p[-1]

        for t in range(max_t):
            # Vertex conflicts
            seen: dict[str, str] = {}
            for aid in agent_ids:
                pos = _pos(aid, t)
                if pos in seen:
                    return {
                        "type": "vertex",
                        "agent_i": seen[pos],
                        "agent_j": aid,
                        "node": pos,
                        "timestep": t,
                    }
                seen[pos] = aid

            # Edge conflicts (swap) for t > 0
            if t > 0:
                for i in range(len(agent_ids)):
                    for j in range(i + 1, len(agent_ids)):
                        ai, aj = agent_ids[i], agent_ids[j]
                        ai_prev, ai_curr = _pos(ai, t - 1), _pos(ai, t)
                        aj_prev, aj_curr = _pos(aj, t - 1), _pos(aj, t)
                        if ai_prev == aj_curr and aj_prev == ai_curr:
                            return {
                                "type": "edge",
                                "agent_i": ai,
                                "agent_j": aj,
                                "node": ai_curr,
                                "timestep": t,
                                "ai_from": ai_prev,
                                "ai_to": ai_curr,
                                "aj_from": aj_prev,
                                "aj_to": aj_curr,
                            }

        return None

    @staticmethod
    def build_graph_from_warehouse(warehouse_config: dict) -> dict[str, list[tuple[str, float]]]:
        """Convert warehouse JSON to adjacency dict for CBS.

        Edges are bidirectional. Cost is Euclidean distance between nodes.
        """
        positions: dict[str, tuple[float, float]] = {}
        for node in warehouse_config.get("nodes", []):
            positions[node["name"]] = (float(node["x"]), float(node["y"]))

        graph: dict[str, list[tuple[str, float]]] = {
            node["name"]: [] for node in warehouse_config.get("nodes", [])
        }

        for edge in warehouse_config.get("edges", []):
            a, b = edge["from"], edge["to"]
            if a in positions and b in positions:
                dx = positions[a][0] - positions[b][0]
                dy = positions[a][1] - positions[b][1]
                cost = math.sqrt(dx * dx + dy * dy)

                if not any(n == b for n, _ in graph.get(a, [])):
                    graph[a].append((b, cost))
                if not any(n == a for n, _ in graph.get(b, [])):
                    graph[b].append((a, cost))

        return graph

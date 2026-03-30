"""
Priority Inheritance with Backtracking (PIBT) — fast online MAPF.

Better than CBS for real-time replanning (100+ robots).
CBS is optimal but slow; PIBT is suboptimal but fast enough for 15Hz.

Algorithm:
  1. Sort agents by priority (highest first)
  2. For each agent, try to move toward goal
  3. If blocked by lower-priority agent, that agent inherits priority
     and tries to move out of the way
  4. If backtracking fails, agent waits in place

Phase 11: Scale to 100+ Robots.
"""

import math
from typing import Any


class PIBTSolver:
    """Priority Inheritance with Backtracking — fast online MAPF.

    Better than CBS for real-time replanning (100+ robots).
    CBS is optimal but slow; PIBT is suboptimal but fast enough for 15Hz.
    """

    def step(
        self,
        agents: list[dict],
        graph: dict[str, list[tuple[str, float]]],
    ) -> dict:
        """One timestep of PIBT — returns next position for each agent.

        Args:
            agents: [{agent_id, position, goal, priority, wait_time}]
            graph: {node_id: [(neighbor_id, cost), ...]}

        Returns:
            {
                success: bool,
                moves: {agent_id: next_node},
            }
        """
        # Guard: duplicate agent IDs
        agent_ids = [a["agent_id"] for a in agents]
        if len(agent_ids) != len(set(agent_ids)):
            seen: set[str] = set()
            for aid in agent_ids:
                if aid in seen:
                    raise ValueError(f"Duplicate agent_id: {aid}")
                seen.add(aid)

        # Sort by priority: highest priority first, then longest wait_time
        sorted_agents = self._priority_sort(agents)

        # Current positions and occupied set
        occupied: set[str] = set()
        moves: dict[str, str] = {}
        resolved: set[str] = set()  # Agents whose move has been decided

        # Map agent_id -> agent for quick lookup
        agent_map = {a["agent_id"]: a for a in sorted_agents}

        # Map position -> agent_id (current positions)
        pos_to_agent: dict[str, str] = {}
        for agent in sorted_agents:
            pos_to_agent[agent["position"]] = agent["agent_id"]

        # Process each agent in priority order
        for agent in sorted_agents:
            aid = agent["agent_id"]
            if aid in resolved:
                continue

            # Track call stack to prevent recursion cycles
            call_stack: set[str] = set()
            self._pibt_step_agent(
                aid, agent_map, graph, occupied, moves, resolved,
                pos_to_agent, call_stack,
            )

        # Any unresolved agents stay in place
        for agent in sorted_agents:
            aid = agent["agent_id"]
            if aid not in moves:
                moves[aid] = agent["position"]
                occupied.add(agent["position"])

        return {
            "success": True,
            "moves": moves,
        }

    def _pibt_step_agent(
        self,
        agent_id: str,
        agent_map: dict[str, dict],
        graph: dict[str, list[tuple[str, float]]],
        occupied: set[str],
        moves: dict[str, str],
        resolved: set[str],
        pos_to_agent: dict[str, str],
        call_stack: set[str],
    ) -> bool:
        """Recursively try to move an agent. Returns True if successful.

        Priority inheritance: if a higher-priority agent needs to move through
        a lower-priority agent's position, the lower-priority agent is asked
        to move first.

        call_stack prevents infinite recursion from cyclic push chains.
        """
        # Cycle detection: if this agent is already being processed, stop
        if agent_id in call_stack:
            return False

        call_stack.add(agent_id)

        agent = agent_map[agent_id]
        current = agent["position"]
        goal = agent["goal"]

        # If at goal, stay
        if current == goal:
            moves[agent_id] = current
            occupied.add(current)
            resolved.add(agent_id)
            return True

        # Get neighbors sorted by distance to goal (greedy heuristic)
        neighbors = graph.get(current, [])
        scored_neighbors = []
        for neighbor, cost in neighbors:
            dist = self._distance_to_goal(neighbor, goal, graph)
            scored_neighbors.append((dist, neighbor))

        scored_neighbors.sort()  # Closest to goal first

        # Try each neighbor
        for _, next_node in scored_neighbors:
            if next_node in occupied:
                continue

            # Check if another agent is currently there
            blocking_agent = pos_to_agent.get(next_node)
            if blocking_agent and blocking_agent != agent_id and blocking_agent not in resolved:
                # Priority inheritance: ask blocking agent to move first
                success = self._pibt_step_agent(
                    blocking_agent, agent_map, graph, occupied, moves,
                    resolved, pos_to_agent, call_stack,
                )
                if not success:
                    continue
                # After blocking agent moved, check if next_node is now free
                if next_node in occupied:
                    continue

            if next_node not in occupied:
                moves[agent_id] = next_node
                occupied.add(next_node)
                resolved.add(agent_id)
                return True

        # All neighbors blocked — wait in place
        moves[agent_id] = current
        occupied.add(current)
        resolved.add(agent_id)
        return False

    def _priority_sort(self, agents: list[dict]) -> list[dict]:
        """Sort by priority: waiting longest > carrying load > distance to goal.

        Higher priority value = processed first.
        Ties broken by wait_time (longer wait = higher priority).
        """
        return sorted(
            agents,
            key=lambda a: (a.get("priority", 0), a.get("wait_time", 0)),
            reverse=True,
        )

    @staticmethod
    def _distance_to_goal(
        node: str,
        goal: str,
        graph: dict[str, list[tuple[str, float]]],
    ) -> float:
        """Simple BFS distance (hop count) as heuristic for greedy neighbor selection."""
        if node == goal:
            return 0.0

        from collections import deque

        visited = {node}
        queue = deque([(node, 0)])

        while queue:
            current, dist = queue.popleft()
            for neighbor, _ in graph.get(current, []):
                if neighbor == goal:
                    return float(dist + 1)
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, dist + 1))

        # No path — large penalty
        return float("inf")

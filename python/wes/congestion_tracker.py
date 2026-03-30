"""
CongestionTracker — track congestion hotspots for 100+ robot fleets.

Maintains per-node metrics:
  - occupancy: total robot-ticks at this node
  - wait_time_avg: average consecutive ticks a robot stays
  - throughput: unique robots that visited this node

Phase 11: Scale to 100+ Robots.
"""

from collections import defaultdict


class CongestionTracker:
    """Track congestion hotspots for 100+ robot fleets."""

    def __init__(self):
        # Per-node occupancy count (total robot-ticks)
        self._occupancy: dict[str, int] = defaultdict(int)
        # Per-node unique robot set (for throughput)
        self._unique_robots: dict[str, set[str]] = defaultdict(set)
        # Track last position per robot (for consecutive wait counting)
        self._last_position: dict[str, str] = {}
        # Per-node total consecutive wait ticks (for avg wait time)
        self._wait_ticks: dict[str, int] = defaultdict(int)
        # Per-node number of wait events (for averaging)
        self._wait_events: dict[str, int] = defaultdict(int)

    def update(self, robot_positions: dict[str, str]):
        """Update node occupancy counts.

        Args:
            robot_positions: {robot_id: node_id}
        """
        for robot_id, node_id in robot_positions.items():
            self._occupancy[node_id] += 1
            self._unique_robots[node_id].add(robot_id)

            # Track consecutive waiting
            if self._last_position.get(robot_id) == node_id:
                self._wait_ticks[node_id] += 1
                self._wait_events[node_id] += 1
            else:
                # Robot just arrived — start tracking
                self._wait_events[node_id] += 1

            self._last_position[robot_id] = node_id

    def get_congestion_map(self) -> dict:
        """Return {node_id: {occupancy, wait_time_avg, throughput}}.

        Returns:
            Dict mapping node IDs to congestion metrics.
        """
        result = {}
        for node_id in self._occupancy:
            wait_events = self._wait_events.get(node_id, 0)
            wait_ticks = self._wait_ticks.get(node_id, 0)
            result[node_id] = {
                "occupancy": self._occupancy[node_id],
                "wait_time_avg": round(wait_ticks / max(wait_events, 1), 2),
                "throughput": len(self._unique_robots.get(node_id, set())),
            }
        return result

    def get_bottlenecks(self, top_n: int = 5) -> list[dict]:
        """Return top N congested nodes.

        Sorted by occupancy descending.

        Args:
            top_n: Number of top bottleneck nodes to return.

        Returns:
            [{node_id, occupancy, wait_time_avg, throughput}, ...]
        """
        cmap = self.get_congestion_map()
        if not cmap:
            return []

        sorted_nodes = sorted(
            cmap.items(),
            key=lambda item: item[1]["occupancy"],
            reverse=True,
        )

        return [
            {"node_id": node_id, **metrics}
            for node_id, metrics in sorted_nodes[:top_n]
        ]

    def reset(self):
        """Clear all tracked data."""
        self._occupancy.clear()
        self._unique_robots.clear()
        self._last_position.clear()
        self._wait_ticks.clear()
        self._wait_events.clear()

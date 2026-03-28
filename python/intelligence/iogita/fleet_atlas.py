"""
FleetAtlas — multi-robot fingerprint aggregation and map change detection.

Aggregates individual robot zone identifications into a fleet-level
"atlas" that tracks:
- Which zones are occupied
- Zone transition patterns
- Map drift / change detection (nodes added/removed)
"""

import time
import numpy as np
from typing import Any, Optional


class FleetAtlas:
    """
    Aggregates zone identification results across the entire fleet.
    Detects when the map has changed (nodes added/removed).
    """

    def __init__(self, zones: list[dict], nodes: list[dict]):
        """
        Args:
            zones: Zone definitions from warehouse config.
            nodes: Node definitions.
        """
        self.zones = {z["name"]: z for z in zones}
        self.nodes = {n["name"]: n for n in nodes}
        self._fingerprints: dict[str, dict[str, Any]] = {}
        self._zone_history: list[dict[str, Any]] = []
        self._map_hash = self._compute_map_hash(nodes)

    def _compute_map_hash(self, nodes: list[dict]) -> int:
        """Compute a hash of the map structure for change detection."""
        node_names = sorted(n["name"] for n in nodes)
        coords = [(n["name"], n.get("x", 0), n.get("y", 0)) for n in nodes]
        return hash(tuple(node_names) + tuple(str(c) for c in coords))

    def update_fingerprint(self, robot_id: str, zone: str, pose: dict[str, float]):
        """
        Update the fingerprint for a robot.

        Args:
            robot_id: Robot identifier.
            zone: Current zone name.
            pose: {x, y, theta} position.
        """
        now = time.time()
        prev = self._fingerprints.get(robot_id)

        self._fingerprints[robot_id] = {
            "robot_id": robot_id,
            "zone": zone,
            "pose": pose,
            "updated_at": now,
        }

        # Record zone transition
        if prev is not None and prev["zone"] != zone:
            self._zone_history.append({
                "robot_id": robot_id,
                "from_zone": prev["zone"],
                "to_zone": zone,
                "timestamp": now,
            })

    def get_fleet_snapshot(self) -> dict[str, Any]:
        """
        Return current fleet-wide zone occupation summary.
        """
        zone_counts: dict[str, int] = {}
        for fp in self._fingerprints.values():
            z = fp["zone"]
            zone_counts[z] = zone_counts.get(z, 0) + 1

        return {
            "total_robots": len(self._fingerprints),
            "zone_occupation": zone_counts,
            "fingerprints": list(self._fingerprints.values()),
            "recent_transitions": self._zone_history[-20:],
        }

    def detect_map_change(self, new_nodes: list[dict]) -> dict[str, Any]:
        """
        Detect if the map has changed from the baseline.

        Args:
            new_nodes: Current node list.

        Returns:
            Dict with change detection results.
        """
        new_hash = self._compute_map_hash(new_nodes)
        changed = new_hash != self._map_hash

        if not changed:
            return {"changed": False, "added_nodes": [], "removed_nodes": []}

        old_names = set(self.nodes.keys())
        new_names = {n["name"] for n in new_nodes}

        added = sorted(new_names - old_names)
        removed = sorted(old_names - new_names)

        return {
            "changed": True,
            "added_nodes": added,
            "removed_nodes": removed,
        }

    def get_zone_transition_matrix(self) -> dict[str, Any]:
        """
        Compute zone transition matrix from history.

        Returns:
            Dict with zone names and transition counts.
        """
        zone_names = sorted(self.zones.keys())
        matrix: dict[str, dict[str, int]] = {z: {z2: 0 for z2 in zone_names} for z in zone_names}

        for transition in self._zone_history:
            fz = transition["from_zone"]
            tz = transition["to_zone"]
            if fz in matrix and tz in matrix[fz]:
                matrix[fz][tz] += 1

        return {
            "zone_names": zone_names,
            "transitions": matrix,
            "total_transitions": len(self._zone_history),
        }

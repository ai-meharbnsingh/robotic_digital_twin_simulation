"""
KDTree Adapter — drop-in replacement for HierarchicalZoneIdentifier.

Makes IoGitaEngine from iogita_kdtree_addverb work with all existing
Gazebo benchmark scripts that expect the HierarchicalZoneIdentifier interface.

Usage (one-line swap in any benchmark):
  # OLD: from intelligence.iogita.zone_identifier import HierarchicalZoneIdentifier
  # NEW:
  from intelligence.iogita.kdtree_adapter import KDTreeZoneIdentifier as HierarchicalZoneIdentifier

The adapter maps:
  HierarchicalZoneIdentifier methods → IoGitaEngine methods
  - __init__(zones, nodes, edges) → load_config()
  - get_node_dock_features(name) → returns (0, 0, 0) placeholder
  - set_node_fingerprint(name, scan, h, d, t) → stores scan for calibrate()
  - rebuild_hopfield() → calibrate(scans_dict)
  - identify_zone(scan) → identify_zone(scan)
  - identify_node(scan, ...) → identify_node(scan, ...)
"""

import os
import sys
import math
import numpy as np
from typing import Optional

# Import IoGitaEngine from the kdtree deliverable
_KDTREE_ROOT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..", "..",
    "iogita_kdtree_addverb",
)
if _KDTREE_ROOT not in sys.path:
    sys.path.insert(0, _KDTREE_ROOT)

from engine import IoGitaEngine


class KDTreeZoneIdentifier:
    """Drop-in adapter: wraps IoGitaEngine with HierarchicalZoneIdentifier interface."""

    def __init__(self, zones, nodes, edges=None):
        self._engine = IoGitaEngine()
        self._config = {
            "zones": zones,
            "nodes": nodes,
            "edges": edges or [],
        }
        self._engine.load_config(self._config)

        # Properties that existing code reads
        self.zones = zones
        self.nodes_by_name = {n["name"]: n for n in nodes}

        # Calibration data (collected via set_node_fingerprint)
        self._pending_cal_scans = {}
        self._calibrated = False

        # Zone/node maps
        self._node_to_zone = {}
        for z in zones:
            for nn in z.get("nodes", z.get("node_names", [])):
                self._node_to_zone[nn] = z["name"]

    def get_node_dock_features(self, node_name: str):
        """Compatibility: returns placeholder features (KDTree doesn't need these)."""
        node = self.nodes_by_name.get(node_name, {})
        # Return (heading, dock_dist, zone_type_id) — unused by KDTree
        return (0.0, 0.0, 0)

    def set_node_fingerprint(self, node_name: str, scan: np.ndarray,
                              heading=0, dock_dist=0, zone_type=0):
        """Store scan for later calibration."""
        if scan is not None and len(scan) > 0:
            self._pending_cal_scans[node_name] = np.asarray(scan, dtype=np.float64).copy()

    def rebuild_hopfield(self):
        """Calibrate the KDTree engine from collected scans."""
        if self._pending_cal_scans:
            self._engine.calibrate(self._pending_cal_scans)
            self._calibrated = True

    def identify_zone(self, scan: np.ndarray, last_known_node: str = "") -> dict:
        """Zone identification — delegates to KDTree engine."""
        return self._engine.identify_zone(scan, last_known_node)

    def identify_node(self, scan: np.ndarray, last_known_node: str = "",
                       heading_deg: float = 0.0, k: int = 5) -> dict:
        """Node identification — delegates to KDTree engine."""
        return self._engine.identify_node(scan, last_known_node, heading_deg, k)

    def full_recovery(self, scan: np.ndarray, last_known_node: str,
                       heading_deg: float = 0.0) -> dict:
        """Full recovery pipeline — delegates to KDTree engine."""
        return self._engine.full_recovery(scan, last_known_node, heading_deg)

    def identify(self, features):
        """Zone ID from [x, y] coordinates (pose-based, no LiDAR).
        Used by FastAPI routes.
        """
        x, y = features[0], features[1]
        best_node = None
        best_dist = float("inf")
        for name, node in self.nodes_by_name.items():
            d = math.sqrt((x - node["x"]) ** 2 + (y - node["y"]) ** 2)
            if d < best_dist:
                best_dist = d
                best_node = name
        if best_node:
            return self._node_to_zone.get(best_node, "unknown")
        return "unknown"

    def recover_from_last_known(self, scan_360: np.ndarray,
                                last_x: float, last_y: float,
                                heading_deg: float = 0.0, k: int = 5) -> dict:
        """4-clue recovery from last known (x, y) position.

        Maps to IoGitaEngine.identify_node() — finds nearest node to (last_x, last_y)
        and uses that as the last_known_node for the KDTree 4-clue scoring.
        """
        # Find nearest node to last known position
        best_node = ""
        best_dist = float("inf")
        for name, node in self.nodes_by_name.items():
            d = math.sqrt((node["x"] - last_x) ** 2 + (node["y"] - last_y) ** 2)
            if d < best_dist:
                best_dist = d
                best_node = name

        result = self._engine.full_recovery(scan_360, best_node, heading_deg)
        return {
            "zone": result["zone"],
            "node": result["node"],
            "confidence": result["zone_confidence"],
            "method": result["method"],
            "candidates": result.get("candidates", []),
        }

    def hierarchical_zone_id(self, scan: np.ndarray, previous_zone=None) -> dict:
        """Zone identification (Hopfield compat name)."""
        result = self._engine.identify_zone(scan)
        return {"zone": result["zone"], "confidence": result["confidence"]}

    @property
    def _cal_scans(self):
        """Access calibration scans (Hopfield compat)."""
        return self._engine._cal_scans

    @property
    def _zone_hopfield(self):
        """Shim: expose a rank_all interface using KDTree distances."""
        return _KDTreeRankShim(self._engine)

    @property
    def engine(self):
        """Direct access to underlying IoGitaEngine."""
        return self._engine

    @property
    def calibrated(self):
        return self._calibrated


class _KDTreeRankShim:
    """Makes KDTree zone distances look like Hopfield rank_all output."""

    def __init__(self, engine: IoGitaEngine):
        self._engine = engine

    def rank_all(self, features):
        """Return (ranked_list, distances) similar to Hopfield's rank output."""
        if self._engine._zone_tree is None:
            return [], []
        k = len(self._engine._zone_names)
        dists, idxs = self._engine._zone_tree.query(features, k=k)
        if np.isscalar(idxs):
            idxs = [idxs]
            dists = [dists]
        ranked = []
        for d, i in zip(dists, idxs):
            sim = 1.0 / (1.0 + float(d))
            ranked.append((self._engine._zone_names[int(i)], sim))
        return ranked, list(dists)

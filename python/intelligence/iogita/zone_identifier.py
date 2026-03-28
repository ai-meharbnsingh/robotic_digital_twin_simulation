"""
ZoneIdentifier — identifies which warehouse zone a robot occupies.

Wraps sg_engine Network if available, otherwise falls back to an
inline Hopfield energy-based classifier.

Performance target: <1ms per identification.
"""

import time
import numpy as np
from typing import Optional

# Try to import sg_engine from system path
_SG_AVAILABLE = False
try:
    from sg_engine.network import Network as SGNetwork
    _SG_AVAILABLE = True
except ImportError:
    SGNetwork = None


class _HopfieldFallback:
    """
    Inline Hopfield network for zone classification.
    Used when sg_engine is not installed.

    Stores zone patterns as attractors. Given a feature vector,
    converges to the nearest attractor (zone).
    """

    def __init__(self, patterns: dict[str, np.ndarray]):
        """
        Args:
            patterns: {zone_name: centroid_vector} — each zone's representative feature vector.
        """
        self.patterns = patterns
        self.zone_names = list(patterns.keys())
        if self.zone_names:
            dim = len(next(iter(patterns.values())))
            # Weight matrix: sum of outer products of patterns (Hebbian learning)
            self.W = np.zeros((dim, dim))
            for p in patterns.values():
                pn = p / (np.linalg.norm(p) + 1e-12)
                self.W += np.outer(pn, pn)
            # Zero diagonal
            np.fill_diagonal(self.W, 0)
        else:
            self.W = np.array([])

    def identify(self, features: np.ndarray, max_iter: int = 5) -> str:
        """
        Converge to nearest attractor and return zone name.
        """
        if len(self.zone_names) == 0:
            return "unknown"

        # Normalize input
        state = features / (np.linalg.norm(features) + 1e-12)

        # Iterate
        for _ in range(max_iter):
            state = np.sign(self.W @ state)
            state = np.where(state == 0, 1, state)

        # Find closest pattern by cosine similarity
        best_zone = "unknown"
        best_sim = -float("inf")
        for name, pat in self.patterns.items():
            pn = pat / (np.linalg.norm(pat) + 1e-12)
            sim = float(np.dot(state, pn))
            if sim > best_sim:
                best_sim = sim
                best_zone = name

        return best_zone


class ZoneIdentifier:
    """
    Identifies which warehouse zone a robot is in based on its position features.

    Uses sg_engine Network if available, otherwise falls back to Hopfield.
    """

    def __init__(self, zones: list[dict], nodes: list[dict]):
        """
        Args:
            zones: Zone definitions from warehouse config [{name, type, nodes}]
            nodes: Node definitions [{name, x, y, type}]
        """
        self.zones = zones
        self.nodes_by_name = {n["name"]: n for n in nodes}
        self.num_zones = len(zones)
        self._sg_network = None
        self._fallback = None

        # Build zone centroids
        self._zone_centroids: dict[str, np.ndarray] = {}
        for zone in zones:
            zone_nodes = zone.get("nodes", [])
            if not zone_nodes:
                continue
            coords = []
            for nn in zone_nodes:
                node = self.nodes_by_name.get(nn)
                if node:
                    coords.append([node["x"], node["y"]])
            if coords:
                self._zone_centroids[zone["name"]] = np.mean(coords, axis=0)

        if _SG_AVAILABLE and SGNetwork is not None:
            self.backend = "sg_engine"
            self._init_sg_engine()
        else:
            self.backend = "hopfield_fallback"
            self._fallback = _HopfieldFallback(self._zone_centroids)

    def _init_sg_engine(self):
        """Initialize sg_engine Network with zone patterns."""
        try:
            self._sg_network = SGNetwork(dim=2)
            for name, centroid in self._zone_centroids.items():
                self._sg_network.add_attractor(centroid, label=name)
        except Exception:
            self.backend = "hopfield_fallback"
            self._fallback = _HopfieldFallback(self._zone_centroids)

    def identify(self, features: list[float]) -> str:
        """
        Identify zone from a feature vector (x, y).

        Args:
            features: [x, y] position

        Returns:
            Zone name string.
        """
        feat_arr = np.array(features, dtype=np.float64)

        if self._sg_network is not None:
            try:
                result = self._sg_network.classify(feat_arr)
                if isinstance(result, str):
                    return result
                return str(result)
            except Exception:
                pass

        if self._fallback is not None:
            return self._fallback.identify(feat_arr)

        # Direct distance fallback
        return self._nearest_zone(feat_arr)

    def identify_timed(self, features: list[float]) -> tuple[str, float]:
        """
        Identify zone and return (zone_name, elapsed_ms).
        """
        start = time.perf_counter()
        zone = self.identify(features)
        elapsed_ms = (time.perf_counter() - start) * 1000
        return zone, elapsed_ms

    def _nearest_zone(self, features: np.ndarray) -> str:
        """Fallback: nearest centroid by Euclidean distance."""
        best = "unknown"
        best_dist = float("inf")
        for name, centroid in self._zone_centroids.items():
            dist = float(np.linalg.norm(features - centroid))
            if dist < best_dist:
                best_dist = dist
                best = name
        return best

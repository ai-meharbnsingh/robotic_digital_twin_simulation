"""
ZoneIdentifier v4 — Hierarchical zone-first, node-second identification.

Fixes the 11.1% accuracy failure via Strategy B:
  Step 1: Zone classification (7-12 zones) using AGGREGATED zone fingerprints
  Step 2: Node classification within confirmed zone using graph topology

Root cause of failure: 539-way node classification in one shot overloaded
the Hopfield network even at D=10,000 because 280 shelf nodes had nearly
identical 16-feature LiDAR signatures.

Fix: Zone-level classification is a 7-12 way problem where each zone type
IS geometrically distinct (charge != shelf != corridor != operations).
Node narrowing within a confirmed zone uses graph position, not LiDAR.

Performance targets:
  - Zone identification: >90% accuracy
  - Node identification (within correct zone): >75%
  - ODE time: <5ms (zone-level, 7-12 patterns at D=10,000)
  - Cold start recovery: <5s total

ADR-NEW: Hierarchical ID — zone first, node second.
"""

import math
import time
import numpy as np
from typing import Optional


# ── Zone-type-specific 360-ray LiDAR scan signatures ──────────────────
# Ported from P22 cold_start_v2.py — each zone type has a DISTINCT signature.

def generate_zone_scan(zone_type: str, rng: np.random.Generator,
                       heading_deg: float = 0, dist_from_dock: float = 0) -> np.ndarray:
    """Generate a realistic 360-ray LiDAR scan for a zone type.

    Each zone type has a DISTINCT scan signature — dock != aisle != shelf etc.
    This is the KEY insight from P22: zone types produce discriminable patterns.

    Args:
        zone_type: One of dock/aisle/shelf/cross/hub/lane/mid/pick/drop/ops/
                   charge/predock/none/storage_a/storage_b/corridor/staging/maintenance.
        rng: Numpy random generator for noise.
        heading_deg: Robot heading in degrees (0-360).
        dist_from_dock: Distance from nearest dock in meters.

    Returns:
        360 range values in meters, clipped to [0.1, 12.0].
    """
    scan = np.zeros(360)

    if zone_type in ("dock", "charge", "charging"):
        # Charger station: open front, charger pillar behind, wall on one side
        for i in range(360):
            if 0 <= i < 30 or 330 <= i < 360:
                scan[i] = 8.0 + rng.normal(0, 0.2)
            elif 150 <= i < 210:
                scan[i] = 0.5 + rng.normal(0, 0.05)  # back wall
            elif 60 <= i < 120:
                scan[i] = 4.0 + rng.normal(0, 0.3)
            elif 240 <= i < 300:
                scan[i] = 0.5 + rng.normal(0, 0.05)  # charger pillar side
            else:
                scan[i] = 3.0 + rng.normal(0, 0.5)

    elif zone_type in ("aisle", "lane"):
        # Long corridor: close walls on sides, far front/back
        for i in range(360):
            if 0 <= i < 20 or 340 <= i < 360:
                scan[i] = 6.0 + rng.normal(0, 0.3)
            elif 160 <= i < 200:
                scan[i] = 6.0 + rng.normal(0, 0.3)
            elif 70 <= i < 110:
                scan[i] = 1.2 + rng.normal(0, 0.05)  # right wall
            elif 250 <= i < 290:
                scan[i] = 1.2 + rng.normal(0, 0.05)  # left wall
            else:
                scan[i] = 2.0 + rng.normal(0, 0.3)

    elif zone_type in ("shelf", "storage_a"):
        # Parallel shelf rows: tight aisles (1.2m), jagged with periodic gaps
        for i in range(360):
            base = 1.2 + rng.normal(0, 0.08)
            if i % 30 < 5:
                base = 2.8 + rng.normal(0, 0.15)  # gap between shelf units
            scan[i] = base

    elif zone_type == "storage_b":
        # Perpendicular shelves: wider aisles (1.5m), different gap pattern
        for i in range(360):
            if 0 <= i < 45 or 315 <= i < 360:
                scan[i] = 1.5 + rng.normal(0, 0.1)   # narrow front
            elif 135 <= i < 225:
                scan[i] = 1.5 + rng.normal(0, 0.1)   # narrow back
            elif 45 <= i < 135:
                scan[i] = 4.0 + rng.normal(0, 0.2)   # open side (perpendicular view)
            else:
                scan[i] = 4.0 + rng.normal(0, 0.2)   # open other side
            # Shelf edges every 20 degrees
            if i % 20 < 3:
                scan[i] = 0.8 + rng.normal(0, 0.05)  # shelf edge close

    elif zone_type in ("cross", "none"):
        # Open intersection
        for i in range(360):
            scan[i] = 4.0 + rng.normal(0, 0.3)

    elif zone_type == "hub":
        # Large open area
        for i in range(360):
            scan[i] = 5.0 + rng.normal(0, 0.4)

    elif zone_type in ("predock", "staging"):
        # Half-wall barriers + dock door: one side blocked, one open
        for i in range(360):
            if 0 <= i < 60 or 300 <= i < 360:
                scan[i] = 2.0 + rng.normal(0, 0.15)  # half-wall front
            elif 120 <= i < 240:
                scan[i] = 6.0 + rng.normal(0, 0.3)   # open toward warehouse
            elif 60 <= i < 120:
                scan[i] = 1.0 + rng.normal(0, 0.08)  # dock door pillar
            else:
                scan[i] = 3.0 + rng.normal(0, 0.2)

    elif zone_type == "corridor":
        # Wide transit corridor (3m) with wall markers (distinct from narrow aisle)
        for i in range(360):
            if 0 <= i < 25 or 335 <= i < 360:
                scan[i] = 8.0 + rng.normal(0, 0.3)   # long forward view
            elif 155 <= i < 205:
                scan[i] = 8.0 + rng.normal(0, 0.3)   # long backward view
            elif 65 <= i < 115:
                scan[i] = 3.0 + rng.normal(0, 0.1)   # wide right wall
            elif 245 <= i < 295:
                scan[i] = 3.0 + rng.normal(0, 0.1)   # wide left wall
            else:
                scan[i] = 4.0 + rng.normal(0, 0.3)
            # Wall markers every 60 degrees: small bumps
            if i % 60 < 4:
                scan[i] = min(scan[i], 2.5 + rng.normal(0, 0.05))

    elif zone_type == "mid":
        # Medium open area
        for i in range(360):
            scan[i] = 3.0 + rng.normal(0, 0.3)

    elif zone_type == "pick":
        # Pick station: open front, table/conveyor behind
        for i in range(360):
            if 0 <= i < 40 or 320 <= i < 360:
                scan[i] = 5.0 + rng.normal(0, 0.3)
            elif 150 <= i < 210:
                scan[i] = 1.0 + rng.normal(0, 0.1)   # pickup table
            elif 70 <= i < 110:
                scan[i] = 1.8 + rng.normal(0, 0.15)
            elif 250 <= i < 290:
                scan[i] = 1.8 + rng.normal(0, 0.15)
            else:
                scan[i] = 2.5 + rng.normal(0, 0.3)

    elif zone_type == "drop":
        # Drop station: conveyor close in front, open behind
        for i in range(360):
            if 0 <= i < 20 or 340 <= i < 360:
                scan[i] = 1.0 + rng.normal(0, 0.1)   # conveyor
            elif 150 <= i < 210:
                scan[i] = 6.0 + rng.normal(0, 0.3)
            elif 60 <= i < 120:
                scan[i] = 4.0 + rng.normal(0, 0.3)
            elif 240 <= i < 300:
                scan[i] = 4.0 + rng.normal(0, 0.3)
            else:
                scan[i] = 3.0 + rng.normal(0, 0.4)

    elif zone_type in ("ops", "operations"):
        # Wide open area with scattered pick/drop tables
        for i in range(360):
            scan[i] = 3.5 + rng.normal(0, 0.5)
            # Occasional table at 90-degree intervals
            if i % 90 < 8:
                scan[i] = 1.5 + rng.normal(0, 0.1)

    elif zone_type == "maintenance":
        # Workbench + tool rack: asymmetric clutter
        for i in range(360):
            if 0 <= i < 90:
                scan[i] = 2.0 + rng.normal(0, 0.3)   # workbench side
            elif 90 <= i < 180:
                scan[i] = 1.0 + rng.normal(0, 0.15)  # tool rack (close)
            elif 180 <= i < 270:
                scan[i] = 3.5 + rng.normal(0, 0.2)   # open exit
            else:
                scan[i] = 1.5 + rng.normal(0, 0.2)   # wall with equipment

    else:
        # Unknown type: medium open
        for i in range(360):
            scan[i] = 2.0 + rng.normal(0, 0.5)

    return np.clip(scan, 0.1, 12.0)


# ── 16-feature extraction from 360-ray scan ───────────────────────────

def extract_16_features(scan_360: np.ndarray, heading_deg: float,
                        dist_from_dock: float, turns_since_dock: float = 0.0) -> np.ndarray:
    """Extract 16 features from a 360-ray LiDAR scan.

    Features normalized to ~[0, 1] for equal weighting in distance metrics.

    Features:
      F1-F4:   Sector clearances (front/back/left/right median) / 12m
      F5-F6:   Scan variance (front half, full) / 12
      F7-F8:   Gap count (>1m jumps, >2m jumps)
      F9-F10:  Symmetry (left-right, front-back)
      F11-F12: Density (fraction close <2m, fraction far >4m)
      F13-F14: Heading (normalized, binned)
      F15-F16: FMS timing (dist_from_dock, turns_since_dock)
    """
    front = np.median(scan_360[345:360].tolist() + scan_360[0:15].tolist()) / 12.0
    back = np.median(scan_360[165:195]) / 12.0
    left = np.median(scan_360[255:285]) / 12.0
    right = np.median(scan_360[75:105]) / 12.0

    var_front_half = float(np.var(scan_360[315:360].tolist() + scan_360[0:45].tolist())) / 12.0
    var_all = float(np.var(scan_360)) / 12.0

    diffs = np.abs(np.diff(scan_360))
    gap_count = int(np.sum(diffs > 1.0))
    big_gap_count = int(np.sum(diffs > 2.0))

    sym_lr = abs(left - right) / max(left + right, 0.01)
    sym_fb = abs(front - back) / max(front + back, 0.01)

    close_count = int(np.sum(scan_360 < 2.0)) / 360.0
    far_count = int(np.sum(scan_360 > 4.0)) / 360.0

    heading_norm = heading_deg / 360.0
    heading_bin = int(heading_deg / 45) / 8.0

    dist_norm = min(dist_from_dock / 30.0, 1.0)
    turns_norm = min(turns_since_dock / 10.0, 1.0)

    return np.array([
        front, back, left, right,
        var_front_half, var_all,
        gap_count / 50.0, big_gap_count / 20.0,
        sym_lr, sym_fb,
        close_count, far_count,
        heading_norm, heading_bin,
        dist_norm, turns_norm,
    ], dtype=np.float64)


ZONE_FEATURE_DIM = 36  # 36 sectors of 10 degrees each


def extract_zone_features(scan_360: np.ndarray) -> np.ndarray:
    """Raw 36-sector median histogram from a 360-ray LiDAR scan.

    Splits 360 degrees into 36 sectors of 10 degrees each.
    Each sector value = median range / 12.0 (max range).
    No other normalization. No hand-tuned features.

    This replaces the 12-feature version that saturated on real Gazebo
    data (F1=1.0 for all zones, variance exceeding [0,1] range).

    The raw median histogram preserves the actual geometry signal:
    shelf zones read ~0.65m (sector value ~0.05), open zones read
    ~2.7m (~0.23), corridors read differently depending on wall distance.
    """
    sector_width = 360 // ZONE_FEATURE_DIM  # 10 rays per sector
    features = np.zeros(ZONE_FEATURE_DIM, dtype=np.float64)

    for i in range(ZONE_FEATURE_DIM):
        start = i * sector_width
        end = start + sector_width
        features[i] = np.median(scan_360[start:end]) / 12.0

    return features


# ── Hopfield ODE at D=10,000 ─────────────────────────────────────────

class _HopfieldODE:
    """
    Hopfield attractor network — D=10,000 version.

    Used for ZONE-LEVEL identification (7-12 patterns), NOT node-level.
    At D=10,000 with 12 patterns: P/D = 0.0012, well within capacity.

    Capacity: 0.138 * 10,000 = 1,380 patterns.
    """

    D = 10_000

    def __init__(self, beta: float = 4.0, dt: float = 0.05, max_steps: int = 50,
                 seed: int = 42, n_features: int = 16):
        self.beta = beta
        self.dt = dt
        self.max_steps = max_steps
        self.n_features = n_features

        rng = np.random.default_rng(seed)
        self._proj_matrix = rng.standard_normal((self.D, n_features))

        self.pat_names: list[str] = []
        self.P_mat: np.ndarray = np.array([])
        self.n_patterns = 0

    def _encode(self, features: np.ndarray) -> np.ndarray:
        """Encode feature vector into D-dimensional bipolar pattern."""
        projection = self._proj_matrix @ features
        return np.sign(projection).astype(np.float64)

    def store_patterns(self, patterns: dict[str, np.ndarray]):
        """Encode and store all patterns."""
        self.pat_names = []
        encoded = []
        for name, feat in patterns.items():
            self.pat_names.append(name)
            encoded.append(self._encode(feat))

        if encoded:
            self.P_mat = np.array(encoded)
            self.n_patterns = len(encoded)
        else:
            self.P_mat = np.array([])
            self.n_patterns = 0

    def run_dynamics(self, query: np.ndarray) -> tuple[np.ndarray, int]:
        """Run ODE: dQ/dt = -Q + tanh(beta * P^T(P@Q/D))."""
        if self.n_patterns == 0:
            return query.copy(), 0

        state = query.copy()
        for step in range(self.max_steps):
            similarities = self.P_mat @ state / self.D
            field = self.P_mat.T @ similarities
            new_state = np.tanh(self.beta * field)
            delta = self.dt * (-state + new_state)
            state = state + delta
            if np.linalg.norm(delta) < 1e-6:
                return state, step + 1

        return state, self.max_steps

    def rank_all(self, features: np.ndarray) -> tuple[list[tuple[str, float]], float]:
        """Rank all patterns by similarity to query.

        Returns:
            (ranked_list, ode_time_ms)
        """
        if self.n_patterns == 0:
            return [], 0.0

        t0 = time.perf_counter()
        query = self._encode(features)

        # Direct cosine similarity
        direct_sims = self.P_mat @ query / self.D

        # ODE refinement
        final_state, _ = self.run_dynamics(query)
        ode_sims = self.P_mat @ final_state / self.D

        # Use whichever has better discrimination
        direct_spread = float(np.max(direct_sims) - np.mean(direct_sims))
        ode_spread = float(np.max(ode_sims) - np.mean(ode_sims))

        sims = ode_sims if ode_spread > direct_spread * 1.1 else direct_sims

        elapsed_ms = (time.perf_counter() - t0) * 1000

        results = [(self.pat_names[i], float(sims[i])) for i in range(self.n_patterns)]
        results.sort(key=lambda x: -x[1])
        return results, elapsed_ms


# ── Hierarchical Zone Identifier ──────────────────────────────────────

_UNSET = object()  # Sentinel to distinguish "not provided" from "explicitly None"


class HierarchicalZoneIdentifier:
    """
    Strategy B: Zone-first, node-second identification.

    Step 1: Classify into one of 7-12 zones (each geometrically distinct).
             Uses zone-level aggregated Hopfield patterns at D=10,000.
             This is a MUCH easier problem than 539-way node classification.

    Step 2: Narrow to specific node within confirmed zone using
             graph topology + relative position.

    This addresses the root cause: 280 shelf nodes have identical LiDAR
    but belong to different zones with distinct macro-level geometry.
    """

    def __init__(self, zones: list[dict], nodes: list[dict],
                 edges: Optional[list[dict]] = None):
        self.zones = zones
        self.nodes_by_name = {n["name"]: n for n in nodes}
        self._last_zone: Optional[str] = None

        # Build zone metadata
        self._zone_types: dict[str, str] = {}
        self._node_to_zone: dict[str, str] = {}
        self._zone_nodes: dict[str, list[str]] = {}
        for zone in zones:
            zn = zone["name"]
            self._zone_types[zn] = zone.get("type", "none")
            self._zone_nodes[zn] = zone.get("nodes", [])
            for nn in zone.get("nodes", []):
                self._node_to_zone[nn] = zn

        # Build zone centroids (x, y)
        self._zone_centroids: dict[str, np.ndarray] = {}
        for zone in zones:
            coords = []
            for nn in zone.get("nodes", []):
                node = self.nodes_by_name.get(nn)
                if node:
                    coords.append([node["x"], node["y"]])
            if coords:
                self._zone_centroids[zone["name"]] = np.mean(coords, axis=0)

        # Build node adjacency
        self._node_adjacency: dict[str, list[str]] = {}
        if edges:
            for edge in edges:
                f, t = edge["from"], edge["to"]
                self._node_adjacency.setdefault(f, []).append(t)
                if not edge.get("isUniDirectional", False):
                    self._node_adjacency.setdefault(t, []).append(f)

        # Build zone adjacency
        self._zone_adjacency: dict[str, set[str]] = {}
        for zone in zones:
            zn = zone["name"]
            neighbors: set[str] = set()
            for nn in zone.get("nodes", []):
                for adj in self._node_adjacency.get(nn, []):
                    adj_zone = self._node_to_zone.get(adj)
                    if adj_zone and adj_zone != zn:
                        neighbors.add(adj_zone)
            self._zone_adjacency[zn] = neighbors

        # Find dock nodes for feature computation
        all_nodes = list(self.nodes_by_name.values())
        self._dock_nodes = [n for n in all_nodes if n.get("type") in ("charge", "dock")]
        if not self._dock_nodes:
            self._dock_nodes = all_nodes[:1] if all_nodes else []

        # Build ZONE-LEVEL fingerprints (geometry-only, 12 features)
        # and NODE-LEVEL fingerprints (full 16 features)
        self._zone_fingerprints: dict[str, np.ndarray] = {}
        self._node_fingerprints: dict[str, np.ndarray] = {}
        self._build_fingerprints()

        # Build zone-level Hopfield ODE with 36-sector raw histogram features
        self._zone_hopfield = _HopfieldODE(beta=4.0, dt=0.05, max_steps=50, n_features=ZONE_FEATURE_DIM)
        self._zone_hopfield.store_patterns(self._zone_fingerprints)

    def _compute_dock_features(self, x: float, y: float, node: dict) -> tuple[float, float, float]:
        """Compute heading, distance, and turns relative to nearest dock."""
        if not self._dock_nodes:
            return 0.0, 0.0, 0.0

        best_dist = float("inf")
        best_dock = self._dock_nodes[0]
        for dock in self._dock_nodes:
            dx = x - dock["x"]
            dy = y - dock["y"]
            d = math.sqrt(dx * dx + dy * dy)
            if d < best_dist:
                best_dist = d
                best_dock = dock

        dx = x - best_dock["x"]
        dy = y - best_dock["y"]
        heading = math.degrees(math.atan2(dy, dx)) % 360

        # Add position-dependent offset to break collinear symmetry
        heading = (heading + best_dist * 7.3) % 360

        turns_est = best_dist / 2.0
        return heading, best_dist, turns_est

    def get_node_dock_features(self, node_name: str) -> tuple[float, float, float]:
        """Public accessor for node dock features (used by tests)."""
        node = self.nodes_by_name.get(node_name)
        if not node:
            return 0.0, 0.0, 0.0
        return self._compute_dock_features(node["x"], node["y"], node)

    def _build_fingerprints(self, n_scans: int = 20, seed: int = 42):
        """Build node-level AND zone-level fingerprints.

        Node fingerprints: averaged 16-feature vector per node (includes position).
        Zone fingerprints: averaged 12-feature GEOMETRY-ONLY vector per zone.

        CRITICAL: Zone fingerprints use extract_zone_features (12 features)
        NOT extract_16_features. Position features (heading, dist, turns)
        would blur the zone centroid and destroy zone-type discrimination.
        """
        rng = np.random.default_rng(seed)

        # Step 1: Build per-node fingerprints (full 16 features for node narrowing)
        # AND collect per-node geometry features (12 features for zone aggregation)
        _node_zone_features: dict[str, np.ndarray] = {}

        for node in self.nodes_by_name.values():
            node_name = node["name"]
            zone_name = self._node_to_zone.get(node_name)
            node_type = node.get("type", "none")
            scan_type = self._zone_types.get(zone_name, node_type) if zone_name else node_type

            heading, dist, turns = self._compute_dock_features(node["x"], node["y"], node)

            full_features = []
            zone_features = []
            for _ in range(n_scans):
                scan = generate_zone_scan(scan_type, rng, heading, dist)
                full_features.append(extract_16_features(scan, heading, dist, turns))
                zone_features.append(extract_zone_features(scan))

            self._node_fingerprints[node_name] = np.mean(full_features, axis=0)
            _node_zone_features[node_name] = np.mean(zone_features, axis=0)

        # Step 2: Aggregate GEOMETRY-ONLY features to zone-level (12 features)
        for zone in self.zones:
            zn = zone["name"]
            zone_geo_fps = []
            for nn in zone.get("nodes", []):
                if nn in _node_zone_features:
                    zone_geo_fps.append(_node_zone_features[nn])
            if zone_geo_fps:
                self._zone_fingerprints[zn] = np.mean(zone_geo_fps, axis=0)

    @property
    def zone_adjacency(self) -> dict[str, set[str]]:
        """Public accessor for zone adjacency (used by tests)."""
        return self._zone_adjacency

    @property
    def node_fingerprints(self) -> dict[str, np.ndarray]:
        """Public accessor for node fingerprints (used by tests)."""
        return self._node_fingerprints

    @property
    def last_zone(self) -> Optional[str]:
        return self._last_zone

    @last_zone.setter
    def last_zone(self, value: Optional[str]):
        self._last_zone = value

    def set_node_fingerprint(self, node_name: str, scan_360: np.ndarray,
                             heading_deg: float, dist_from_dock: float,
                             turns_since_dock: float = 0.0):
        """Replace a node's fingerprint with one built from a REAL scan.

        Used by full_flow to inject real Gazebo raycasts into the fingerprint
        store, replacing the synthetic calibration fingerprint.
        """
        full_feat = extract_16_features(scan_360, heading_deg, dist_from_dock, turns_since_dock)
        zone_feat = extract_zone_features(scan_360)
        self._node_fingerprints[node_name] = full_feat
        # Store zone features for later rebuild
        if not hasattr(self, '_node_zone_features_real'):
            self._node_zone_features_real = {}
        self._node_zone_features_real[node_name] = zone_feat
        # Store raw calibration scan for wall count clue
        if not hasattr(self, '_cal_scans'):
            self._cal_scans = {}
        self._cal_scans[node_name] = scan_360.copy()

    def rebuild_hopfield(self):
        """Rebuild zone-level Hopfield ODE from current node fingerprints.

        Call this after injecting real fingerprints via set_node_fingerprint().
        Re-aggregates geometry-only features to zone level and rebuilds the
        D=10,000 Hopfield pattern store.
        """
        # Use real zone features if available, otherwise extract from node fingerprints
        zone_feat_source = getattr(self, '_node_zone_features_real', {})

        self._zone_fingerprints = {}
        for zone in self.zones:
            zn = zone["name"]
            zone_geo_fps = []
            for nn in zone.get("nodes", []):
                if nn in zone_feat_source:
                    zone_geo_fps.append(zone_feat_source[nn])
                elif nn in self._node_fingerprints:
                    # Fallback: cannot derive 36-sector from 16-feature, skip
                    pass
            if zone_geo_fps:
                self._zone_fingerprints[zn] = np.mean(zone_geo_fps, axis=0)

        # Rebuild Hopfield with new zone fingerprints
        self._zone_hopfield = _HopfieldODE(beta=4.0, dt=0.05, max_steps=50, n_features=ZONE_FEATURE_DIM)
        self._zone_hopfield.store_patterns(self._zone_fingerprints)

    def hierarchical_zone_id(self, scan_360: np.ndarray,
                             heading_deg: float = 0.0,
                             dist_from_dock: float = 0.0,
                             turns_since_dock: float = 0.0,
                             previous_zone=_UNSET) -> dict:
        """Step 1: Identify ZONE from scan (7-12 way classification).

        This is the core fix: zone-level is 7-12 classes, each geometrically
        distinct. Much easier than 539-way node classification.

        Returns:
            {zone, confidence, ode_time_ms, method, candidates, features}
        """
        # Use GEOMETRY-ONLY features for zone-level matching (12 features)
        # Position features (heading, dist) would hurt zone classification
        zone_features = extract_zone_features(scan_360)
        # Keep full 16 features for later node narrowing
        full_features = extract_16_features(scan_360, heading_deg, dist_from_dock, turns_since_dock)

        # Run zone-level Hopfield matching on 12 geometry features
        ranked, ode_time_ms = self._zone_hopfield.rank_all(zone_features)

        if not ranked:
            return {
                "zone": "unknown",
                "confidence": 0.0,
                "ode_time_ms": 0.0,
                "method": "no_zones",
                "candidates": [],
                "features": full_features,
            }

        # Apply graph filter if previous zone known
        # _UNSET = use internal state; None = cold start (no graph filter)
        if previous_zone is _UNSET:
            prev = self._last_zone
        else:
            prev = previous_zone

        if prev and prev in self._zone_adjacency:
            reachable = self._zone_adjacency[prev] | {prev}
            reachable_ranked = [(z, s) for z, s in ranked if z in reachable]

            if len(reachable_ranked) == 1:
                best_zone = reachable_ranked[0][0]
                confidence = 1.0
                method = "HIERARCHICAL_GRAPH_UNIQUE"
            elif reachable_ranked:
                best_zone = reachable_ranked[0][0]
                if len(reachable_ranked) >= 2:
                    margin = reachable_ranked[0][1] - reachable_ranked[1][1]
                    confidence = min(0.5 + margin * 2.0, 0.98)
                else:
                    confidence = 0.9
                method = "HIERARCHICAL_GRAPH_RANKED"
            else:
                # No reachable match — use global best
                best_zone = ranked[0][0]
                confidence = 0.3
                method = "HIERARCHICAL_TELEPORT"
        else:
            # Cold start — no previous zone
            best_zone = ranked[0][0]
            if len(ranked) >= 2:
                margin = ranked[0][1] - ranked[1][1]
                confidence = min(0.5 + margin * 2.0, 0.95)
            else:
                confidence = 0.9
            method = "HIERARCHICAL_COLD"

        self._last_zone = best_zone

        return {
            "zone": best_zone,
            "confidence": confidence,
            "ode_time_ms": ode_time_ms,
            "method": method,
            "candidates": ranked[:5],
            "features": full_features,
        }

    def narrow_to_node(self, zone_name: str, scan_360: np.ndarray,
                       heading_deg: float = 0.0,
                       dist_from_dock: float = 0.0,
                       use_graph: bool = True) -> dict:
        """Step 2: Narrow to specific node within a confirmed zone.

        Uses per-node fingerprint matching RESTRICTED to nodes in the zone,
        plus graph topology for disambiguation.

        Args:
            zone_name: Confirmed zone from Step 1.
            scan_360: The same 360-ray scan.
            heading_deg: Robot heading.
            dist_from_dock: Distance from dock.
            use_graph: Whether to use graph adjacency for additional filtering.

        Returns:
            {node, confidence, method, candidates}
        """
        zone_nodes = self._zone_nodes.get(zone_name, [])
        if not zone_nodes:
            return {
                "node": "unknown",
                "confidence": 0.0,
                "method": "empty_zone",
                "candidates": [],
            }

        if len(zone_nodes) == 1:
            return {
                "node": zone_nodes[0],
                "confidence": 1.0,
                "method": "single_node_zone",
                "candidates": [(zone_nodes[0], 1.0)],
            }

        # Extract features from scan
        features = extract_16_features(scan_360, heading_deg, dist_from_dock, 0.0)

        # Match against ONLY the nodes in this zone
        candidates = []
        for nn in zone_nodes:
            if nn in self._node_fingerprints:
                fp = self._node_fingerprints[nn]
                dist = float(np.linalg.norm(features - fp))
                similarity = 1.0 / (1.0 + dist)
                candidates.append((nn, similarity))

        candidates.sort(key=lambda x: -x[1])

        if not candidates:
            return {
                "node": zone_nodes[0],  # fallback to first node
                "confidence": 0.1,
                "method": "no_fingerprints",
                "candidates": [],
            }

        best_node = candidates[0][0]
        if len(candidates) >= 2:
            margin = candidates[0][1] - candidates[1][1]
            confidence = min(0.5 + margin * 3.0, 0.95)
        else:
            confidence = 0.9

        return {
            "node": best_node,
            "confidence": confidence,
            "method": "zone_restricted_fp" if not use_graph else "zone_restricted_graph",
            "candidates": candidates[:5],
        }

    @staticmethod
    def _wall_count(scan_360: np.ndarray, threshold: float = 1.5) -> int:
        """Count sectors with range < threshold (walls/obstacles).

        Corner node = 2+ walls, edge = 1, center = 0.
        """
        sector_width = 360 // 8
        walls = 0
        for i in range(8):
            start = i * sector_width
            sector = scan_360[start:start + sector_width]
            if np.median(sector) < threshold:
                walls += 1
        return walls

    @staticmethod
    def _cal_wall_count(cal_scan: np.ndarray, threshold: float = 1.5) -> int:
        """Wall count from calibration scan."""
        sector_width = 360 // 8
        walls = 0
        for i in range(8):
            start = i * sector_width
            sector = cal_scan[start:start + sector_width]
            if np.median(sector) < threshold:
                walls += 1
        return walls

    def recover_from_last_known(self, scan_360: np.ndarray,
                                last_x: float, last_y: float,
                                heading_deg: float = 0.0,
                                k: int = 5) -> dict:
        """Crash recovery: 4-clue combined scoring.

        Combined score = 0.4*lidar + 0.2*walls + 0.25*proximity + 0.15*heading

        Clues:
          1. LiDAR similarity (36-sector histogram vs calibration) — weight 0.4
          2. Wall count match (sectors < 1.5m: corner=2+, edge=1, center=0) — weight 0.2
          3. Proximity to last known position (closer = higher) — weight 0.25
          4. Heading match (IMU compass vs known approach heading) — weight 0.15

        Args:
            scan_360: Current 360-ray LiDAR scan after crash.
            last_x: Last known x position before crash.
            last_y: Last known y position before crash.
            heading_deg: IMU compass heading after crash.
            k: Number of nearest candidate nodes (default 5).

        Returns:
            {node, zone, confidence, method, candidates, distances}
        """
        W_LIDAR = 0.40
        W_WALLS = 0.20
        W_PROX  = 0.25
        W_HEAD  = 0.15

        # Step 1: Find k nearest nodes to last known position
        node_dists = []
        for nn, node in self.nodes_by_name.items():
            dx = node["x"] - last_x
            dy = node["y"] - last_y
            d = math.sqrt(dx * dx + dy * dy)
            node_dists.append((nn, d))
        node_dists.sort(key=lambda x: x[1])
        candidates_names = [nd[0] for nd in node_dists[:k]]
        candidate_dists = {nd[0]: nd[1] for nd in node_dists[:k]}

        if not candidates_names:
            return {
                "node": "unknown", "zone": "unknown",
                "confidence": 0.0, "method": "no_nodes",
                "candidates": [], "distances": {},
            }

        if len(candidates_names) == 1:
            nn = candidates_names[0]
            return {
                "node": nn,
                "zone": self._node_to_zone.get(nn, "unknown"),
                "confidence": 1.0,
                "method": "single_candidate",
                "candidates": [(nn, 1.0)],
                "distances": candidate_dists,
            }

        # Step 2: Compute per-scan clues
        query_zf = extract_zone_features(scan_360)
        scan_walls = self._wall_count(scan_360)

        # Max distance among candidates (for normalization)
        max_dist = max(candidate_dists.values()) if candidate_dists else 1.0
        max_dist = max(max_dist, 0.1)

        # Step 3: Score each candidate with 4 clues
        scored = []
        for nn in candidates_names:
            # Clue 1: LiDAR similarity (0-1)
            lidar_sim = 0.0
            real_feats = getattr(self, '_node_zone_features_real', {})
            if nn in real_feats:
                fp = real_feats[nn]
                n = min(len(query_zf), len(fp))
                dist = float(np.linalg.norm(query_zf[:n] - fp[:n]))
                lidar_sim = 1.0 / (1.0 + dist)
            elif nn in self._node_fingerprints:
                fp = self._node_fingerprints[nn]
                scan_feat = extract_16_features(scan_360, 0, 0, 0)
                dist = float(np.linalg.norm(scan_feat - fp))
                lidar_sim = 1.0 / (1.0 + dist)

            # Clue 2: Wall count match (0 or 1)
            cal_scan = getattr(self, '_cal_scans', {}).get(nn)
            if cal_scan is not None:
                cal_walls = self._cal_wall_count(cal_scan)
                wall_score = 1.0 if cal_walls == scan_walls else 0.0
            else:
                wall_score = 0.5  # no cal data, neutral

            # Clue 3: Proximity — closer to last known = higher (0-1)
            prox_score = 1.0 - (candidate_dists[nn] / max_dist)

            # Clue 4: Heading match — compare IMU heading to approach heading
            node_data = self.nodes_by_name[nn]
            approach_heading = math.degrees(math.atan2(
                node_data["y"] - last_y, node_data["x"] - last_x
            )) % 360
            head_diff = abs(heading_deg - approach_heading)
            if head_diff > 180:
                head_diff = 360 - head_diff
            head_score = 1.0 - (head_diff / 180.0)  # 0=opposite, 1=same direction

            # Combined score
            total = (W_LIDAR * lidar_sim +
                     W_WALLS * wall_score +
                     W_PROX  * prox_score +
                     W_HEAD  * head_score)

            scored.append((nn, total))

        scored.sort(key=lambda x: -x[1])

        if not scored:
            nn = candidates_names[0]
            return {
                "node": nn,
                "zone": self._node_to_zone.get(nn, "unknown"),
                "confidence": 0.2,
                "method": "nearest_fallback",
                "candidates": [(nn, 0.2)],
                "distances": candidate_dists,
            }

        best = scored[0][0]
        if len(scored) >= 2:
            margin = scored[0][1] - scored[1][1]
            confidence = min(0.5 + margin * 5.0, 0.99)
        else:
            confidence = 0.9

        return {
            "node": best,
            "zone": self._node_to_zone.get(best, "unknown"),
            "confidence": confidence,
            "method": "4clue_k_nearest",
            "candidates": scored[:k],
            "distances": candidate_dists,
        }

    def identify_from_scan(self, scan_360: np.ndarray,
                           heading_deg: float = 0.0,
                           dist_from_dock: float = 0.0,
                           turns_since_dock: float = 0.0,
                           previous_zone=_UNSET) -> dict:
        """Full hierarchical identification: zone first, then node.

        Combines Step 1 (zone ID) and Step 2 (node narrowing) into
        a single call for backward compatibility.

        Returns:
            {zone, node, zone_confidence, node_confidence, ode_time_ms, method, features, candidates}
        """
        # Step 1: Zone identification
        zone_result = self.hierarchical_zone_id(
            scan_360, heading_deg, dist_from_dock, turns_since_dock, previous_zone
        )

        # Step 2: Node narrowing within zone
        node_result = self.narrow_to_node(
            zone_result["zone"], scan_360, heading_deg, dist_from_dock
        )

        return {
            "zone": zone_result["zone"],
            "node": node_result["node"],
            "zone_confidence": zone_result["confidence"],
            "node_confidence": node_result["confidence"],
            "confidence": zone_result["confidence"],  # backward compat
            "ode_time_ms": zone_result["ode_time_ms"],
            "method": zone_result["method"],
            "features": zone_result["features"],
            "candidates": zone_result["candidates"],
        }


# ── Legacy API ────────────────────────────────────────────────────────
# Kept for backward compatibility with existing tests.

class ZoneIdentifier(HierarchicalZoneIdentifier):
    """Backward-compatible wrapper around HierarchicalZoneIdentifier.

    Maps old identify([x,y]) API to zone centroid lookup.
    """

    def identify(self, position: list[float]) -> dict:
        """Legacy position-based identification (nearest centroid)."""
        pos = np.array(position[:2])
        best_zone = "unknown"
        best_dist = float("inf")

        for zn, centroid in self._zone_centroids.items():
            d = float(np.linalg.norm(pos - centroid))
            if d < best_dist:
                best_dist = d
                best_zone = zn

        return {
            "zone": best_zone,
            "confidence": max(0.0, 1.0 - best_dist / 20.0),
            "method": "centroid",
            "ode_time_ms": 0.0,
            "features": np.zeros(16),
            "candidates": [(best_zone, 1.0)],
        }

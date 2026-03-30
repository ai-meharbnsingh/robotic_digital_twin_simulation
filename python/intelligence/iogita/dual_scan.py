"""
DualScanFingerprint — scan-move-scan creates position-specific change signatures.

Strategy C: Single scan fails because corridors look identical. Two scans from
different positions create a CHANGE signature unique to each location.

The delta features (sector change rate, displacement-normalized differences)
are what make identical-looking corridors distinguishable.

ADR-NEW: Dual-scan — two scans minimum for corridor disambiguation.
"""

import numpy as np
from typing import Optional


N_SECTORS = 8       # 8 sectors of 45 degrees each
N_RAYS = 360        # Full 360 LiDAR scan


def _sector_stats(scan_360: np.ndarray, n_sectors: int = N_SECTORS) -> np.ndarray:
    """Compute per-sector statistics from a 360-ray scan.

    For each sector: [median, min, max, variance]
    Returns (n_sectors, 4) array.
    """
    sector_width = N_RAYS // n_sectors
    stats = np.zeros((n_sectors, 4))

    for i in range(n_sectors):
        start = i * sector_width
        end = start + sector_width
        sector = scan_360[start:end]
        stats[i, 0] = np.median(sector)
        stats[i, 1] = np.min(sector)
        stats[i, 2] = np.max(sector)
        stats[i, 3] = np.var(sector)

    return stats


def _histogram_features(scan_360: np.ndarray, bins: int = 8) -> np.ndarray:
    """Compute range histogram (fraction of rays in each bin).

    Bins: [0-1.5, 1.5-3, 3-4.5, 4.5-6, 6-7.5, 7.5-9, 9-10.5, 10.5-12]
    Returns normalized histogram (sums to 1).
    """
    edges = np.linspace(0, 12.0, bins + 1)
    hist, _ = np.histogram(scan_360, bins=edges)
    total = max(hist.sum(), 1)
    return hist.astype(np.float64) / total


def combine_scans(scan1: np.ndarray, scan2: np.ndarray,
                  displacement_m: float, direction_deg: float) -> np.ndarray:
    """Combine two scans into a dual-scan fingerprint.

    The DELTA between scans is position-specific even when individual
    scans look identical (e.g., uniform corridors).

    Feature layout (56 features total):
      [0:8]   scan1 sector medians (normalized by 12m)
      [8:16]  scan1 sector variances (normalized by 12)
      [16:24] scan2 sector medians (normalized by 12m)
      [24:32] scan2 sector variances (normalized by 12)
      [32:40] DELTA sector medians: (scan2 - scan1) sector medians / displacement
      [40:48] DELTA sector variances: abs(scan2 - scan1) variance / displacement
      [48:52] scan1 histogram features (4 key bins: close, mid, far, very_far)
      [52:56] scan2 histogram features (4 key bins)

    Args:
        scan1: First 360-ray scan (before move).
        scan2: Second 360-ray scan (after move).
        displacement_m: Distance moved between scans.
        direction_deg: Direction of movement.

    Returns:
        56-element feature vector (all values approximately normalized).
    """
    stats1 = _sector_stats(scan1)  # (8, 4)
    stats2 = _sector_stats(scan2)  # (8, 4)

    # Normalize medians by max range
    medians1 = stats1[:, 0] / 12.0
    medians2 = stats2[:, 0] / 12.0

    # Normalize variances
    vars1 = stats1[:, 3] / 12.0
    vars2 = stats2[:, 3] / 12.0

    # DELTA features — change per meter of displacement
    # These are what make identical corridors distinguishable
    disp = max(displacement_m, 0.1)  # prevent div by zero
    delta_medians = (medians2 - medians1) / disp
    delta_vars = np.abs(vars2 - vars1) / disp

    # Histogram features (compressed: 8 bins -> 4 key bins)
    hist1 = _histogram_features(scan1, bins=8)
    hist2 = _histogram_features(scan2, bins=8)
    # Compress: close (0-3m), mid (3-6m), far (6-9m), very_far (9-12m)
    hist1_compressed = np.array([
        hist1[0] + hist1[1],  # 0-3m
        hist1[2] + hist1[3],  # 3-6m
        hist1[4] + hist1[5],  # 6-9m
        hist1[6] + hist1[7],  # 9-12m
    ])
    hist2_compressed = np.array([
        hist2[0] + hist2[1],
        hist2[2] + hist2[3],
        hist2[4] + hist2[5],
        hist2[6] + hist2[7],
    ])

    return np.concatenate([
        medians1,           # 0:8
        vars1,              # 8:16
        medians2,           # 16:24
        vars2,              # 24:32
        delta_medians,      # 32:40 — KEY: position-specific change
        delta_vars,         # 40:48 — KEY: texture change rate
        hist1_compressed,   # 48:52
        hist2_compressed,   # 52:56
    ])


class DualScanFingerprint:
    """
    Manages dual-scan fingerprint collection and matching.

    Calibration phase: robot visits all zones, collects scan1+move+scan2
    at known positions. Builds a library of dual-scan fingerprints per zone.

    Recovery phase: robot performs scan-move-scan and matches against library.

    The delta features are what distinguish identical-looking corridors:
    two corridors may produce the same single scan, but the CHANGE after
    a 2m move will differ because the wall/obstacle geometry diverges.
    """

    def __init__(self, n_features: int = 56, seed: int = 42):
        self.n_features = n_features
        self._zone_fingerprints: dict[str, list[np.ndarray]] = {}
        self._zone_centroids: dict[str, np.ndarray] = {}

    def add_fingerprint(self, zone_name: str, fingerprint: np.ndarray):
        """Add a calibration fingerprint for a zone."""
        if zone_name not in self._zone_fingerprints:
            self._zone_fingerprints[zone_name] = []
        self._zone_fingerprints[zone_name].append(fingerprint.copy())

    def build_centroids(self):
        """Build zone-level centroids from collected fingerprints."""
        self._zone_centroids = {}
        for zone_name, fps in self._zone_fingerprints.items():
            if fps:
                self._zone_centroids[zone_name] = np.mean(fps, axis=0)

    def match(self, query: np.ndarray, top_k: int = 3) -> list[tuple[str, float]]:
        """Match a dual-scan fingerprint against zone centroids.

        Uses Euclidean distance (features are normalized, so this is fair).

        Returns:
            List of (zone_name, similarity) sorted by similarity descending.
            Similarity = 1 / (1 + distance).
        """
        if not self._zone_centroids:
            return []

        results = []
        for zone_name, centroid in self._zone_centroids.items():
            # Match dimensions (query might have fewer features)
            n = min(len(query), len(centroid))
            dist = float(np.linalg.norm(query[:n] - centroid[:n]))
            similarity = 1.0 / (1.0 + dist)
            results.append((zone_name, similarity))

        results.sort(key=lambda x: -x[1])
        return results[:top_k]

    def calibrate_from_scans(self, zone_name: str,
                             scan_pairs: list[tuple[np.ndarray, np.ndarray, float, float]]):
        """Calibrate zone from multiple scan pairs.

        Args:
            zone_name: Zone to calibrate.
            scan_pairs: List of (scan1, scan2, displacement_m, direction_deg) tuples.
        """
        for scan1, scan2, disp, direction in scan_pairs:
            fp = combine_scans(scan1, scan2, disp, direction)
            self.add_fingerprint(zone_name, fp)
        self.build_centroids()

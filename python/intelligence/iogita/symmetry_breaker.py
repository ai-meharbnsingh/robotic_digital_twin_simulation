"""
SymmetryBreaker — LiDAR-only disambiguation of identical-looking aisles.

Problem: In a warehouse with 10 identical storage aisles, a single LiDAR scan
from inside any aisle looks nearly the same — same shelf height, same spacing,
same width. Single-scan zone identification can't distinguish Aisle_A from Aisle_E.

Solution WITHOUT camera (5 signals, LiDAR + odometry only):

  Signal 1: END-CAP ASYMMETRY
    Even identical aisles have different geometry at their ends.
    Aisle 1 might face a wall, Aisle 5 faces a corridor.
    Long-range rays (>5m) in the along-aisle direction see these differences.

  Signal 2: WALL DISTANCE GRADIENT
    Each aisle is at a different distance from the warehouse boundary.
    The max-range readings in the cross-aisle direction differ by aisle position.
    Aisle 1 (near wall): left side reads 2m, right side reads 28m.
    Aisle 5 (middle): left side reads 14m, right side reads 16m.

  Signal 3: MULTI-SCAN DISPLACEMENT VECTOR
    Robot moves 1-2m along the aisle and rescans. The DELTA pattern
    (how ranges change) is unique per aisle because adjacent geometry differs.
    Uses DualScanFingerprint's 56-feature delta vector.

  Signal 4: ADJACENT AISLE ECHO
    Cross-aisle rays pass through shelf gaps and bounce off adjacent aisles.
    The return pattern depends on which adjacent aisles exist and their contents.
    Outer aisles have walls; inner aisles have more shelves.

  Signal 5: ODOMETRY DISPLACEMENT PRIOR
    If we know the last confirmed position (from barcode, FMS, or AMCL),
    dead-reckoning odometry gives a coarse estimate of current position.
    This provides a strong Bayesian prior even with 10-20% drift.

Scoring:
  aisle_score = 0.25*endcap + 0.20*wall_dist + 0.20*multi_scan +
                0.15*adjacent + 0.20*odom_prior

  If no odometry available: weights redistribute to LiDAR signals.
"""

import math
import numpy as np
from typing import Optional
from scipy.spatial import KDTree


N_RAYS = 360
ALONG_AISLE_SECTORS = [(0, 30), (330, 360)]      # Forward-facing rays (0±15°)
ALONG_AISLE_REAR = [(150, 210)]                    # Rear-facing rays (180±30°)
CROSS_AISLE_LEFT = [(60, 120)]                     # Left-facing rays (90±30°)
CROSS_AISLE_RIGHT = [(240, 300)]                   # Right-facing rays (270±30°)


def _sector_median(scan: np.ndarray, sectors: list[tuple[int, int]]) -> float:
    """Median range across specified angular sectors."""
    rays = []
    for start, end in sectors:
        rays.extend(scan[start:min(end, len(scan))])
    if not rays:
        return 12.0
    return float(np.median(rays))


def _sector_stats(scan: np.ndarray, sectors: list[tuple[int, int]]) -> dict:
    """Stats across specified angular sectors."""
    rays = []
    for start, end in sectors:
        rays.extend(scan[start:min(end, len(scan))])
    if not rays:
        return {"median": 12.0, "std": 0.0, "min": 12.0, "max": 12.0, "count": 0}
    arr = np.array(rays)
    return {
        "median": float(np.median(arr)),
        "std": float(np.std(arr)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "count": len(arr),
    }


class AisleSignature:
    """Computed LiDAR signature for an aisle position."""

    def __init__(self, aisle_name: str):
        self.aisle_name = aisle_name
        self.endcap_forward: float = 0.0    # Median forward long-range
        self.endcap_rear: float = 0.0       # Median rear long-range
        self.wall_dist_left: float = 0.0    # Cross-aisle left distance
        self.wall_dist_right: float = 0.0   # Cross-aisle right distance
        self.wall_asymmetry: float = 0.0    # |left - right| / max(left, right)
        self.adjacent_echo_left: float = 0.0  # Variance in left cross-aisle rays
        self.adjacent_echo_right: float = 0.0
        self.scan_delta_norm: float = 0.0   # Norm of multi-scan delta (if available)
        self.position_x: float = 0.0        # Calibrated position
        self.position_y: float = 0.0

    def to_feature_vector(self) -> np.ndarray:
        """Convert to numerical feature vector for KDTree matching."""
        return np.array([
            self.endcap_forward / 12.0,
            self.endcap_rear / 12.0,
            self.wall_dist_left / 30.0,     # Normalize by warehouse width
            self.wall_dist_right / 30.0,
            self.wall_asymmetry,
            self.adjacent_echo_left,
            self.adjacent_echo_right,
            self.scan_delta_norm,
        ], dtype=np.float64)


class SymmetryBreaker:
    """
    Disambiguates identical-looking aisles using LiDAR-only signals.

    Calibration: collect scans from each aisle at known positions.
    Recovery: match new scan(s) against calibrated signatures.
    """

    def __init__(self):
        self._aisle_signatures: dict[str, AisleSignature] = {}
        self._aisle_positions: dict[str, tuple[float, float]] = {}
        self._feature_tree: Optional[KDTree] = None
        self._aisle_names: list[str] = []
        self._calibrated = False

    def extract_signature(
        self,
        aisle_name: str,
        scan: np.ndarray,
        position_xy: tuple[float, float] = (0.0, 0.0),
        scan2: Optional[np.ndarray] = None,
        displacement_m: float = 0.0,
    ) -> AisleSignature:
        """Extract aisle signature from LiDAR scan(s).

        Args:
            aisle_name: Name of the aisle.
            scan: Primary 360-ray LiDAR scan.
            position_xy: Known (x, y) position (for calibration).
            scan2: Optional second scan after movement (for delta features).
            displacement_m: Distance moved between scan and scan2.
        """
        scan = self._normalize(scan)
        sig = AisleSignature(aisle_name)
        sig.position_x, sig.position_y = position_xy

        # Signal 1: End-cap asymmetry
        sig.endcap_forward = _sector_median(scan, ALONG_AISLE_SECTORS)
        sig.endcap_rear = _sector_median(scan, ALONG_AISLE_REAR)

        # Signal 2: Wall distance gradient
        left_stats = _sector_stats(scan, CROSS_AISLE_LEFT)
        right_stats = _sector_stats(scan, CROSS_AISLE_RIGHT)
        sig.wall_dist_left = left_stats["median"]
        sig.wall_dist_right = right_stats["median"]
        max_wall = max(sig.wall_dist_left, sig.wall_dist_right, 0.1)
        sig.wall_asymmetry = abs(sig.wall_dist_left - sig.wall_dist_right) / max_wall

        # Signal 4: Adjacent aisle echo (cross-aisle variance)
        sig.adjacent_echo_left = left_stats["std"] / 12.0
        sig.adjacent_echo_right = right_stats["std"] / 12.0

        # Signal 3: Multi-scan delta (if second scan available)
        if scan2 is not None:
            scan2 = self._normalize(scan2)
            delta = scan2 - scan
            disp = max(displacement_m, 0.1)
            sig.scan_delta_norm = float(np.linalg.norm(delta / disp)) / 360.0

        return sig

    def calibrate(self, signatures: list[AisleSignature]):
        """Build KDTree from calibrated aisle signatures."""
        self._aisle_signatures = {}
        self._aisle_positions = {}
        self._aisle_names = []
        features = []

        for sig in signatures:
            self._aisle_signatures[sig.aisle_name] = sig
            self._aisle_positions[sig.aisle_name] = (sig.position_x, sig.position_y)
            features.append(sig.to_feature_vector())
            self._aisle_names.append(sig.aisle_name)

        if features:
            feat_arr = np.array(features)
            self._feature_tree = KDTree(feat_arr)
            self._calibrated = True

            # Detect if LiDAR can discriminate between aisles
            # If max pairwise distance is small, all aisles look identical
            if len(feat_arr) >= 2:
                pairwise_dists = []
                for i in range(len(feat_arr)):
                    for j in range(i + 1, len(feat_arr)):
                        pairwise_dists.append(float(np.linalg.norm(feat_arr[i] - feat_arr[j])))
                self._lidar_discriminative = max(pairwise_dists) > 0.1
            else:
                self._lidar_discriminative = False

    def identify_aisle(
        self,
        scan: np.ndarray,
        last_known_xy: Optional[tuple[float, float]] = None,
        heading_deg: float = 0.0,
        scan2: Optional[np.ndarray] = None,
        displacement_m: float = 0.0,
        odom_drift_m: float = 2.0,
    ) -> dict:
        """Identify which aisle the robot is in using LiDAR-only signals.

        Args:
            scan: Current 360-ray LiDAR scan.
            last_known_xy: Last confirmed (x, y) position (for odometry prior).
            heading_deg: Current heading in degrees.
            scan2: Optional second scan after movement.
            displacement_m: Distance moved between scans.
            odom_drift_m: Expected odometry drift (meters, for prior width).

        Returns:
            Dict with aisle name, confidence, breakdown of signal contributions.
        """
        if not self._calibrated:
            return {"aisle": "unknown", "confidence": 0.0, "method": "not_calibrated"}

        # Extract query signature
        query_sig = self.extract_signature(
            "query", scan,
            scan2=scan2, displacement_m=displacement_m,
        )
        query_vec = query_sig.to_feature_vector()

        # KDTree lookup — get top candidates
        k = min(5, len(self._aisle_names))
        dists, idxs = self._feature_tree.query(query_vec, k=k)

        if np.isscalar(idxs):
            idxs = [idxs]
            dists = [dists]

        # Use calibration-time discriminability flag
        lidar_discriminative = getattr(self, '_lidar_discriminative', True)

        # Score candidates with all 5 signals
        scored = []
        for dist, idx in zip(dists, idxs):
            aisle = self._aisle_names[idx]
            cal_sig = self._aisle_signatures[aisle]

            # LiDAR similarity (inverse distance)
            lidar_sim = 1.0 / (1.0 + dist)

            # Endcap score — how well forward/rear readings match
            endcap_diff = (
                abs(query_sig.endcap_forward - cal_sig.endcap_forward) +
                abs(query_sig.endcap_rear - cal_sig.endcap_rear)
            ) / 24.0
            endcap_score = 1.0 - min(endcap_diff, 1.0)

            # Wall distance score
            wall_diff = (
                abs(query_sig.wall_dist_left - cal_sig.wall_dist_left) +
                abs(query_sig.wall_dist_right - cal_sig.wall_dist_right)
            ) / 60.0
            wall_score = 1.0 - min(wall_diff, 1.0)

            # Adjacent echo score
            echo_diff = (
                abs(query_sig.adjacent_echo_left - cal_sig.adjacent_echo_left) +
                abs(query_sig.adjacent_echo_right - cal_sig.adjacent_echo_right)
            )
            echo_score = 1.0 / (1.0 + echo_diff * 10.0)

            # Multi-scan delta score
            delta_score = 0.5  # neutral if no second scan
            if scan2 is not None:
                delta_diff = abs(query_sig.scan_delta_norm - cal_sig.scan_delta_norm)
                delta_score = 1.0 / (1.0 + delta_diff * 50.0)

            # Odometry prior
            odom_score = 0.5  # neutral if no odometry
            if last_known_xy is not None:
                cal_pos = self._aisle_positions.get(aisle, (0, 0))
                odom_dist = math.sqrt(
                    (last_known_xy[0] - cal_pos[0]) ** 2 +
                    (last_known_xy[1] - cal_pos[1]) ** 2
                )
                # Gaussian prior: closer to last known = more likely
                odom_score = math.exp(-(odom_dist ** 2) / (2.0 * odom_drift_m ** 2))

            # Weighted combination with adaptive weighting
            # Key insight: when all candidates score >0.95 on LiDAR,
            # LiDAR cannot discriminate and should contribute ZERO.
            # Odometry becomes the sole discriminator.

            if last_known_xy is not None:
                if not lidar_discriminative:
                    # All aisles look the same to LiDAR → pure odometry
                    total = odom_score
                else:
                    # LiDAR has real signal — blend with odometry
                    total = (
                        0.20 * endcap_score +
                        0.15 * wall_score +
                        0.15 * delta_score +
                        0.10 * echo_score +
                        0.40 * odom_score
                    )
            else:
                # No odometry — LiDAR only (may be low accuracy)
                total = (
                    0.30 * endcap_score +
                    0.25 * wall_score +
                    0.25 * delta_score +
                    0.20 * echo_score
                )

            scored.append({
                "aisle": aisle,
                "total": round(total, 4),
                "endcap": round(endcap_score, 4),
                "wall_dist": round(wall_score, 4),
                "delta": round(delta_score, 4),
                "echo": round(echo_score, 4),
                "odom": round(odom_score, 4),
            })

        scored.sort(key=lambda x: -x["total"])
        best = scored[0]

        # Confidence from margin between top 2
        confidence = best["total"]
        if len(scored) >= 2:
            margin = best["total"] - scored[1]["total"]
            confidence = min(0.5 + margin * 5.0, 0.99)

        return {
            "aisle": best["aisle"],
            "confidence": round(confidence, 4),
            "method": "symmetry_breaker_lidar_only",
            "signals": best,
            "candidates": scored[:3],
            "has_dual_scan": scan2 is not None,
            "has_odometry": last_known_xy is not None,
        }

    @staticmethod
    def _normalize(scan) -> np.ndarray:
        arr = np.asarray(scan, dtype=np.float64)
        if len(arr) != N_RAYS:
            arr = np.interp(np.linspace(0, len(arr) - 1, N_RAYS), np.arange(len(arr)), arr)
        arr = np.where(np.isfinite(arr), arr, 12.0)
        return np.clip(arr, 0.1, 12.0)


def generate_symmetric_warehouse(
    n_aisles: int = 6,
    aisle_width: float = 2.3,
    aisle_length: float = 15.0,
    shelf_height: float = 1.2,
    warehouse_width: float = 30.0,
) -> dict:
    """Generate a warehouse config with N identical aisles for testing.

    Returns config with nodes, zones, and synthetic scan generator.
    Each aisle has identical internal geometry but different positions.
    """
    nodes = []
    zones = []
    aisle_start_x = -(n_aisles * aisle_width) / 2

    for i in range(n_aisles):
        aisle_name = f"Aisle_{chr(65 + i)}"  # Aisle_A, Aisle_B, ...
        center_x = aisle_start_x + (i + 0.5) * aisle_width
        center_y = 0.0

        node_names = []
        for j in range(3):  # 3 nodes per aisle (start, mid, end)
            y = -aisle_length / 2 + j * (aisle_length / 2)
            name = f"{aisle_name}_N{j}"
            nodes.append({
                "name": name,
                "x": center_x,
                "y": y,
                "type": "shelf",
                "zone": aisle_name,
            })
            node_names.append(name)

        zones.append({
            "name": aisle_name,
            "type": "storage",
            "node_names": node_names,
        })

    # Boundary walls
    left_wall_x = aisle_start_x - 2.0
    right_wall_x = aisle_start_x + n_aisles * aisle_width + 2.0
    front_wall_y = aisle_length / 2 + 2.0
    rear_wall_y = -aisle_length / 2 - 2.0

    return {
        "nodes": nodes,
        "zones": zones,
        "geometry": {
            "aisle_width": aisle_width,
            "aisle_length": aisle_length,
            "shelf_height": shelf_height,
            "warehouse_width": warehouse_width,
            "left_wall_x": left_wall_x,
            "right_wall_x": right_wall_x,
            "front_wall_y": front_wall_y,
            "rear_wall_y": rear_wall_y,
            "n_aisles": n_aisles,
            "aisle_start_x": aisle_start_x,
            "aisle_width_each": aisle_width,
        },
    }


def simulate_aisle_scan(
    aisle_index: int,
    position_along_aisle: float,
    geometry: dict,
    noise_std: float = 0.05,
    rng: np.random.RandomState = None,
) -> np.ndarray:
    """Simulate a 360° LiDAR scan from inside an aisle.

    The key: identical aisles produce NEARLY identical scans internally,
    but cross-aisle and along-aisle long-range readings differ by position.

    Args:
        aisle_index: Which aisle (0 = leftmost).
        position_along_aisle: -1.0 to 1.0 (fraction of aisle length from center).
        geometry: From generate_symmetric_warehouse().
        noise_std: Gaussian noise on range measurements.
        rng: Random state for reproducibility.
    """
    if rng is None:
        rng = np.random.RandomState(42)

    n_aisles = geometry["n_aisles"]
    aisle_width = geometry["aisle_width_each"]
    aisle_length = geometry["aisle_length"]
    aisle_start_x = geometry["aisle_start_x"]
    left_wall = geometry["left_wall_x"]
    right_wall = geometry["right_wall_x"]
    front_wall = geometry["front_wall_y"]
    rear_wall = geometry["rear_wall_y"]

    # Robot position
    robot_x = aisle_start_x + (aisle_index + 0.5) * aisle_width
    robot_y = position_along_aisle * (aisle_length / 2)

    scan = np.full(N_RAYS, 12.0, dtype=np.float64)

    for ray_idx in range(N_RAYS):
        angle_deg = ray_idx  # 0° = forward, 90° = left, 270° = right
        angle_rad = math.radians(angle_deg)
        dx = math.cos(angle_rad)
        dy = math.sin(angle_rad)

        min_range = 12.0

        # Check shelf walls on both sides (identical for all aisles)
        # Left shelf: at robot_x - aisle_width/2
        # Right shelf: at robot_x + aisle_width/2
        half_w = aisle_width / 2.0

        if abs(dx) > 0.001:
            # Left shelf
            t_left = (-half_w) / dx
            if t_left > 0:
                hit_y = robot_y + t_left * dy
                if -aisle_length / 2 <= hit_y <= aisle_length / 2:
                    min_range = min(min_range, t_left)

            # Right shelf
            t_right = half_w / dx
            if t_right > 0:
                hit_y = robot_y + t_right * dy
                if -aisle_length / 2 <= hit_y <= aisle_length / 2:
                    min_range = min(min_range, t_right)

        # Cross-aisle: rays that pass through shelf gaps hit distant walls
        # This is where ASYMMETRY comes from
        if abs(dx) > 0.001:
            # Left warehouse wall
            t_lw = (left_wall - robot_x) / dx
            if t_lw > 0:
                min_range = min(min_range, t_lw)

            # Right warehouse wall
            t_rw = (right_wall - robot_x) / dx
            if t_rw > 0:
                min_range = min(min_range, t_rw)

        if abs(dy) > 0.001:
            # Front wall (end of aisle — ENDCAP ASYMMETRY)
            t_fw = (front_wall - robot_y) / dy
            if t_fw > 0:
                min_range = min(min_range, t_fw)

            # Rear wall
            t_bw = (rear_wall - robot_y) / dy
            if t_bw > 0:
                min_range = min(min_range, t_bw)

        # Adjacent aisle shelves create echo patterns
        for adj in range(n_aisles):
            if adj == aisle_index:
                continue
            adj_x = aisle_start_x + (adj + 0.5) * aisle_width
            # Simplified: adjacent aisle shelves at adj_x ± half_w
            for shelf_side in [-half_w, half_w]:
                shelf_x = adj_x + shelf_side
                if abs(dx) > 0.001:
                    t = (shelf_x - robot_x) / dx
                    if t > 0:
                        hit_y = robot_y + t * dy
                        if -aisle_length / 2 <= hit_y <= aisle_length / 2:
                            min_range = min(min_range, t)

        scan[ray_idx] = min(min_range, 12.0)

    # Add noise
    scan += rng.normal(0, noise_std, N_RAYS)
    return np.clip(scan, 0.1, 12.0)

"""
StateEncoder — encodes fleet state into a high-dimensional feature vector.

Takes a list of robot states and produces a fixed-size vector suitable
for attractor-based analysis and bottleneck prediction.
"""

import numpy as np
from typing import Any


class StateEncoder:
    """
    Encodes fleet state into a high-dimensional vector.

    Feature extraction:
    - Per-robot: position (x, y), velocity, battery, status encoding
    - Fleet-level: mean/std of positions, velocity histogram, status distribution
    """

    # Status to numeric encoding
    STATUS_MAP = {
        "idle": 0, "moving": 1, "charging": 2, "loading": 3,
        "unloading": 4, "error": 5, "offline": 6, "docking": 7,
        "undocking": 8, "waiting": 9,
    }

    def __init__(self, max_robots: int = 50, feature_dim: int = 128):
        """
        Args:
            max_robots: Maximum number of robots to encode.
            feature_dim: Output vector dimension.
        """
        self.max_robots = max_robots
        self.feature_dim = feature_dim

    def encode(self, robots: list[dict[str, Any]]) -> np.ndarray:
        """
        Encode fleet state into a feature vector.

        Args:
            robots: List of robot state dicts from MongoDB.

        Returns:
            numpy array of shape (feature_dim,)
        """
        if not robots:
            return np.zeros(self.feature_dim, dtype=np.float64)

        n = min(len(robots), self.max_robots)
        raw_features = []

        # Per-robot features
        positions_x = []
        positions_y = []
        velocities = []
        batteries = []
        status_counts = np.zeros(10, dtype=np.float64)

        for robot in robots[:n]:
            pose = robot.get("pose", {})
            vel = robot.get("velocity", {})
            bat = robot.get("battery", {})
            status = robot.get("status", "idle")

            px = pose.get("x", 0.0)
            py = pose.get("y", 0.0)
            vl = vel.get("linear", 0.0)
            bp = bat.get("charge_pct", 100.0)

            positions_x.append(px)
            positions_y.append(py)
            velocities.append(vl)
            batteries.append(bp)

            idx = self.STATUS_MAP.get(status, 0)
            status_counts[idx] += 1

        # Fleet-level aggregates
        px_arr = np.array(positions_x)
        py_arr = np.array(positions_y)
        vel_arr = np.array(velocities)
        bat_arr = np.array(batteries)

        aggregates = np.array([
            n,                          # fleet size
            np.mean(px_arr),            # mean x
            np.std(px_arr),             # std x
            np.mean(py_arr),            # mean y
            np.std(py_arr),             # std y
            np.mean(vel_arr),           # mean velocity
            np.std(vel_arr),            # std velocity
            np.max(vel_arr) if len(vel_arr) > 0 else 0,
            np.mean(bat_arr),           # mean battery
            np.min(bat_arr) if len(bat_arr) > 0 else 0,
            np.std(bat_arr),            # std battery
        ], dtype=np.float64)

        # Combine: aggregates (11) + status_counts (10) + per-robot features
        combined = np.concatenate([aggregates, status_counts])

        # Add per-robot position features (up to fill feature_dim)
        for i in range(min(n, (self.feature_dim - len(combined)) // 4)):
            combined = np.append(combined, [
                positions_x[i], positions_y[i], velocities[i], batteries[i]
            ])

        # Pad or truncate to feature_dim
        if len(combined) < self.feature_dim:
            combined = np.pad(combined, (0, self.feature_dim - len(combined)))
        else:
            combined = combined[:self.feature_dim]

        return combined.astype(np.float64)

    def encode_timed(self, robots: list[dict[str, Any]]) -> tuple[np.ndarray, float]:
        """Encode and return (vector, elapsed_ms)."""
        import time
        start = time.perf_counter()
        vec = self.encode(robots)
        elapsed = (time.perf_counter() - start) * 1000
        return vec, elapsed

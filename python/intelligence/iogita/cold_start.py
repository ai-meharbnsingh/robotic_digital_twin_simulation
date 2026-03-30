"""
ColdStartRecovery v4 — boot_recovery with dual-scan flow.

Recovery sequence:
  Phase 1: Safe 360 scan (zero risk)
  Phase 2: Hierarchical zone ID from single scan
  Phase 3: Dual scan if confidence < 85% (with safety checks)
  Phase 4: Graph-assisted fallback if still uncertain
  Phase 5: AMCL fallback if all else fails

Safety rules enforced at every phase transition.

ADR-NEW: Dual-scan — two scans minimum for corridor disambiguation.
ADR-NEW: Honest testing — calibration != evaluation data, always.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Protocol

import numpy as np

from .safety_checker import SafetyChecker, ClearanceResult, MoveCommand
from .dual_scan import DualScanFingerprint, combine_scans
from .zone_identifier import HierarchicalZoneIdentifier, extract_16_features


@dataclass
class RecoveryResult:
    """Result of a cold start recovery attempt."""
    zone: str
    node: str
    zone_confidence: float
    node_confidence: float
    method: str
    elapsed_s: float
    safety_violations: list[str] = field(default_factory=list)
    phases_executed: list[str] = field(default_factory=list)
    dual_scan_used: bool = False
    amcl_fallback: bool = False


class RobotInterface(Protocol):
    """Protocol for robot hardware interaction during recovery."""

    def get_lidar_scan(self) -> np.ndarray:
        """Get current 360-ray LiDAR scan."""
        ...

    def rotate_360(self) -> None:
        """Rotate in place to get a full scan (if LiDAR is < 360 deg)."""
        ...

    def move(self, direction_deg: float, distance_m: float, speed_mps: float) -> bool:
        """Move robot in direction. Returns False if obstacle detected (S3)."""
        ...

    def get_heading(self) -> float:
        """Get current heading in degrees."""
        ...

    def get_dist_from_dock(self) -> float:
        """Get estimated distance from nearest dock."""
        ...

    def start_amcl(self) -> dict:
        """Start AMCL localization. Returns {zone, node, confidence}."""
        ...


class SimulatedRobot:
    """Simulated robot for testing — uses synthetic scans at given position."""

    def __init__(self, x: float, y: float, zone_type: str,
                 rng: np.random.Generator, heading: float = 0.0,
                 dist_from_dock: float = 5.0):
        self.x = x
        self.y = y
        self.zone_type = zone_type
        self.rng = rng
        self._heading = heading
        self._dist_from_dock = dist_from_dock
        self._moved = False
        self._move_dx = 0.0
        self._move_dy = 0.0

    def get_lidar_scan(self) -> np.ndarray:
        from .zone_identifier import generate_zone_scan
        # After move, position shifts slightly — different noise seed
        heading = self._heading
        if self._moved:
            heading = (heading + 15) % 360  # slight heading change from move
        return generate_zone_scan(self.zone_type, self.rng, heading, self._dist_from_dock)

    def rotate_360(self) -> None:
        pass  # simulated 360 LiDAR doesn't need rotation

    def move(self, direction_deg: float, distance_m: float, speed_mps: float) -> bool:
        rad = np.radians(direction_deg)
        self._move_dx = distance_m * np.cos(rad)
        self._move_dy = distance_m * np.sin(rad)
        self.x += self._move_dx
        self.y += self._move_dy
        self._moved = True
        return True  # no obstacles in simulation

    def get_heading(self) -> float:
        return self._heading

    def get_dist_from_dock(self) -> float:
        return self._dist_from_dock

    def start_amcl(self) -> dict:
        return {"zone": "unknown", "node": "unknown", "confidence": 0.5}


def boot_recovery(robot: RobotInterface,
                  zone_id: HierarchicalZoneIdentifier,
                  safety: Optional[SafetyChecker] = None,
                  dual_scan_lib: Optional[DualScanFingerprint] = None) -> RecoveryResult:
    """
    Main cold start recovery sequence.

    Phase 1: Safe 360 scan (zero risk)
    Phase 2: Hierarchical zone ID from single scan
    Phase 3: Dual scan if confidence < 85% (with safety)
    Phase 4: Graph-assisted fallback if still uncertain
    Phase 5: AMCL fallback if all else fails

    Args:
        robot: Robot interface (real or simulated).
        zone_id: HierarchicalZoneIdentifier with calibrated fingerprints.
        safety: SafetyChecker instance (created if None).
        dual_scan_lib: DualScanFingerprint library (optional).

    Returns:
        RecoveryResult with zone, node, confidence, method, timing.
    """
    if safety is None:
        safety = SafetyChecker()

    t_start = time.perf_counter()
    phases: list[str] = []
    violations: list[str] = []

    # ── Phase 1: Safe 360 scan (zero risk) ────────────────────────
    phases.append("phase1_scan")
    robot.rotate_360()
    scan1 = robot.get_lidar_scan()
    heading = robot.get_heading()
    dist_dock = robot.get_dist_from_dock()

    # ── Phase 2: Hierarchical zone ID from single scan ────────────
    phases.append("phase2_zone_id")
    zone_result = zone_id.hierarchical_zone_id(
        scan1, heading, dist_dock
    )

    # S4: If high confidence, skip dual scan
    if safety.should_skip_move(zone_result["confidence"]):
        node_result = zone_id.narrow_to_node(
            zone_result["zone"], scan1, heading, dist_dock
        )
        elapsed = time.perf_counter() - t_start
        return RecoveryResult(
            zone=zone_result["zone"],
            node=node_result["node"],
            zone_confidence=zone_result["confidence"],
            node_confidence=node_result["confidence"],
            method="single_scan_high_confidence",
            elapsed_s=elapsed,
            phases_executed=phases,
            safety_violations=violations,
        )

    # ── Phase 3: Dual scan (with safety) ──────────────────────────
    dual_scan_used = False
    if zone_result["confidence"] < 0.85:
        phases.append("phase3_dual_scan")
        safety.reset_move_state()
        clearance = safety.check_clearance(scan1)

        if clearance.is_safe_to_move:
            move_cmd = safety.create_safe_move(clearance, desired_distance=2.0)

            if move_cmd is not None:
                # S2: crawl speed enforced by SafetyChecker
                success = robot.move(
                    move_cmd.direction_deg,
                    move_cmd.distance_m,
                    move_cmd.speed_mps,
                )

                if success and not safety.is_move_aborted():
                    # S3: move succeeded without obstacle
                    scan2 = robot.get_lidar_scan()
                    dual_scan_used = True

                    # Try dual-scan fingerprint matching
                    if dual_scan_lib is not None:
                        dual_fp = combine_scans(
                            scan1, scan2, move_cmd.distance_m, move_cmd.direction_deg
                        )
                        dual_matches = dual_scan_lib.match(dual_fp, top_k=3)
                        if dual_matches and dual_matches[0][1] > 0.6:
                            zone_result_dual = {
                                "zone": dual_matches[0][0],
                                "confidence": dual_matches[0][1],
                            }
                            if zone_result_dual["confidence"] > zone_result["confidence"]:
                                zone_result = {
                                    **zone_result,
                                    "zone": zone_result_dual["zone"],
                                    "confidence": zone_result_dual["confidence"],
                                    "method": "DUAL_SCAN_MATCH",
                                }

                    # Also re-run hierarchical zone ID on scan2
                    zone_result2 = zone_id.hierarchical_zone_id(
                        scan2, heading, dist_dock
                    )

                    # Use best of scan1 and scan2 results
                    if zone_result2["confidence"] > zone_result["confidence"]:
                        zone_result = zone_result2
                        zone_result["method"] = "DUAL_SCAN_RESCAN"

                else:
                    # S3: obstacle detected during move — use single scan
                    violations.append("S3: Obstacle during move, using single scan")
            else:
                violations.append("S1: Insufficient clearance for safe move")
        else:
            violations.extend(clearance.violations)

    # ── Phase 4: Graph-assisted fallback ──────────────────────────
    if zone_result["confidence"] > 0.50:
        phases.append("phase4_node_narrow")
        node_result = zone_id.narrow_to_node(
            zone_result["zone"], scan1, heading, dist_dock, use_graph=True
        )

        # S7: check if confidence sufficient for nav goal
        if safety.can_publish_nav_goal(zone_result["confidence"]):
            elapsed = time.perf_counter() - t_start
            return RecoveryResult(
                zone=zone_result["zone"],
                node=node_result["node"],
                zone_confidence=zone_result["confidence"],
                node_confidence=node_result["confidence"],
                method=zone_result.get("method", "graph_assisted"),
                elapsed_s=elapsed,
                phases_executed=phases,
                safety_violations=violations,
                dual_scan_used=dual_scan_used,
            )

    # ── Phase 5: AMCL fallback ────────────────────────────────────
    phases.append("phase5_amcl_fallback")
    amcl_result = robot.start_amcl()

    elapsed = time.perf_counter() - t_start
    return RecoveryResult(
        zone=amcl_result.get("zone", "unknown"),
        node=amcl_result.get("node", "unknown"),
        zone_confidence=amcl_result.get("confidence", 0.5),
        node_confidence=amcl_result.get("confidence", 0.5),
        method="amcl_fallback",
        elapsed_s=elapsed,
        phases_executed=phases,
        safety_violations=violations,
        dual_scan_used=dual_scan_used,
        amcl_fallback=True,
    )


# ── State persistence (kept from v3) ─────────────────────────────────

class ColdStartStateManager:
    """Saves/loads robot state snapshots for recovery context."""

    def __init__(self, state_dir: Optional[Path] = None):
        self.state_dir = state_dir
        self._cache: dict[str, dict] = {}
        if state_dir is not None:
            state_dir.mkdir(parents=True, exist_ok=True)

    def save_state(self, robot_id: str, state: dict[str, Any]) -> bool:
        snapshot = {
            "robot_id": robot_id,
            "state": state,
            "saved_at": time.time(),
        }
        self._cache[robot_id] = snapshot

        if self.state_dir is not None:
            path = self.state_dir / f"{robot_id}.json"
            try:
                with open(path, "w") as f:
                    json.dump(snapshot, f, default=str)
                return True
            except Exception:
                return False
        return True

    def load_state(self, robot_id: str) -> Optional[dict[str, Any]]:
        if robot_id in self._cache:
            return self._cache[robot_id]

        if self.state_dir is not None:
            path = self.state_dir / f"{robot_id}.json"
            if path.exists():
                try:
                    with open(path, "r") as f:
                        snapshot = json.load(f)
                    self._cache[robot_id] = snapshot
                    return snapshot
                except Exception:
                    return None
        return None

    def generate_recovery_hints(self, robot_id: str,
                                current_state: dict[str, Any]) -> dict[str, Any]:
        start = time.perf_counter()
        last = self.load_state(robot_id)

        hints: dict[str, Any] = {
            "robot_id": robot_id,
            "has_prior_state": last is not None,
            "steps": [],
        }

        if last is not None:
            last_state = last.get("state", {})
            age_s = time.time() - last.get("saved_at", 0)
            hints["state_age_s"] = round(age_s, 1)

            pose = last_state.get("pose", {})
            if pose:
                hints["steps"].append({
                    "action": "restore_position",
                    "data": pose,
                })

            node = last_state.get("current_node", "")
            if node:
                hints["steps"].append({
                    "action": "localize_to_node",
                    "data": {"node": node},
                })

            battery = last_state.get("battery", {})
            if battery.get("charge_pct", 100) < 20:
                hints["steps"].append({
                    "action": "charge_first",
                    "data": battery,
                })

            task_id = last_state.get("current_task_id")
            if task_id:
                hints["steps"].append({
                    "action": "resume_task",
                    "data": {"task_id": task_id},
                })
        else:
            hints["steps"].append({"action": "full_init", "data": {}})
            hints["steps"].append({"action": "localize", "data": {}})

        hints["recovery_time_ms"] = round((time.perf_counter() - start) * 1000, 2)
        return hints

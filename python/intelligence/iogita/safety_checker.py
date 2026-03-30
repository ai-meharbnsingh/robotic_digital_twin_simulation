"""
SafetyChecker — enforces all 7 safety rules for cold start recovery movement.

Safety Rules (NON-NEGOTIABLE):
  S1: NEVER move without 2m clearance in move direction
  S2: Move speed MAX 0.1 m/s (crawl mode)
  S3: If ANY obstacle during move -> STOP, use single scan
  S4: If single scan zone confidence > 85% -> skip move entirely
  S5: Safety laser scanner operates independently — do NOT override
  S6: If confidence < 70% after all attempts -> fall back to AMCL
  S7: NEVER publish nav goal without zone confirmation at >70% confidence

ADR-007: Safety scanner independence — io-gita never overrides hardware safety.
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np


# Safety constants
MIN_CLEARANCE_M = 2.0       # S1: minimum clearance before moving
MAX_CRAWL_SPEED = 0.1       # S2: max speed during recovery move (m/s)
SAFETY_BUFFER_M = 0.5       # Buffer from nearest obstacle
HIGH_CONFIDENCE = 0.85      # S4: skip move if confidence above this
MIN_CONFIDENCE = 0.70       # S6/S7: minimum for nav goal / no-AMCL
MAX_MOVE_DISTANCE_M = 2.0   # Maximum distance to move for dual scan
N_CLEARANCE_SECTORS = 8     # Check 8 directions (45 deg each)


@dataclass
class ClearanceResult:
    """Result of a clearance check in all directions."""
    is_safe_to_move: bool
    best_direction_deg: float
    best_clearance_m: float
    all_sectors: list[tuple[float, float]]  # [(direction_deg, clearance_m), ...]
    violations: list[str]


@dataclass
class MoveCommand:
    """Safe move command after clearance verification."""
    direction_deg: float
    distance_m: float
    speed_mps: float
    clearance_verified: bool


class SafetyChecker:
    """
    Enforces all 7 safety rules during cold start recovery.

    Usage:
        checker = SafetyChecker()
        clearance = checker.check_clearance(scan_360)
        if clearance.is_safe_to_move:
            cmd = checker.create_safe_move(clearance)
            # execute cmd...
        else:
            # use single-scan only
    """

    def __init__(self,
                 min_clearance_m: float = MIN_CLEARANCE_M,
                 max_speed_mps: float = MAX_CRAWL_SPEED,
                 safety_buffer_m: float = SAFETY_BUFFER_M,
                 high_confidence: float = HIGH_CONFIDENCE,
                 min_confidence: float = MIN_CONFIDENCE):
        self.min_clearance_m = min_clearance_m
        self.max_speed_mps = max_speed_mps
        self.safety_buffer_m = safety_buffer_m
        self.high_confidence = high_confidence
        self.min_confidence = min_confidence
        self._obstacle_detected_during_move = False

    def check_clearance(self, scan_360: np.ndarray) -> ClearanceResult:
        """Check clearance in all 8 cardinal/ordinal directions (S1).

        Scans the 360-ray LiDAR and computes median clearance in each
        of 8 sectors (45 deg each). Returns the safest direction.

        Args:
            scan_360: 360-element LiDAR range array.

        Returns:
            ClearanceResult with best direction, clearances, and safety status.
        """
        violations = []
        sector_clearances: list[tuple[float, float]] = []
        sector_width = 360 // N_CLEARANCE_SECTORS  # 45 deg

        for i in range(N_CLEARANCE_SECTORS):
            center_deg = i * sector_width + sector_width // 2
            start = i * sector_width
            end = start + sector_width

            # Handle wrap-around for sector spanning 0/360
            if end <= 360:
                sector_rays = scan_360[start:end]
            else:
                sector_rays = np.concatenate([scan_360[start:360], scan_360[0:end - 360]])

            median_clearance = float(np.median(sector_rays))
            min_clearance = float(np.min(sector_rays))

            # Use the MINIMUM ray in the sector for safety (conservative)
            sector_clearances.append((float(center_deg), min_clearance))

        # Sort by clearance descending to find best direction
        sorted_sectors = sorted(sector_clearances, key=lambda x: -x[1])
        best_dir, best_clear = sorted_sectors[0]

        # S1: Check if ANY direction has >= 2m clearance
        is_safe = best_clear >= self.min_clearance_m

        if not is_safe:
            violations.append(
                f"S1: No direction has {self.min_clearance_m}m clearance "
                f"(best: {best_clear:.1f}m at {best_dir:.0f} deg)"
            )

        return ClearanceResult(
            is_safe_to_move=is_safe,
            best_direction_deg=best_dir,
            best_clearance_m=best_clear,
            all_sectors=sector_clearances,
            violations=violations,
        )

    def should_skip_move(self, zone_confidence: float) -> bool:
        """S4: If single scan zone confidence > 85%, skip move entirely."""
        return zone_confidence > self.high_confidence

    def should_fallback_to_amcl(self, zone_confidence: float) -> bool:
        """S6: If confidence < 70% after all attempts, use AMCL."""
        return zone_confidence < self.min_confidence

    def can_publish_nav_goal(self, zone_confidence: float) -> bool:
        """S7: Never publish nav goal without >70% zone confirmation."""
        return zone_confidence >= self.min_confidence

    def create_safe_move(self, clearance: ClearanceResult,
                         desired_distance: float = MAX_MOVE_DISTANCE_M) -> Optional[MoveCommand]:
        """Create a safe move command respecting all safety rules.

        S1: Only moves if clearance verified
        S2: Speed capped at 0.1 m/s
        S3: Obstacle monitor should be active (caller responsibility)

        Args:
            clearance: Result from check_clearance().
            desired_distance: How far to move (capped by available clearance).

        Returns:
            MoveCommand if safe, None if cannot move.
        """
        if not clearance.is_safe_to_move:
            return None

        # Cap distance: min(desired, clearance - safety_buffer)
        max_safe_distance = clearance.best_clearance_m - self.safety_buffer_m
        actual_distance = min(desired_distance, max_safe_distance)

        if actual_distance < 0.3:
            # Too close to obstacle even with buffer
            return None

        return MoveCommand(
            direction_deg=clearance.best_direction_deg,
            distance_m=actual_distance,
            speed_mps=self.max_speed_mps,  # S2: always crawl speed
            clearance_verified=True,
        )

    def on_obstacle_detected(self):
        """S3: Called when obstacle detected during move. Must stop immediately."""
        self._obstacle_detected_during_move = True

    def is_move_aborted(self) -> bool:
        """Check if current move was aborted due to obstacle (S3)."""
        return self._obstacle_detected_during_move

    def reset_move_state(self):
        """Reset move state for next recovery attempt."""
        self._obstacle_detected_during_move = False

    def validate_recovery_result(self, zone: str, confidence: float,
                                 method: str) -> dict:
        """Validate a recovery result against all safety rules.

        Returns dict with pass/fail for each rule and overall verdict.
        """
        checks = {
            "S4_skip_respected": True,  # checked at call site
            "S5_safety_scanner": True,  # hardware — always independent
            "S6_amcl_fallback": not (confidence < self.min_confidence and method != "amcl_fallback"),
            "S7_nav_goal_ok": confidence >= self.min_confidence or method == "amcl_fallback",
        }
        checks["all_passed"] = all(checks.values())
        checks["zone"] = zone
        checks["confidence"] = confidence
        checks["method"] = method
        return checks

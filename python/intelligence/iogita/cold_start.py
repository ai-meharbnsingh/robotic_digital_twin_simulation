"""
ColdStartRecovery — saves/loads robot state for fast recovery.

When a robot restarts (power cycle, firmware update, error recovery),
this module provides hints to quickly restore context:
- Last known position and zone
- Active task state
- Battery profile
- Recommended re-initialization steps

Performance target: full recovery < 2s.
"""

import json
import time
from pathlib import Path
from typing import Any, Optional


class ColdStartRecovery:
    """
    Saves robot state snapshots and generates recovery hints
    for cold start scenarios.
    """

    def __init__(self, state_dir: Optional[Path] = None):
        """
        Args:
            state_dir: Directory to persist state snapshots.
                       If None, operates in memory-only mode.
        """
        self.state_dir = state_dir
        self._state_cache: dict[str, dict] = {}

        if state_dir is not None:
            state_dir.mkdir(parents=True, exist_ok=True)

    def save_state(self, robot_id: str, state: dict[str, Any]) -> bool:
        """
        Save a robot state snapshot.

        Args:
            robot_id: Robot identifier.
            state: Full robot state dict.

        Returns:
            True if saved successfully.
        """
        snapshot = {
            "robot_id": robot_id,
            "state": state,
            "saved_at": time.time(),
        }
        self._state_cache[robot_id] = snapshot

        if self.state_dir is not None:
            try:
                path = self.state_dir / f"{robot_id}.json"
                with open(path, "w") as f:
                    json.dump(snapshot, f, default=str)
                return True
            except Exception:
                return False
        return True

    def load_state(self, robot_id: str) -> Optional[dict[str, Any]]:
        """
        Load the last known state for a robot.

        Args:
            robot_id: Robot identifier.

        Returns:
            State dict or None if no state saved.
        """
        # Check memory cache first
        if robot_id in self._state_cache:
            return self._state_cache[robot_id]

        # Try disk
        if self.state_dir is not None:
            path = self.state_dir / f"{robot_id}.json"
            if path.exists():
                try:
                    with open(path, "r") as f:
                        snapshot = json.load(f)
                    self._state_cache[robot_id] = snapshot
                    return snapshot
                except Exception:
                    return None
        return None

    def generate_recovery_hints(self, robot_id: str, current_state: dict[str, Any]) -> dict[str, Any]:
        """
        Generate recovery hints for a cold-starting robot.

        Args:
            robot_id: Robot identifier.
            current_state: Current (possibly partial) robot state.

        Returns:
            Dict with recovery hints.
        """
        start = time.perf_counter()

        last_snapshot = self.load_state(robot_id)
        hints: dict[str, Any] = {
            "robot_id": robot_id,
            "has_prior_state": last_snapshot is not None,
            "steps": [],
        }

        if last_snapshot is not None:
            last_state = last_snapshot.get("state", {})
            age_s = time.time() - last_snapshot.get("saved_at", 0)
            hints["state_age_s"] = round(age_s, 1)

            # Position recovery
            pose = last_state.get("pose", {})
            if pose:
                hints["steps"].append({
                    "action": "restore_position",
                    "description": f"Restore to last known position ({pose.get('x', 0):.1f}, {pose.get('y', 0):.1f})",
                    "data": pose,
                })

            # Node recovery
            current_node = last_state.get("current_node", "")
            if current_node:
                hints["steps"].append({
                    "action": "localize_to_node",
                    "description": f"Localize to node {current_node}",
                    "data": {"node": current_node},
                })

            # Battery check
            battery = last_state.get("battery", {})
            charge = battery.get("charge_pct", 100)
            if charge < 20:
                hints["steps"].append({
                    "action": "charge_first",
                    "description": f"Battery was at {charge}% — charge before task resumption",
                    "data": {"charge_pct": charge},
                })

            # Task recovery
            task_id = last_state.get("current_task_id")
            if task_id:
                hints["steps"].append({
                    "action": "resume_task",
                    "description": f"Resume task {task_id}",
                    "data": {"task_id": task_id},
                })
        else:
            # No prior state — full initialization
            hints["steps"].append({
                "action": "full_init",
                "description": "No prior state found — perform full initialization",
                "data": {},
            })
            hints["steps"].append({
                "action": "localize",
                "description": "Run barcode/LiDAR localization to determine position",
                "data": {},
            })

        elapsed_ms = (time.perf_counter() - start) * 1000
        hints["recovery_time_ms"] = round(elapsed_ms, 2)

        return hints

    def clear_state(self, robot_id: str) -> bool:
        """Remove saved state for a robot."""
        self._state_cache.pop(robot_id, None)
        if self.state_dir is not None:
            path = self.state_dir / f"{robot_id}.json"
            if path.exists():
                # Move to .bak instead of deleting (per INVARIANT 0)
                bak = self.state_dir / f"{robot_id}.json.bak"
                path.rename(bak)
        return True

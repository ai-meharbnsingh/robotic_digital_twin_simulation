"""
ConveyorController — manages conveyor belt segments.

Each segment has:
  - State machine: IDLE → RUNNING → JAMMED → MAINTENANCE → IDLE
  - Speed control (m/s)
  - Direction (forward/reverse)
  - Jam detection (simulated via package dwell time)
  - Upstream/downstream segment linking (for cascade stop on jam)

Config-driven: loads from configs/wcs/conveyor_layout.yaml
"""

import time
import uuid
from enum import Enum
from typing import Any, Optional


class ConveyorState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    JAMMED = "jammed"
    MAINTENANCE = "maintenance"
    STOPPED = "stopped"          # Stopped by upstream jam or E-stop


class ConveyorSegment:
    """Single conveyor belt segment."""

    def __init__(
        self,
        segment_id: str,
        name: str,
        length_m: float,
        max_speed_mps: float = 1.5,
        direction: str = "forward",
        upstream_id: Optional[str] = None,
        upstream_ids: Optional[list[str]] = None,
        downstream_id: Optional[str] = None,
        max_belt_capacity: int = 20,
    ):
        self.segment_id = segment_id
        self.name = name
        self.length_m = length_m
        self.max_speed_mps = max_speed_mps
        self.direction = direction
        # Support both single upstream_id and multi upstream_ids
        if upstream_ids:
            self.upstream_ids = upstream_ids
        elif upstream_id:
            self.upstream_ids = [upstream_id]
        else:
            self.upstream_ids = []
        # Keep upstream_id as first element for backward compatibility
        self.upstream_id = self.upstream_ids[0] if self.upstream_ids else None
        self.downstream_id = downstream_id
        self.max_belt_capacity = max_belt_capacity

        self.state = ConveyorState.IDLE
        self.current_speed_mps = 0.0
        self.packages_on_belt: list[str] = []
        self.total_packages_transported = 0
        self.jam_count = 0
        self.last_state_change = time.time()
        self.uptime_s = 0.0
        self._run_start: Optional[float] = None

    def start(self, speed_mps: Optional[float] = None) -> dict:
        """Start the conveyor segment."""
        if self.state == ConveyorState.MAINTENANCE:
            return {"ok": False, "error": "segment in maintenance"}
        if self.state == ConveyorState.JAMMED:
            return {"ok": False, "error": "segment jammed — clear jam first"}

        target_speed = min(speed_mps or self.max_speed_mps, self.max_speed_mps)
        self.current_speed_mps = target_speed
        self.state = ConveyorState.RUNNING
        self.last_state_change = time.time()
        self._run_start = time.time()
        return {"ok": True, "speed_mps": self.current_speed_mps}

    def stop(self) -> dict:
        """Stop the conveyor segment."""
        if self._run_start:
            self.uptime_s += time.time() - self._run_start
            self._run_start = None
        self.current_speed_mps = 0.0
        self.state = ConveyorState.IDLE
        self.last_state_change = time.time()
        return {"ok": True}

    def set_speed(self, speed_mps: float) -> dict:
        """Change speed while running."""
        if self.state != ConveyorState.RUNNING:
            return {"ok": False, "error": "not running"}
        clamped = max(0.0, min(speed_mps, self.max_speed_mps))
        self.current_speed_mps = clamped
        return {"ok": True, "speed_mps": clamped}

    def trigger_jam(self, reason: str = "package_dwell_timeout") -> dict:
        """Trigger a jam condition."""
        if self._run_start:
            self.uptime_s += time.time() - self._run_start
            self._run_start = None
        self.state = ConveyorState.JAMMED
        self.current_speed_mps = 0.0
        self.jam_count += 1
        self.last_state_change = time.time()
        return {"ok": True, "reason": reason, "jam_count": self.jam_count}

    def clear_jam(self) -> dict:
        """Clear jam and return to idle."""
        if self.state != ConveyorState.JAMMED:
            return {"ok": False, "error": "not jammed"}
        self.state = ConveyorState.IDLE
        self.last_state_change = time.time()
        return {"ok": True}

    def set_maintenance(self, enable: bool) -> dict:
        """Enter/exit maintenance mode."""
        if enable:
            if self._run_start:
                self.uptime_s += time.time() - self._run_start
                self._run_start = None
            self.state = ConveyorState.MAINTENANCE
            self.current_speed_mps = 0.0
        else:
            self.state = ConveyorState.IDLE
        self.last_state_change = time.time()
        return {"ok": True, "maintenance": enable}

    def add_package(self, package_id: str) -> dict:
        """Package enters this segment."""
        if self.state != ConveyorState.RUNNING:
            return {"ok": False, "error": f"segment not running (state={self.state.value})"}
        if len(self.packages_on_belt) >= self.max_belt_capacity:
            return {"ok": False, "error": f"belt full ({self.max_belt_capacity} packages)"}
        self.packages_on_belt.append(package_id)
        return {"ok": True, "segment_id": self.segment_id}

    def remove_package(self, package_id: str) -> dict:
        """Package exits this segment."""
        if package_id in self.packages_on_belt:
            self.packages_on_belt.remove(package_id)
            self.total_packages_transported += 1
            return {"ok": True}
        return {"ok": False, "error": "package not on this segment"}

    def get_eta_s(self) -> float:
        """Estimated time for a package to traverse this segment."""
        if self.current_speed_mps <= 0:
            return float("inf")
        return self.length_m / self.current_speed_mps

    def to_dict(self) -> dict[str, Any]:
        """Serialize for API response."""
        return {
            "segment_id": self.segment_id,
            "name": self.name,
            "state": self.state.value,
            "speed_mps": round(self.current_speed_mps, 3),
            "max_speed_mps": self.max_speed_mps,
            "length_m": self.length_m,
            "direction": self.direction,
            "packages_on_belt": list(self.packages_on_belt),
            "package_count": len(self.packages_on_belt),
            "total_transported": self.total_packages_transported,
            "jam_count": self.jam_count,
            "upstream_id": self.upstream_id,
            "upstream_ids": list(self.upstream_ids),
            "downstream_id": self.downstream_id,
            "eta_s": round(self.get_eta_s(), 2) if self.current_speed_mps > 0 else None,
            "uptime_s": round(self.uptime_s, 1),
        }


class ConveyorController:
    """Manages all conveyor segments in the warehouse.

    Handles:
    - Segment CRUD (from config)
    - Start/stop/speed control
    - Jam detection and cascade stop
    - Package flow between segments
    """

    def __init__(self):
        self._segments: dict[str, ConveyorSegment] = {}

    def load_config(self, config: dict):
        """Load conveyor layout from config dict.

        Config format:
          segments:
            - segment_id: "CONV_01"
              name: "Inbound Belt A"
              length_m: 8.0
              max_speed_mps: 1.5
              direction: "forward"
              upstream_id: null
              downstream_id: "CONV_02"
        """
        for seg_cfg in config.get("segments", []):
            seg = ConveyorSegment(
                segment_id=seg_cfg["segment_id"],
                name=seg_cfg.get("name", seg_cfg["segment_id"]),
                length_m=seg_cfg.get("length_m", 5.0),
                max_speed_mps=seg_cfg.get("max_speed_mps", 1.5),
                direction=seg_cfg.get("direction", "forward"),
                upstream_id=seg_cfg.get("upstream_id"),
                upstream_ids=seg_cfg.get("upstream_ids"),
                downstream_id=seg_cfg.get("downstream_id"),
                max_belt_capacity=seg_cfg.get("max_belt_capacity", 20),
            )
            self._segments[seg.segment_id] = seg

    def get_segment(self, segment_id: str) -> Optional[ConveyorSegment]:
        return self._segments.get(segment_id)

    def get_all_segments(self) -> list[dict]:
        return [s.to_dict() for s in self._segments.values()]

    def start_segment(self, segment_id: str, speed_mps: Optional[float] = None) -> dict:
        seg = self._segments.get(segment_id)
        if not seg:
            return {"ok": False, "error": f"segment '{segment_id}' not found"}
        return seg.start(speed_mps)

    def stop_segment(self, segment_id: str) -> dict:
        seg = self._segments.get(segment_id)
        if not seg:
            return {"ok": False, "error": f"segment '{segment_id}' not found"}
        return seg.stop()

    def start_all(self, speed_mps: Optional[float] = None) -> dict:
        """Start all segments."""
        results = {}
        for sid, seg in self._segments.items():
            results[sid] = seg.start(speed_mps)
        return {"ok": True, "segments": results}

    def stop_all(self) -> dict:
        """Emergency stop all segments."""
        for seg in self._segments.values():
            seg.stop()
        return {"ok": True, "stopped": len(self._segments)}

    def trigger_jam(self, segment_id: str, reason: str = "package_dwell_timeout") -> dict:
        """Trigger jam on a segment and cascade-stop upstream segments."""
        seg = self._segments.get(segment_id)
        if not seg:
            return {"ok": False, "error": f"segment '{segment_id}' not found"}

        result = seg.trigger_jam(reason)

        # Cascade stop: BFS traversal of upstream_ids graph.
        # Handles merge topology (e.g., INBOUND_A + INBOUND_B → MAIN_LINE).
        # visited set prevents infinite loops in cyclic configurations.
        cascade_stopped = []
        queue = list(seg.upstream_ids)
        visited = set()
        while queue:
            current_id = queue.pop(0)
            if current_id in visited or current_id not in self._segments:
                continue
            visited.add(current_id)
            upstream = self._segments[current_id]
            if upstream.state == ConveyorState.RUNNING:
                # Accumulate uptime before transitioning to STOPPED
                if upstream._run_start:
                    upstream.uptime_s += time.time() - upstream._run_start
                    upstream._run_start = None
                upstream.state = ConveyorState.STOPPED
                upstream.current_speed_mps = 0.0
                cascade_stopped.append(current_id)
            queue.extend(upstream.upstream_ids)

        result["cascade_stopped"] = cascade_stopped
        return result

    def clear_jam(self, segment_id: str) -> dict:
        """Clear jam and resume cascade-stopped upstream segments."""
        seg = self._segments.get(segment_id)
        if not seg:
            return {"ok": False, "error": f"segment '{segment_id}' not found"}

        result = seg.clear_jam()

        # Resume ALL upstream segments that were cascade-stopped (BFS for merge topology)
        cascade_resumed = []
        queue = list(seg.upstream_ids)
        visited = set()
        while queue:
            current_id = queue.pop(0)
            if current_id in visited or current_id not in self._segments:
                continue
            visited.add(current_id)
            upstream = self._segments[current_id]
            if upstream.state == ConveyorState.STOPPED:
                upstream.start()
                cascade_resumed.append(current_id)
            queue.extend(upstream.upstream_ids)

        result["cascade_resumed"] = cascade_resumed
        return result

    def transfer_package(self, package_id: str, from_id: str, to_id: str) -> dict:
        """Move package from one segment to the next (atomic)."""
        from_seg = self._segments.get(from_id)
        to_seg = self._segments.get(to_id)

        if not from_seg:
            return {"ok": False, "error": f"source segment '{from_id}' not found"}
        if not to_seg:
            return {"ok": False, "error": f"destination segment '{to_id}' not found"}
        if package_id not in from_seg.packages_on_belt:
            return {"ok": False, "error": f"package '{package_id}' not on segment '{from_id}'"}

        # Check destination accepts BEFORE removing from source (atomic)
        if to_seg.state != ConveyorState.RUNNING:
            return {"ok": False, "error": f"destination '{to_id}' not running (state={to_seg.state.value})"}
        if len(to_seg.packages_on_belt) >= to_seg.max_belt_capacity:
            return {"ok": False, "error": f"destination '{to_id}' belt full ({to_seg.max_belt_capacity})"}

        # Now safe to transfer
        from_seg.packages_on_belt.remove(package_id)
        from_seg.total_packages_transported += 1
        to_seg.packages_on_belt.append(package_id)

        return {"ok": True, "from": from_id, "to": to_id, "package_id": package_id}

    def get_stats(self) -> dict:
        """System-wide conveyor statistics."""
        total = len(self._segments)
        by_state = {}
        for s in self._segments.values():
            by_state[s.state.value] = by_state.get(s.state.value, 0) + 1
        total_transported = sum(s.total_packages_transported for s in self._segments.values())
        total_on_belt = sum(len(s.packages_on_belt) for s in self._segments.values())
        total_jams = sum(s.jam_count for s in self._segments.values())

        return {
            "total_segments": total,
            "running": by_state.get("running", 0),
            "jammed": by_state.get("jammed", 0),
            "idle": by_state.get("idle", 0),
            "stopped": by_state.get("stopped", 0),
            "maintenance": by_state.get("maintenance", 0),
            "total_packages_transported": total_transported,
            "packages_on_belt": total_on_belt,
            "total_jam_events": total_jams,
        }

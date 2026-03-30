"""
ConveyorDesigner — design conveyor layouts for 3D warehouse visualization.

Provides:
  generate_conveyor_layout — create conveyor segments from waypoints
  add_divert_point — add sorter divert at position on segment
  auto_connect_to_lanes — wire conveyor endpoints to outbound lanes
  export_yaml — generate conveyor_layout.yaml from designed layout
  validate_topology — check no orphaned segments, consistent flow direction

Called from: app/routes/designer.py (Phase 15 endpoints).
"""

import math
from collections import defaultdict, deque
from typing import Any

import yaml


ALLOWED_DIVERT_TYPES = {"popup", "tilt_tray", "crossbelt", "pusher"}


class ConveyorDesigner:
    """Design conveyor layouts for warehouse systems."""

    def __init__(self):
        self._segments: list[dict] = []
        self._divert_points: list[dict] = []
        self._lanes: list[dict] = []
        self._next_segment_id = 1
        self._next_divert_id = 1

    # ── generate_conveyor_layout ────────────────────────────────

    def generate_conveyor_layout(
        self, waypoints: list[dict], max_speed_mps: float = 1.5
    ) -> list[dict]:
        """
        From a list of (x, y) waypoints, create conveyor segments.

        Each consecutive pair of waypoints becomes a segment.
        Segment length is the Euclidean distance between the points.

        Args:
            waypoints: List of dicts with 'x' and 'y' (meters).
                       Minimum 2 waypoints required.
            max_speed_mps: Maximum speed in meters per second (default 1.5).

        Returns:
            List of segment dicts, each with:
              segment_id, name, length_m, max_speed_mps,
              direction, start_x, start_y, end_x, end_y,
              upstream_id, downstream_id.
        """
        if len(waypoints) < 2:
            return []

        self._segments = []
        segments: list[dict] = []

        for i in range(len(waypoints) - 1):
            start = waypoints[i]
            end = waypoints[i + 1]

            dx = float(end["x"]) - float(start["x"])
            dy = float(end["y"]) - float(start["y"])
            length = round(math.sqrt(dx * dx + dy * dy), 3)

            seg_id = f"SEG_{self._next_segment_id:03d}"
            self._next_segment_id += 1

            upstream = segments[-1]["segment_id"] if segments else None
            segment = {
                "segment_id": seg_id,
                "name": f"Conveyor Segment {seg_id}",
                "length_m": length,
                "max_speed_mps": max_speed_mps,
                "direction": "forward",
                "start_x": float(start["x"]),
                "start_y": float(start["y"]),
                "end_x": float(end["x"]),
                "end_y": float(end["y"]),
                "upstream_id": upstream,
                "downstream_id": None,
            }

            # Link previous segment's downstream to this segment
            if segments:
                segments[-1]["downstream_id"] = seg_id

            segments.append(segment)

        self._segments = segments
        return list(segments)

    # ── add_divert_point ────────────────────────────────────────

    def add_divert_point(
        self,
        segment_id: str,
        position_m: float,
        target_lane: str,
        divert_type: str = "popup",
    ) -> dict | None:
        """
        Add a sorter divert point on a segment.

        Args:
            segment_id: ID of the segment to add divert to.
            position_m: Distance along segment where divert is placed (meters).
            target_lane: Lane ID where diverted items go.
            divert_type: Type of divert mechanism (popup, tilt_tray, crossbelt, pusher).

        Returns:
            Divert point dict, or None if segment_id not found or invalid divert_type.

        Raises:
            ValueError: If divert_type is not in ALLOWED_DIVERT_TYPES.
        """
        if divert_type not in ALLOWED_DIVERT_TYPES:
            raise ValueError(
                f"Invalid divert_type '{divert_type}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_DIVERT_TYPES))}"
            )

        # Verify segment exists
        seg = None
        for s in self._segments:
            if s["segment_id"] == segment_id:
                seg = s
                break

        if seg is None:
            return None

        # Validate position within segment length
        if position_m < 0 or position_m > seg["length_m"]:
            return None

        divert_id = f"DIV_{self._next_divert_id:03d}"
        self._next_divert_id += 1

        divert = {
            "divert_id": divert_id,
            "name": f"Divert {divert_id}",
            "segment_id": segment_id,
            "position_m": round(position_m, 3),
            "target_lane": target_lane,
            "divert_type": divert_type,
        }
        self._divert_points.append(divert)
        return divert

    # ── auto_connect_to_lanes ───────────────────────────────────

    def auto_connect_to_lanes(
        self, segments: list[dict], lanes: list[dict]
    ) -> list[dict]:
        """
        Wire conveyor segment endpoints to lanes.

        Logic:
        - Segments with no upstream (entry points) connect to 'inbound' lanes.
        - Segments with no downstream (exit points) connect to 'outbound' lanes.
        - Matching is by order: first entry segment to first inbound lane, etc.

        Args:
            segments: List of segment dicts.
            lanes: List of lane dicts with 'lane_id', 'type'.

        Returns:
            Updated list of lane dicts with 'connected_segment_id' set.
        """
        if not segments or not lanes:
            return list(lanes) if lanes else []

        # Find entry and exit segments
        entry_segments = [s for s in segments if s.get("upstream_id") is None]
        exit_segments = [s for s in segments if s.get("downstream_id") is None]

        inbound_lanes = [l for l in lanes if l.get("type") == "inbound"]
        outbound_lanes = [l for l in lanes if l.get("type") == "outbound"]

        updated_lanes = []
        for lane in lanes:
            updated = dict(lane)
            if lane.get("type") == "inbound" and entry_segments:
                idx = inbound_lanes.index(lane) if lane in inbound_lanes else -1
                if 0 <= idx < len(entry_segments):
                    updated["connected_segment_id"] = entry_segments[idx]["segment_id"]
            elif lane.get("type") == "outbound" and exit_segments:
                idx = outbound_lanes.index(lane) if lane in outbound_lanes else -1
                if 0 <= idx < len(exit_segments):
                    updated["connected_segment_id"] = exit_segments[idx]["segment_id"]
            updated_lanes.append(updated)

        self._lanes = updated_lanes
        return updated_lanes

    # ── export_yaml ─────────────────────────────────────────────

    def export_yaml(self) -> str:
        """
        Generate YAML representation of the designed conveyor layout.

        Produces a structure compatible with configs/wcs/conveyor_layout.yaml.

        Returns:
            YAML string.
        """
        # Convert segments to YAML-friendly format (strip start/end coords for config)
        yaml_segments = []
        for seg in self._segments:
            yaml_seg = {
                "segment_id": seg["segment_id"],
                "name": seg["name"],
                "length_m": seg["length_m"],
                "max_speed_mps": seg["max_speed_mps"],
                "direction": seg["direction"],
                "upstream_id": seg["upstream_id"],
                "downstream_id": seg["downstream_id"],
            }
            yaml_segments.append(yaml_seg)

        data: dict[str, Any] = {
            "segments": yaml_segments,
            "divert_points": list(self._divert_points),
            "lanes": list(self._lanes),
        }

        return yaml.dump(data, default_flow_style=False, sort_keys=False)

    # ── validate_topology ───────────────────────────────────────

    def validate_topology(self) -> dict:
        """
        Validate the conveyor topology.

        Checks:
        1. No orphaned segments (every segment reachable from some entry point).
        2. Flow direction consistent (no bidirectional cycles within a chain).
        3. All divert point segment references are valid.
        4. All lane segment references are valid.

        Returns:
            {
                "valid": bool,
                "errors": [str],
                "warnings": [str],
                "segment_count": int,
                "divert_count": int,
                "entry_points": [segment_ids],
                "exit_points": [segment_ids],
            }
        """
        errors: list[str] = []
        warnings: list[str] = []

        if not self._segments:
            errors.append("No segments defined")
            return {
                "valid": False,
                "errors": errors,
                "warnings": warnings,
                "segment_count": 0,
                "divert_count": 0,
                "entry_points": [],
                "exit_points": [],
            }

        seg_ids = {s["segment_id"] for s in self._segments}

        # Find entry and exit points
        entry_points = [
            s["segment_id"]
            for s in self._segments
            if s.get("upstream_id") is None
        ]
        exit_points = [
            s["segment_id"]
            for s in self._segments
            if s.get("downstream_id") is None
        ]

        if not entry_points:
            errors.append("No entry points (all segments have upstream)")

        if not exit_points:
            errors.append("No exit points (all segments have downstream)")

        # Check for orphaned segments via BFS from entry points
        reachable: set[str] = set()
        queue: deque[str] = deque(entry_points)
        reachable.update(entry_points)

        # Build downstream adjacency
        downstream_map: dict[str, str | None] = {}
        for seg in self._segments:
            downstream_map[seg["segment_id"]] = seg.get("downstream_id")

        while queue:
            current = queue.popleft()
            ds = downstream_map.get(current)
            if ds and ds in seg_ids and ds not in reachable:
                reachable.add(ds)
                queue.append(ds)

        orphaned = seg_ids - reachable
        if orphaned:
            errors.append(
                f"Orphaned segments (not reachable from entry): {', '.join(sorted(orphaned))}"
            )

        # Check divert point references
        for dp in self._divert_points:
            if dp["segment_id"] not in seg_ids:
                errors.append(
                    f"Divert {dp['divert_id']} references nonexistent segment: {dp['segment_id']}"
                )

        # Check lane segment references
        for lane in self._lanes:
            connected = lane.get("connected_segment_id")
            if connected and connected not in seg_ids:
                warnings.append(
                    f"Lane {lane.get('lane_id', '?')} references nonexistent segment: {connected}"
                )

        # Flow direction consistency check: detect cycles
        for entry in entry_points:
            chain: set[str] = set()
            current: str | None = entry
            while current and current in seg_ids:
                if current in chain:
                    errors.append(
                        f"Cycle detected in conveyor chain starting from {entry}"
                    )
                    break
                chain.add(current)
                current = downstream_map.get(current)

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "segment_count": len(self._segments),
            "divert_count": len(self._divert_points),
            "entry_points": entry_points,
            "exit_points": exit_points,
        }

    # ── accessors ───────────────────────────────────────────────

    @property
    def segments(self) -> list[dict]:
        """Current segment list."""
        return list(self._segments)

    @property
    def divert_points(self) -> list[dict]:
        """Current divert point list."""
        return list(self._divert_points)

    @property
    def lanes(self) -> list[dict]:
        """Current lane list."""
        return list(self._lanes)

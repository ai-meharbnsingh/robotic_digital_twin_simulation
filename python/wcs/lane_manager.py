"""
LaneManager — manages inbound/outbound warehouse lanes.

Lanes are endpoints of conveyors:
  - Inbound lanes: receiving dock → conveyor → storage
  - Outbound lanes: storage → conveyor → shipping dock
  - Express lanes: priority processing

Tracks capacity, occupancy, overflow alerts.
"""

import time
from enum import Enum
from typing import Any, Optional


class LaneType(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    EXPRESS = "express"
    RETURNS = "returns"
    STAGING = "staging"


class LaneState(str, Enum):
    OPEN = "open"
    FULL = "full"
    CLOSED = "closed"
    OVERFLOW = "overflow"


class Lane:
    """Single warehouse lane (inbound or outbound)."""

    def __init__(
        self,
        lane_id: str,
        name: str,
        lane_type: LaneType,
        max_capacity: int = 50,
        connected_segment_id: Optional[str] = None,
    ):
        self.lane_id = lane_id
        self.name = name
        self.lane_type = lane_type
        self.max_capacity = max_capacity
        self.connected_segment_id = connected_segment_id

        self.current_count = 0
        self.packages: list[str] = []
        self.state = LaneState.OPEN
        self.total_processed = 0
        self.overflow_events = 0
        self.last_activity = time.time()

    def add_package(self, package_id: str) -> dict:
        """Add package to lane."""
        if self.state == LaneState.CLOSED:
            return {"ok": False, "error": "lane closed"}

        if self.current_count >= self.max_capacity:
            self.state = LaneState.OVERFLOW
            self.overflow_events += 1
            return {"ok": False, "error": "lane full", "overflow": True}

        self.packages.append(package_id)
        self.current_count += 1
        self.last_activity = time.time()

        if self.current_count >= self.max_capacity:
            self.state = LaneState.FULL
        else:
            self.state = LaneState.OPEN

        return {"ok": True, "count": self.current_count, "capacity": self.max_capacity}

    def remove_package(self, package_id: Optional[str] = None) -> dict:
        """Remove package from lane (FIFO if no specific ID)."""
        if self.current_count == 0:
            return {"ok": False, "error": "lane empty"}

        if package_id:
            if package_id not in self.packages:
                return {"ok": False, "error": f"package '{package_id}' not in this lane"}
            self.packages.remove(package_id)
        elif self.packages:
            package_id = self.packages.pop(0)
        else:
            return {"ok": False, "error": "no packages"}

        self.current_count -= 1
        self.total_processed += 1
        self.last_activity = time.time()

        if self.current_count < self.max_capacity:
            self.state = LaneState.OPEN

        return {"ok": True, "package_id": package_id, "count": self.current_count}

    def close(self) -> dict:
        self.state = LaneState.CLOSED
        return {"ok": True}

    def open(self) -> dict:
        self.state = LaneState.FULL if self.current_count >= self.max_capacity else LaneState.OPEN
        return {"ok": True}

    def get_utilization_pct(self) -> float:
        if self.max_capacity <= 0:
            return 0.0
        return round(self.current_count / self.max_capacity * 100, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "lane_id": self.lane_id,
            "name": self.name,
            "type": self.lane_type.value,
            "state": self.state.value,
            "current_count": self.current_count,
            "max_capacity": self.max_capacity,
            "utilization_pct": self.get_utilization_pct(),
            "packages": list(self.packages),
            "total_processed": self.total_processed,
            "overflow_events": self.overflow_events,
            "connected_segment_id": self.connected_segment_id,
        }


class LaneManager:
    """Manages all warehouse lanes."""

    def __init__(self):
        self._lanes: dict[str, Lane] = {}

    def load_config(self, config: dict):
        """Load lane definitions from config."""
        for lane_cfg in config.get("lanes", []):
            lane = Lane(
                lane_id=lane_cfg["lane_id"],
                name=lane_cfg.get("name", lane_cfg["lane_id"]),
                lane_type=LaneType(lane_cfg.get("type", "outbound")),
                max_capacity=lane_cfg.get("max_capacity", 50),
                connected_segment_id=lane_cfg.get("connected_segment_id"),
            )
            self._lanes[lane.lane_id] = lane

    def get_lane(self, lane_id: str) -> Optional[Lane]:
        return self._lanes.get(lane_id)

    def get_all_lanes(self) -> list[dict]:
        return [l.to_dict() for l in self._lanes.values()]

    def get_lanes_by_type(self, lane_type: LaneType) -> list[dict]:
        return [l.to_dict() for l in self._lanes.values() if l.lane_type == lane_type]

    def get_capacities(self) -> dict[str, dict]:
        """Return capacity info for all lanes (used by SorterEngine)."""
        return {
            lid: {"current": l.current_count, "max": l.max_capacity}
            for lid, l in self._lanes.items()
        }

    def add_package_to_lane(self, lane_id: str, package_id: str) -> dict:
        lane = self._lanes.get(lane_id)
        if not lane:
            return {"ok": False, "error": f"lane '{lane_id}' not found"}
        return lane.add_package(package_id)

    def remove_package_from_lane(self, lane_id: str, package_id: Optional[str] = None) -> dict:
        lane = self._lanes.get(lane_id)
        if not lane:
            return {"ok": False, "error": f"lane '{lane_id}' not found"}
        return lane.remove_package(package_id)

    def get_stats(self) -> dict:
        total = len(self._lanes)
        # Count each state explicitly — avoids bugs when subtraction ignores OVERFLOW
        by_state: dict[str, int] = {}
        for l in self._lanes.values():
            by_state[l.state.value] = by_state.get(l.state.value, 0) + 1
        total_packages = sum(l.current_count for l in self._lanes.values())
        total_capacity = sum(l.max_capacity for l in self._lanes.values())
        total_processed = sum(l.total_processed for l in self._lanes.values())
        total_overflows = sum(l.overflow_events for l in self._lanes.values())

        return {
            "total_lanes": total,
            "open": by_state.get("open", 0),
            "full": by_state.get("full", 0),
            "closed": by_state.get("closed", 0),
            "overflow": by_state.get("overflow", 0),
            "total_packages": total_packages,
            "total_capacity": total_capacity,
            "utilization_pct": round(total_packages / max(total_capacity, 1) * 100, 1),
            "total_processed": total_processed,
            "total_overflow_events": total_overflows,
        }

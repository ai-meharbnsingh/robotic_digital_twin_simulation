"""
PackageTracker — tracks packages through the entire material flow.

Journey: Robot pick → conveyor entry → segment-to-segment → divert → lane → ship

Each event is logged with timestamp, location, and action.
Query any package's full journey or current location.
"""

import time
import uuid
from enum import Enum
from typing import Any, Optional


class PackageEvent(str, Enum):
    CREATED = "created"
    ROBOT_PICKED = "robot_picked"
    ROBOT_DROPPED = "robot_dropped"
    CONVEYOR_ENTRY = "conveyor_entry"
    CONVEYOR_TRANSFER = "conveyor_transfer"
    CONVEYOR_EXIT = "conveyor_exit"
    SORTER_SCANNED = "sorter_scanned"
    SORTER_DIVERTED = "sorter_diverted"
    SORTER_DEFAULT = "sorter_default"
    SORTER_MISREAD = "sorter_misread"
    LANE_ENTRY = "lane_entry"
    LANE_EXIT = "lane_exit"
    SHIPPED = "shipped"
    ERROR = "error"


class PackageTracker:
    """Tracks packages from creation through shipment."""

    def __init__(self):
        self._packages: dict[str, dict] = {}
        self._events: dict[str, list[dict]] = {}

    def create_package(
        self,
        barcode: str,
        order_id: Optional[str] = None,
        sku: Optional[str] = None,
        weight_kg: float = 0.0,
    ) -> str:
        """Create a new package and return its tracking ID."""
        package_id = str(uuid.uuid4())[:12]
        self._packages[package_id] = {
            "package_id": package_id,
            "barcode": barcode,
            "order_id": order_id,
            "sku": sku,
            "weight_kg": weight_kg,
            "status": PackageEvent.CREATED.value,
            "current_location": None,
            "current_location_type": None,
            "created_at": time.time(),
            "shipped_at": None,
        }
        self._events[package_id] = []
        self._log_event(package_id, PackageEvent.CREATED, location="origin")
        return package_id

    def log_event(
        self,
        package_id: str,
        event: PackageEvent,
        location: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> dict:
        """Log an event for a package."""
        if package_id not in self._packages:
            return {"ok": False, "error": f"package '{package_id}' not found"}
        self._log_event(package_id, event, location, details)
        return {"ok": True, "event": event.value}

    def _log_event(
        self,
        package_id: str,
        event: PackageEvent,
        location: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        entry = {
            "event": event.value,
            "location": location,
            "timestamp": time.time(),
            "details": details or {},
        }
        if package_id not in self._events:
            self._events[package_id] = []
        self._events[package_id].append(entry)

        pkg = self._packages.get(package_id)
        if pkg:
            pkg["status"] = event.value
            if location:
                pkg["current_location"] = location
                # Determine location type
                if event in (PackageEvent.CONVEYOR_ENTRY, PackageEvent.CONVEYOR_TRANSFER):
                    pkg["current_location_type"] = "conveyor"
                elif event in (PackageEvent.LANE_ENTRY,):
                    pkg["current_location_type"] = "lane"
                elif event in (PackageEvent.SORTER_DIVERTED, PackageEvent.SORTER_SCANNED):
                    pkg["current_location_type"] = "sorter"
                elif event == PackageEvent.SHIPPED:
                    pkg["current_location_type"] = "shipped"
                    pkg["shipped_at"] = time.time()

    def get_package(self, package_id: str) -> Optional[dict]:
        """Get package info + full event history."""
        pkg = self._packages.get(package_id)
        if not pkg:
            return None
        result = dict(pkg)
        result["events"] = self._events.get(package_id, [])
        result["event_count"] = len(result["events"])
        if result["events"]:
            result["age_s"] = round(time.time() - result["events"][0]["timestamp"], 1)
        return result

    def find_by_barcode(self, barcode: str) -> list[dict]:
        """Find all packages with a given barcode."""
        return [
            dict(p) for p in self._packages.values()
            if p["barcode"] == barcode
        ]

    def get_packages_at_location(self, location: str) -> list[dict]:
        """Find all packages currently at a location."""
        return [
            dict(p) for p in self._packages.values()
            if p["current_location"] == location
        ]

    def get_in_transit(self) -> list[dict]:
        """Get all packages currently in the system (not shipped)."""
        return [
            dict(p) for p in self._packages.values()
            if p["status"] != PackageEvent.SHIPPED.value
        ]

    def get_stats(self) -> dict:
        total = len(self._packages)
        shipped = sum(1 for p in self._packages.values()
                      if p["status"] == PackageEvent.SHIPPED.value)
        in_transit = total - shipped
        on_conveyor = sum(1 for p in self._packages.values()
                          if p.get("current_location_type") == "conveyor")
        in_lane = sum(1 for p in self._packages.values()
                       if p.get("current_location_type") == "lane")
        errors = sum(1 for p in self._packages.values()
                      if p["status"] == PackageEvent.ERROR.value)

        # Average transit time for shipped packages
        transit_times = []
        for pid, pkg in self._packages.items():
            if pkg.get("shipped_at") and pkg.get("created_at"):
                transit_times.append(pkg["shipped_at"] - pkg["created_at"])
        avg_transit_s = round(sum(transit_times) / max(len(transit_times), 1), 1)

        return {
            "total_packages": total,
            "shipped": shipped,
            "in_transit": in_transit,
            "on_conveyor": on_conveyor,
            "in_lane": in_lane,
            "errors": errors,
            "avg_transit_time_s": avg_transit_s,
        }

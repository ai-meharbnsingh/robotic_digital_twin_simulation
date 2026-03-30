"""
SorterEngine — routes packages to correct outbound lanes.

Supports:
  - Barcode/SKU → lane routing rules
  - Divert mechanisms: popup, tilt-tray, crossbelt (simulated)
  - Priority lanes (express/urgent)
  - Error handling: misread barcode, full lane, unknown SKU
  - Throughput tracking per divert point

Config-driven: rules loaded from conveyor_layout.yaml or added via API.
"""

import time
import uuid
from collections import deque
from enum import Enum
from typing import Any, Optional


class DivertType(str, Enum):
    POPUP = "popup"
    TILT_TRAY = "tilt_tray"
    CROSSBELT = "crossbelt"
    PUSHER = "pusher"


class SortResult(str, Enum):
    DIVERTED = "diverted"
    NO_RULE = "no_rule"
    LANE_FULL = "lane_full"
    MISREAD = "misread"
    DEFAULT_LANE = "default_lane"


class SortRule:
    """Routing rule: barcode pattern → target lane."""

    def __init__(
        self,
        rule_id: str,
        pattern: str,
        target_lane: str,
        priority: int = 0,
        enabled: bool = True,
    ):
        self.rule_id = rule_id
        self.pattern = pattern          # SKU prefix or exact match
        self.target_lane = target_lane
        self.priority = priority        # Higher = checked first
        self.enabled = enabled
        self.match_count = 0

    def matches(self, barcode: str) -> bool:
        """Check if barcode matches this rule's pattern."""
        if not self.enabled:
            return False
        # Prefix match or exact match
        return barcode.startswith(self.pattern) or barcode == self.pattern

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "pattern": self.pattern,
            "target_lane": self.target_lane,
            "priority": self.priority,
            "enabled": self.enabled,
            "match_count": self.match_count,
        }


class DivertPoint:
    """Physical divert location on the conveyor line."""

    def __init__(
        self,
        divert_id: str,
        name: str,
        segment_id: str,
        position_m: float,
        target_lane: str,
        divert_type: DivertType = DivertType.POPUP,
    ):
        self.divert_id = divert_id
        self.name = name
        self.segment_id = segment_id    # Which conveyor segment this divert is on
        self.position_m = position_m    # Position along the segment
        self.target_lane = target_lane
        self.divert_type = divert_type
        self.diverted_count = 0
        self.error_count = 0
        self.enabled = True

    def to_dict(self) -> dict:
        return {
            "divert_id": self.divert_id,
            "name": self.name,
            "segment_id": self.segment_id,
            "position_m": self.position_m,
            "target_lane": self.target_lane,
            "divert_type": self.divert_type.value,
            "diverted_count": self.diverted_count,
            "error_count": self.error_count,
            "enabled": self.enabled,
        }


class SorterEngine:
    """Routes packages to outbound lanes based on barcode/SKU rules.

    Flow:
      1. Package arrives at divert point with barcode
      2. Look up rules (highest priority first)
      3. If rule matches → check target lane capacity → divert
      4. If no rule → send to default lane
      5. If lane full → hold on conveyor, alert
    """

    def __init__(self, default_lane: str = "DEFAULT"):
        self._rules: list[SortRule] = []
        self._diverts: dict[str, DivertPoint] = {}
        self._default_lane = default_lane
        self._max_log = 1000
        self._sort_log: deque[dict] = deque(maxlen=self._max_log)

    def load_config(self, config: dict):
        """Load sort rules and divert points from config."""
        for rule_cfg in config.get("sort_rules", []):
            rule = SortRule(
                rule_id=rule_cfg.get("rule_id", str(uuid.uuid4())),
                pattern=rule_cfg["pattern"],
                target_lane=rule_cfg["target_lane"],
                priority=rule_cfg.get("priority", 0),
                enabled=rule_cfg.get("enabled", True),
            )
            self._rules.append(rule)

        # Sort by priority descending
        self._rules.sort(key=lambda r: -r.priority)

        for div_cfg in config.get("divert_points", []):
            dp = DivertPoint(
                divert_id=div_cfg["divert_id"],
                name=div_cfg.get("name", div_cfg["divert_id"]),
                segment_id=div_cfg["segment_id"],
                position_m=div_cfg.get("position_m", 0.0),
                target_lane=div_cfg["target_lane"],
                divert_type=DivertType(div_cfg.get("divert_type", "popup")),
            )
            self._diverts[dp.divert_id] = dp

    def add_rule(self, pattern: str, target_lane: str, priority: int = 0) -> SortRule:
        """Add a routing rule at runtime."""
        rule = SortRule(
            rule_id=str(uuid.uuid4()),
            pattern=pattern,
            target_lane=target_lane,
            priority=priority,
        )
        self._rules.append(rule)
        self._rules.sort(key=lambda r: -r.priority)
        return rule

    def remove_rule(self, rule_id: str) -> bool:
        before = len(self._rules)
        self._rules = [r for r in self._rules if r.rule_id != rule_id]
        return len(self._rules) < before

    def get_rules(self) -> list[dict]:
        return [r.to_dict() for r in self._rules]

    def get_diverts(self) -> list[dict]:
        return [d.to_dict() for d in self._diverts.values()]

    def sort_package(
        self,
        package_id: str,
        barcode: str,
        lane_capacities: Optional[dict[str, dict]] = None,
    ) -> dict:
        """Determine which lane a package should go to.

        Args:
            package_id: Unique package identifier.
            barcode: Scanned barcode/SKU.
            lane_capacities: {lane_id: {"current": N, "max": M}} for fullness check.

        Returns:
            {result, target_lane, rule_id, divert_id}
        """
        if not barcode or barcode.strip() == "":
            entry = {
                "package_id": package_id,
                "barcode": barcode,
                "result": SortResult.MISREAD.value,
                "target_lane": self._default_lane,
                "rule_id": None,
                "timestamp": time.time(),
            }
            self._log(entry)
            return entry

        # Find matching rule (highest priority first)
        for rule in self._rules:
            if rule.matches(barcode):
                target = rule.target_lane

                # Check lane capacity
                if lane_capacities and target in lane_capacities:
                    cap = lane_capacities[target]
                    if cap.get("current", 0) >= cap.get("max", float("inf")):
                        entry = {
                            "package_id": package_id,
                            "barcode": barcode,
                            "result": SortResult.LANE_FULL.value,
                            "target_lane": target,
                            "rule_id": rule.rule_id,
                            "timestamp": time.time(),
                        }
                        self._log(entry)
                        return entry

                rule.match_count += 1

                # Find divert point for this lane
                divert_id = None
                for dp in self._diverts.values():
                    if dp.target_lane == target and dp.enabled:
                        dp.diverted_count += 1
                        divert_id = dp.divert_id
                        break

                entry = {
                    "package_id": package_id,
                    "barcode": barcode,
                    "result": SortResult.DIVERTED.value,
                    "target_lane": target,
                    "rule_id": rule.rule_id,
                    "divert_id": divert_id,
                    "timestamp": time.time(),
                }
                self._log(entry)
                return entry

        # No matching rule → default lane
        entry = {
            "package_id": package_id,
            "barcode": barcode,
            "result": SortResult.DEFAULT_LANE.value,
            "target_lane": self._default_lane,
            "rule_id": None,
            "timestamp": time.time(),
        }
        self._log(entry)
        return entry

    def get_stats(self) -> dict:
        total = len(self._sort_log)
        diverted = sum(1 for e in self._sort_log if e["result"] == SortResult.DIVERTED.value)
        misread = sum(1 for e in self._sort_log if e["result"] == SortResult.MISREAD.value)
        lane_full = sum(1 for e in self._sort_log if e["result"] == SortResult.LANE_FULL.value)
        default = sum(1 for e in self._sort_log if e["result"] == SortResult.DEFAULT_LANE.value)

        return {
            "total_sorted": total,
            "diverted": diverted,
            "misread": misread,
            "lane_full": lane_full,
            "default_lane": default,
            "accuracy_pct": round(diverted / max(total, 1) * 100, 1),
            "rules_count": len(self._rules),
            "diverts_count": len(self._diverts),
        }

    def get_recent_log(self, limit: int = 50) -> list[dict]:
        log_list = list(self._sort_log)
        return log_list[-limit:]

    def _log(self, entry: dict):
        # deque(maxlen=N) automatically discards oldest entries — O(1) bounded append
        self._sort_log.append(entry)

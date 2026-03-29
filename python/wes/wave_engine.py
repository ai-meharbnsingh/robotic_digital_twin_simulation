"""
WaveEngine — groups orders into waves for batch picking.

A Wave is a batch of orders that share zone affinity and can be dispatched
together. Rules define conditions (zone, priority range, batch size) for
auto-wave generation. Waves are released to generate tasks via TaskGenerator.

Phase 4: Wave Rule Engine.
"""

import time
import uuid
from typing import Any, Optional


class WaveEngine:
    """
    Groups pending orders into waves based on configurable rules.

    Usage:
        engine = WaveEngine(warehouse_config)
        engine.add_rule({"name": "Zone A Batch", "conditions": {"zone": "Storage"}, ...})
        waves = engine.auto_wave(pending_orders)
        tasks = engine.release_wave(wave, task_generator)
    """

    def __init__(self, warehouse_config: dict):
        self._warehouse_config = warehouse_config
        self._node_zone_map = self._build_node_zone_map(warehouse_config)
        self._rules: list[dict[str, Any]] = []

    @staticmethod
    def _build_node_zone_map(warehouse_config: dict) -> dict[str, str]:
        """Map node names to their zone names for zone affinity matching."""
        node_zone = {}
        for zone in warehouse_config.get("zones", []):
            zone_name = zone.get("name", "")
            for node_name in zone.get("nodes", []):
                node_zone[node_name] = zone_name
        return node_zone

    def get_zone_for_node(self, node_name: str) -> str:
        """Return the zone name for a given node, or 'unknown' if not mapped."""
        return self._node_zone_map.get(node_name, "unknown")

    # ── Rule management ──────────────────────────────────

    def add_rule(self, rule: dict[str, Any]) -> dict[str, Any]:
        """
        Add a wave rule. Returns the rule with generated rule_id.

        Rule schema:
            name: str
            conditions:
                zone: str | None        — zone affinity filter
                min_priority: int | None
                max_priority: int | None
                batch_size: int         — min orders to form a wave (default 3)
            action:
                max_robots: int         — max robots for this wave (default 5)
                deadline_s: float | None — seconds from release to deadline
            enabled: bool               — whether rule is active
        """
        rule_doc = {
            "rule_id": rule.get("rule_id", str(uuid.uuid4())),
            "name": rule.get("name", "Unnamed Rule"),
            "conditions": {
                "zone": rule.get("conditions", {}).get("zone"),
                "min_priority": rule.get("conditions", {}).get("min_priority"),
                "max_priority": rule.get("conditions", {}).get("max_priority"),
                "batch_size": rule.get("conditions", {}).get("batch_size", 3),
            },
            "action": {
                "max_robots": rule.get("action", {}).get("max_robots", 5),
                "deadline_s": rule.get("action", {}).get("deadline_s"),
            },
            "enabled": rule.get("enabled", True),
            "created_at": rule.get("created_at", time.time()),
        }
        self._rules.append(rule_doc)
        return rule_doc

    def get_rules(self) -> list[dict[str, Any]]:
        """Return all rules."""
        return list(self._rules)

    def set_rules(self, rules: list[dict[str, Any]]) -> None:
        """Replace all rules (used when loading from MongoDB)."""
        self._rules = list(rules)

    # ── Wave creation ────────────────────────────────────

    def create_wave(
        self,
        order_ids: list[str],
        zone_affinity: Optional[str] = None,
        max_robots: int = 5,
        deadline: Optional[float] = None,
    ) -> dict[str, Any]:
        """Create a wave manually from a list of order IDs."""
        return {
            "wave_id": str(uuid.uuid4()),
            "status": "pending",
            "order_ids": list(order_ids),
            "zone_affinity": zone_affinity,
            "max_robots": max_robots,
            "deadline": deadline,
            "created_at": time.time(),
            "released_at": None,
            "completed_at": None,
            "task_ids": [],
        }

    def auto_wave(self, pending_orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Auto-generate waves from pending orders using active rules.

        For each enabled rule, find matching orders and group them into waves.
        Orders that match multiple rules are assigned to the first matching rule.
        Unmatched orders are NOT waved (remain as individual tasks).

        Returns list of wave dicts.
        """
        assigned_order_ids: set[str] = set()
        waves: list[dict[str, Any]] = []

        for rule in self._rules:
            if not rule.get("enabled", True):
                continue

            conditions = rule.get("conditions", {})
            zone_filter = conditions.get("zone")
            min_pri = conditions.get("min_priority")
            max_pri = conditions.get("max_priority")
            batch_size = conditions.get("batch_size", 3)

            action = rule.get("action", {})
            max_robots = action.get("max_robots", 5)
            deadline_s = action.get("deadline_s")

            # Find matching orders not yet assigned
            matching = []
            for order in pending_orders:
                oid = order.get("order_id", "")
                if oid in assigned_order_ids:
                    continue

                # Zone filter
                if zone_filter:
                    source_zone = self.get_zone_for_node(order.get("source_node", ""))
                    if source_zone != zone_filter:
                        continue

                # Priority filter
                pri = order.get("priority", 0)
                if min_pri is not None and pri < min_pri:
                    continue
                if max_pri is not None and pri > max_pri:
                    continue

                matching.append(order)

            # Only create wave if we have enough orders
            if len(matching) < batch_size:
                continue

            order_ids = [o["order_id"] for o in matching]
            assigned_order_ids.update(order_ids)

            deadline = time.time() + deadline_s if deadline_s else None

            wave = self.create_wave(
                order_ids=order_ids,
                zone_affinity=zone_filter,
                max_robots=max_robots,
                deadline=deadline,
            )
            waves.append(wave)

        return waves

    # ── Wave release ─────────────────────────────────────

    def release_wave(
        self,
        wave: dict[str, Any],
        orders: list[dict[str, Any]],
        task_generator,
    ) -> dict[str, Any]:
        """
        Release a wave — generate tasks from its orders.

        Args:
            wave: Wave dict (must have status=pending)
            orders: Full order documents for the wave's order_ids
            task_generator: TaskGenerator instance

        Returns:
            Updated wave dict with status=active and task_ids populated.
        """
        if wave.get("status") != "pending":
            raise ValueError(f"Cannot release wave {wave['wave_id']}: status={wave['status']}")

        # Filter to only orders in this wave
        wave_order_ids = set(wave.get("order_ids", []))
        wave_orders = [o for o in orders if o.get("order_id") in wave_order_ids]

        # Generate tasks
        tasks = task_generator.from_orders(wave_orders)

        wave["status"] = "active"
        wave["released_at"] = time.time()
        wave["task_ids"] = [t["task_id"] for t in tasks]

        return wave, tasks

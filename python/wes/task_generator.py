"""
TaskGenerator — converts orders into executable PICK/PLACE tasks.

Each order becomes one or more tasks that the fleet manager can assign
to individual robots.
"""

import uuid
import time
from typing import Any


class TaskGenerator:
    """
    Converts orders into robot-assignable tasks.

    A pick_and_drop order becomes:
    1. PICK task at source_node
    2. DROP task at destination_node
    """

    def __init__(self):
        self._task_count = 0

    def from_order(self, order: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Convert an order into tasks.

        Args:
            order: Order dict with source_node, destination_node, etc.

        Returns:
            List of task dicts.
        """
        order_id = order.get("order_id", str(uuid.uuid4()))
        source = order.get("source_node", "")
        dest = order.get("destination_node", "")
        priority = order.get("priority", 0)
        payload = order.get("payload_kg", 0.0)
        order_type = order.get("order_type", "pick_and_drop")

        tasks = []

        if order_type == "pick_and_drop":
            # Combined pick-and-drop task
            self._task_count += 1
            tasks.append({
                "task_id": str(uuid.uuid4()),
                "task_type": "pick_and_drop",
                "status": "pending",
                "assigned_robot_id": None,
                "source_node": source,
                "destination_node": dest,
                "priority": priority,
                "payload_kg": payload,
                "order_id": order_id,
                "created_at": time.time(),
                "assigned_at": None,
                "started_at": None,
                "completed_at": None,
                "error_message": None,
            })
        else:
            # Separate PICK and DROP tasks
            self._task_count += 2
            tasks.append({
                "task_id": str(uuid.uuid4()),
                "task_type": "pick",
                "status": "pending",
                "assigned_robot_id": None,
                "source_node": source,
                "destination_node": source,
                "priority": priority,
                "payload_kg": payload,
                "order_id": order_id,
                "created_at": time.time(),
                "assigned_at": None,
                "started_at": None,
                "completed_at": None,
                "error_message": None,
            })
            tasks.append({
                "task_id": str(uuid.uuid4()),
                "task_type": "drop",
                "status": "pending",
                "assigned_robot_id": None,
                "source_node": source,
                "destination_node": dest,
                "priority": priority,
                "payload_kg": payload,
                "order_id": order_id,
                "created_at": time.time(),
                "assigned_at": None,
                "started_at": None,
                "completed_at": None,
                "error_message": None,
            })

        return tasks

    def from_orders(self, orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert multiple orders into tasks."""
        tasks = []
        for order in orders:
            tasks.extend(self.from_order(order))
        return tasks

    @property
    def task_count(self) -> int:
        return self._task_count

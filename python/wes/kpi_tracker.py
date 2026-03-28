"""
KPITracker — computes WES key performance indicators.

Metrics:
- orders_per_hour: Order arrival throughput
- pick_accuracy_pct: Successful picks / total picks
- throughput_items_per_hour: Completed tasks per hour
- avg_order_cycle_time_s: Average time from order creation to completion
"""

import time
from typing import Any


class KPITracker:
    """
    Computes warehouse execution KPIs from order and task data.
    """

    def compute(self, orders: list[dict[str, Any]], tasks: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Compute KPIs from orders and tasks.

        Args:
            orders: List of order dicts.
            tasks: List of task dicts.

        Returns:
            Dict of KPI values.
        """
        now = time.time()

        # Orders per hour
        total_orders = len(orders)
        completed_orders = sum(1 for o in orders if o.get("status") == "completed")
        pending_orders = sum(1 for o in orders if o.get("status") == "pending")

        # Order timestamps for rate calculation
        if orders:
            timestamps = [o.get("created_at", now) for o in orders]
            earliest = min(timestamps)
            time_span_h = max((now - earliest) / 3600, 1 / 3600)  # at least 1 second
            orders_per_hour = total_orders / time_span_h
        else:
            orders_per_hour = 0.0

        # Task throughput
        completed_tasks = [t for t in tasks if t.get("status") == "completed"]
        failed_tasks = [t for t in tasks if t.get("status") == "failed"]

        if tasks:
            task_timestamps = [t.get("created_at", now) for t in tasks]
            earliest_task = min(task_timestamps)
            task_span_h = max((now - earliest_task) / 3600, 1 / 3600)
            throughput = len(completed_tasks) / task_span_h
        else:
            throughput = 0.0

        # Pick accuracy
        total_picks = len(completed_tasks) + len(failed_tasks)
        pick_accuracy = (len(completed_tasks) / total_picks * 100) if total_picks > 0 else 100.0

        # Average order cycle time
        cycle_times = []
        for o in orders:
            created = o.get("created_at")
            completed_at = o.get("completed_at")
            if created and completed_at:
                cycle_times.append(completed_at - created)
        avg_cycle = sum(cycle_times) / len(cycle_times) if cycle_times else 0.0

        return {
            "orders_per_hour": round(orders_per_hour, 1),
            "pick_accuracy_pct": round(pick_accuracy, 1),
            "throughput_items_per_hour": round(throughput, 1),
            "avg_order_cycle_time_s": round(avg_cycle, 1),
            "pending_orders": pending_orders,
            "completed_orders": completed_orders,
            "total_orders": total_orders,
            "completed_tasks": len(completed_tasks),
            "failed_tasks": len(failed_tasks),
        }

"""
OrderGenerator — generates warehouse orders using a Poisson arrival process.

Produces realistic order patterns with configurable arrival rate (lambda).
Each order has a source node (pick), destination node (drop), and priority.
"""

import time
import uuid
from typing import Any

import numpy as np


class OrderGenerator:
    """
    Generates orders with Poisson-distributed inter-arrival times.
    """

    def __init__(
        self,
        pick_nodes: list[str],
        drop_nodes: list[str],
        arrival_rate: float = 2.0,
        seed: int = None,
    ):
        """
        Args:
            pick_nodes: Available pick station node names.
            drop_nodes: Available drop station node names.
            arrival_rate: Average orders per minute (lambda for Poisson).
            seed: Random seed for reproducibility.
        """
        self.pick_nodes = pick_nodes if pick_nodes else ["PICK_1"]
        self.drop_nodes = drop_nodes if drop_nodes else ["DROP_1"]
        self.arrival_rate = arrival_rate
        self._rng = np.random.RandomState(seed)
        self._order_count = 0

    def generate_one(self) -> dict[str, Any]:
        """
        Generate a single order.

        Returns:
            Order dict with id, source, destination, priority, timestamp.
        """
        self._order_count += 1
        return {
            "order_id": str(uuid.uuid4()),
            "source_node": self._rng.choice(self.pick_nodes),
            "destination_node": self._rng.choice(self.drop_nodes),
            "priority": int(self._rng.randint(0, 11)),
            "payload_kg": round(float(self._rng.uniform(0.5, 25.0)), 1),
            "created_at": time.time(),
            "status": "pending",
            "order_type": "pick_and_drop",
        }

    def generate_batch(self, count: int) -> list[dict[str, Any]]:
        """
        Generate a batch of orders.

        Args:
            count: Number of orders to generate.

        Returns:
            List of order dicts.
        """
        return [self.generate_one() for _ in range(count)]

    def generate_poisson_burst(self, duration_s: float) -> list[dict[str, Any]]:
        """
        Generate orders with Poisson inter-arrival times for a given duration.

        Args:
            duration_s: Duration in seconds.

        Returns:
            List of order dicts with staggered timestamps.
        """
        orders = []
        elapsed = 0.0
        base_time = time.time()

        while elapsed < duration_s:
            # Poisson inter-arrival: exponential distribution
            interval = float(self._rng.exponential(60.0 / self.arrival_rate))
            elapsed += interval
            if elapsed >= duration_s:
                break

            order = self.generate_one()
            order["created_at"] = base_time + elapsed
            orders.append(order)

        return orders

    @property
    def order_count(self) -> int:
        return self._order_count

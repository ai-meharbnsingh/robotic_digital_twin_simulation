"""
StorageOptimizer — slotting optimization and zone balancing.

Analyzes pick frequency and recommends:
  - Move fast-movers closer to pick stations (ABC analysis)
  - Balance inventory across storage zones
  - Identify underutilized and overcrowded locations
"""

import math
from typing import Any, Optional

from .inventory_manager import InventoryManager


class StorageOptimizer:
    """Recommends inventory slot changes based on pick frequency and distance.

    Usage:
        optimizer = StorageOptimizer(inventory, pick_nodes=["PICK_0", "PICK_1"])
        recommendations = optimizer.analyze()
    """

    def __init__(self, inventory: InventoryManager,
                 pick_nodes: Optional[list[str]] = None,
                 node_positions: Optional[dict[str, dict]] = None):
        self._inventory = inventory
        self._pick_nodes = pick_nodes or []
        self._node_positions = node_positions or {}
        self._pick_counts: dict[str, int] = {}  # sku_id → total picks

    def record_pick(self, sku_id: str):
        """Record a pick event for ABC analysis. Increments pick counter for the given SKU."""
        self._pick_counts[sku_id] = self._pick_counts.get(sku_id, 0) + 1

    def abc_analysis(self) -> dict[str, list[dict]]:
        """Classify SKUs into A/B/C categories by pick frequency.

        A = top 20% (fast movers) — should be near pick stations
        B = next 30% (moderate) — middle of warehouse
        C = bottom 50% (slow movers) — back of warehouse
        """
        if not self._pick_counts:
            return {"A": [], "B": [], "C": []}

        sorted_skus = sorted(self._pick_counts.items(), key=lambda x: -x[1])
        total = len(sorted_skus)

        a_cutoff = max(int(total * 0.2), 1)
        b_cutoff = max(int(total * 0.5), a_cutoff + 1)

        result: dict[str, list[dict]] = {"A": [], "B": [], "C": []}
        for i, (sku_id, count) in enumerate(sorted_skus):
            entry = {"sku_id": sku_id, "pick_count": count}
            if i < a_cutoff:
                result["A"].append(entry)
            elif i < b_cutoff:
                result["B"].append(entry)
            else:
                result["C"].append(entry)

        return result

    def _distance_to_pick(self, node_name: str) -> float:
        """Euclidean distance from node to nearest pick station."""
        if not self._pick_nodes or node_name not in self._node_positions:
            return 0.0

        node = self._node_positions[node_name]
        min_dist = float("inf")
        for pick in self._pick_nodes:
            if pick in self._node_positions:
                p = self._node_positions[pick]
                d = math.sqrt((node["x"] - p["x"]) ** 2 + (node["y"] - p["y"]) ** 2)
                min_dist = min(min_dist, d)
        return min_dist if min_dist != float("inf") else 0.0

    def get_recommendations(self) -> list[dict]:
        """Generate slotting recommendations.

        Identifies SKUs that are far from pick stations but frequently picked.
        Recommends moving them closer.
        """
        abc = self.abc_analysis()
        recommendations = []

        for item in abc.get("A", []):
            sku_id = item["sku_id"]
            locations = self._inventory.get_stock_for_sku(sku_id)

            for loc in locations:
                dist = self._distance_to_pick(loc["node_name"])
                if dist > 10.0:  # More than 10m from pick station
                    recommendations.append({
                        "type": "move_closer",
                        "sku_id": sku_id,
                        "current_node": loc["node_name"],
                        "distance_to_pick_m": round(dist, 1),
                        "pick_count": item["pick_count"],
                        "reason": f"A-class SKU stored {dist:.0f}m from pick station — move closer",
                    })

        return recommendations

    def get_zone_balance(self) -> dict[str, dict]:
        """Analyze inventory distribution across zones.

        Returns per-zone: total units, unique SKUs, utilization estimate.
        """
        zone_data: dict[str, dict] = {}

        for loc_dict in self._inventory.get_all_locations():
            node_info = self._node_positions.get(loc_dict["node_name"], {})
            zone = node_info.get("zone", "unknown")

            if zone not in zone_data:
                zone_data[zone] = {"total_units": 0, "unique_skus": set(), "locations": 0}

            zone_data[zone]["total_units"] += loc_dict["quantity"]
            zone_data[zone]["unique_skus"].add(loc_dict["sku_id"])
            zone_data[zone]["locations"] += 1

        # Convert sets to counts for serialization
        return {
            zone: {
                "total_units": d["total_units"],
                "unique_skus": len(d["unique_skus"]),
                "locations": d["locations"],
            }
            for zone, d in zone_data.items()
        }

    def get_stats(self) -> dict:
        abc = self.abc_analysis()
        return {
            "total_tracked_skus": len(self._pick_counts),
            "total_picks": sum(self._pick_counts.values()),
            "a_class": len(abc.get("A", [])),
            "b_class": len(abc.get("B", [])),
            "c_class": len(abc.get("C", [])),
            "recommendations": len(self.get_recommendations()),
        }

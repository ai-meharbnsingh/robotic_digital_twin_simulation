"""
InventoryManager — SKU registry, location tracking, stock levels.

Tracks what's stored where:
  - SKU catalog: product definitions (name, dimensions, weight, category, storage class)
  - Locations: which SKU at which warehouse node, quantity
  - Stock levels: current vs min/max thresholds, reorder points
  - Putaway rules: category → zone mapping (heavy→bottom, fast-moving→front)
  - Stock movements: receive, pick, adjust, transfer (auditable log)

Config-driven: loads SKU catalog from configs/wms/sku_catalog.yaml
"""

import time
import uuid
from enum import Enum
from typing import Any, Optional


class StorageClass(str, Enum):
    STANDARD = "standard"
    COLD = "cold"
    HAZMAT = "hazmat"
    FRAGILE = "fragile"
    HEAVY = "heavy"
    HIGH_VALUE = "high_value"


class MovementType(str, Enum):
    RECEIVE = "receive"
    PICK = "pick"
    ADJUST = "adjust"
    TRANSFER = "transfer"
    CYCLE_COUNT = "cycle_count"
    REPLENISH = "replenish"


class SKU:
    """Product definition."""

    def __init__(
        self,
        sku_id: str,
        name: str,
        category: str = "general",
        storage_class: StorageClass = StorageClass.STANDARD,
        weight_kg: float = 1.0,
        length_cm: float = 30.0,
        width_cm: float = 20.0,
        height_cm: float = 15.0,
        min_stock: int = 10,
        max_stock: int = 100,
        reorder_point: int = 20,
        reorder_qty: int = 50,
    ):
        self.sku_id = sku_id
        self.name = name
        self.category = category
        self.storage_class = storage_class
        self.weight_kg = weight_kg
        self.length_cm = length_cm
        self.width_cm = width_cm
        self.height_cm = height_cm
        self.min_stock = min_stock
        self.max_stock = max_stock
        self.reorder_point = reorder_point
        self.reorder_qty = reorder_qty

    def to_dict(self) -> dict:
        return {
            "sku_id": self.sku_id,
            "name": self.name,
            "category": self.category,
            "storage_class": self.storage_class.value,
            "weight_kg": self.weight_kg,
            "dimensions_cm": {
                "length": self.length_cm,
                "width": self.width_cm,
                "height": self.height_cm,
            },
            "min_stock": self.min_stock,
            "max_stock": self.max_stock,
            "reorder_point": self.reorder_point,
            "reorder_qty": self.reorder_qty,
        }


class StockLocation:
    """Inventory at a specific warehouse node."""

    def __init__(self, sku_id: str, node_name: str, quantity: int = 0):
        self.sku_id = sku_id
        self.node_name = node_name
        self.quantity = quantity
        self.last_updated = time.time()
        self.last_counted = 0.0

    def to_dict(self) -> dict:
        return {
            "sku_id": self.sku_id,
            "node_name": self.node_name,
            "quantity": self.quantity,
            "last_updated": self.last_updated,
            "last_counted": self.last_counted,
        }


class InventoryManager:
    """Manages SKU catalog, stock locations, and movements.

    Usage:
        mgr = InventoryManager()
        mgr.load_catalog(config)
        mgr.receive("SKU-001", "STOR_A_0_0", 50)
        mgr.pick("SKU-001", "STOR_A_0_0", 3)
        levels = mgr.get_stock_levels()
    """

    def __init__(self):
        self._skus: dict[str, SKU] = {}
        self._locations: dict[str, StockLocation] = {}  # key: "sku_id:node_name"
        self._movements: list[dict] = []
        self._putaway_rules: dict[str, str] = {}  # category → preferred_zone
        self._max_movements = 5000

    def load_catalog(self, config: dict):
        """Load SKU catalog from config."""
        for sku_cfg in config.get("skus", []):
            sku = SKU(
                sku_id=sku_cfg["sku_id"],
                name=sku_cfg.get("name", sku_cfg["sku_id"]),
                category=sku_cfg.get("category", "general"),
                storage_class=StorageClass(sku_cfg.get("storage_class", "standard")),
                weight_kg=sku_cfg.get("weight_kg", 1.0),
                length_cm=sku_cfg.get("length_cm", 30.0),
                width_cm=sku_cfg.get("width_cm", 20.0),
                height_cm=sku_cfg.get("height_cm", 15.0),
                min_stock=sku_cfg.get("min_stock", 10),
                max_stock=sku_cfg.get("max_stock", 100),
                reorder_point=sku_cfg.get("reorder_point", 20),
                reorder_qty=sku_cfg.get("reorder_qty", 50),
            )
            self._skus[sku.sku_id] = sku

        for rule in config.get("putaway_rules", []):
            self._putaway_rules[rule["category"]] = rule["preferred_zone"]

    def get_sku(self, sku_id: str) -> Optional[dict]:
        sku = self._skus.get(sku_id)
        return sku.to_dict() if sku else None

    def get_all_skus(self) -> list[dict]:
        """Return all SKUs in the catalog as dicts."""
        return [s.to_dict() for s in self._skus.values()]

    # ── Stock Operations ────────────────────────────────

    def receive(self, sku_id: str, node_name: str, quantity: int) -> dict:
        """Receive inventory (inbound putaway)."""
        if sku_id not in self._skus:
            return {"ok": False, "error": f"SKU '{sku_id}' not in catalog"}
        if quantity <= 0:
            return {"ok": False, "error": "quantity must be positive"}

        key = f"{sku_id}:{node_name}"
        if key not in self._locations:
            self._locations[key] = StockLocation(sku_id, node_name, 0)

        loc = self._locations[key]
        loc.quantity += quantity
        loc.last_updated = time.time()

        self._log_movement(MovementType.RECEIVE, sku_id, node_name, quantity)
        return {"ok": True, "sku_id": sku_id, "node": node_name,
                "new_quantity": loc.quantity}

    def pick(self, sku_id: str, node_name: str, quantity: int) -> dict:
        """Pick inventory (outbound)."""
        if quantity <= 0:
            return {"ok": False, "error": "quantity must be positive"}

        key = f"{sku_id}:{node_name}"
        loc = self._locations.get(key)
        if loc is None or loc.quantity < quantity:
            available = loc.quantity if loc else 0
            return {"ok": False, "error": f"insufficient stock (have={available}, need={quantity})"}

        loc.quantity -= quantity
        loc.last_updated = time.time()

        self._log_movement(MovementType.PICK, sku_id, node_name, -quantity)
        return {"ok": True, "sku_id": sku_id, "node": node_name,
                "picked": quantity, "remaining": loc.quantity}

    def adjust(self, sku_id: str, node_name: str, new_quantity: int, reason: str = "") -> dict:
        """Adjust inventory (cycle count correction)."""
        if new_quantity < 0:
            return {"ok": False, "error": "quantity cannot be negative"}

        key = f"{sku_id}:{node_name}"
        if key not in self._locations:
            self._locations[key] = StockLocation(sku_id, node_name, 0)

        loc = self._locations[key]
        old_qty = loc.quantity
        delta = new_quantity - old_qty
        loc.quantity = new_quantity
        loc.last_updated = time.time()
        loc.last_counted = time.time()

        self._log_movement(MovementType.ADJUST, sku_id, node_name, delta,
                           {"reason": reason, "old_qty": old_qty})
        return {"ok": True, "sku_id": sku_id, "node": node_name,
                "old_quantity": old_qty, "new_quantity": new_quantity, "delta": delta}

    def transfer(self, sku_id: str, from_node: str, to_node: str, quantity: int) -> dict:
        """Transfer inventory between locations."""
        if quantity <= 0:
            return {"ok": False, "error": "quantity must be positive"}

        from_key = f"{sku_id}:{from_node}"
        from_loc = self._locations.get(from_key)
        if from_loc is None or from_loc.quantity < quantity:
            available = from_loc.quantity if from_loc else 0
            return {"ok": False, "error": f"insufficient stock at source (have={available})"}

        to_key = f"{sku_id}:{to_node}"
        if to_key not in self._locations:
            self._locations[to_key] = StockLocation(sku_id, to_node, 0)

        # Atomic: deduct then add
        from_loc.quantity -= quantity
        from_loc.last_updated = time.time()
        self._locations[to_key].quantity += quantity
        self._locations[to_key].last_updated = time.time()

        self._log_movement(MovementType.TRANSFER, sku_id, from_node, -quantity,
                           {"to_node": to_node})
        self._log_movement(MovementType.TRANSFER, sku_id, to_node, quantity,
                           {"from_node": from_node})
        return {"ok": True, "sku_id": sku_id, "from": from_node, "to": to_node,
                "quantity": quantity}

    # ── Stock Queries ───────────────────────────────────

    def get_all_locations(self) -> list[dict]:
        """All stock locations with quantity > 0."""
        return [loc.to_dict() for loc in self._locations.values() if loc.quantity > 0]

    def get_stock_at_node(self, node_name: str) -> list[dict]:
        """All SKUs at a given node."""
        return [loc.to_dict() for loc in self._locations.values()
                if loc.node_name == node_name and loc.quantity > 0]

    def get_stock_for_sku(self, sku_id: str) -> list[dict]:
        """All locations holding a given SKU."""
        return [loc.to_dict() for loc in self._locations.values()
                if loc.sku_id == sku_id and loc.quantity > 0]

    def get_total_stock(self, sku_id: str) -> int:
        """Total quantity of a SKU across all locations."""
        return sum(loc.quantity for loc in self._locations.values()
                   if loc.sku_id == sku_id)

    def get_stock_levels(self) -> list[dict]:
        """Stock levels for all SKUs with min/max/reorder status."""
        levels = []
        for sku in self._skus.values():
            total = self.get_total_stock(sku.sku_id)
            locations = self.get_stock_for_sku(sku.sku_id)
            levels.append({
                "sku_id": sku.sku_id,
                "name": sku.name,
                "total_stock": total,
                "min_stock": sku.min_stock,
                "max_stock": sku.max_stock,
                "reorder_point": sku.reorder_point,
                "below_reorder": total < sku.reorder_point,
                "below_min": total < sku.min_stock,
                "above_max": total > sku.max_stock,
                "locations": len(locations),
                "status": "critical" if total < sku.min_stock
                          else "low" if total < sku.reorder_point
                          else "overstocked" if total > sku.max_stock
                          else "ok",
            })
        return levels

    def get_items_below_reorder(self) -> list[dict]:
        """SKUs below reorder point — need replenishment."""
        return [l for l in self.get_stock_levels() if l["below_reorder"]]

    # ── Putaway ─────────────────────────────────────────

    def get_putaway_zone(self, sku_id: str) -> Optional[str]:
        """Determine preferred zone for a SKU based on category rules."""
        sku = self._skus.get(sku_id)
        if sku is None:
            return None
        return self._putaway_rules.get(sku.category)

    def get_putaway_rules(self) -> dict[str, str]:
        """Return all putaway rules mapping category to preferred zone."""
        return dict(self._putaway_rules)

    # ── Cycle Count ─────────────────────────────────────

    def cycle_count(self, node_name: str, counts: dict[str, int]) -> dict:
        """Perform cycle count at a node.

        Args:
            node_name: Node to count.
            counts: {sku_id: actual_quantity} from physical count.

        Returns:
            Discrepancies found.
        """
        discrepancies = []
        for sku_id, actual_qty in counts.items():
            key = f"{sku_id}:{node_name}"
            expected = self._locations[key].quantity if key in self._locations else 0

            if actual_qty != expected:
                discrepancies.append({
                    "sku_id": sku_id,
                    "node": node_name,
                    "expected": expected,
                    "actual": actual_qty,
                    "delta": actual_qty - expected,
                })
                # Auto-adjust
                self.adjust(sku_id, node_name, actual_qty, reason="cycle_count")

        return {
            "ok": True,
            "node": node_name,
            "items_counted": len(counts),
            "discrepancies": len(discrepancies),
            "details": discrepancies,
        }

    # ── Movement Log ────────────────────────────────────

    def get_movements(self, limit: int = 50, sku_id: Optional[str] = None) -> list[dict]:
        """Get recent stock movements, optionally filtered by SKU."""
        filtered = self._movements
        if sku_id:
            filtered = [m for m in filtered if m["sku_id"] == sku_id]
        return filtered[-limit:]

    def _log_movement(self, movement_type: MovementType, sku_id: str,
                      node_name: str, quantity: int, details: Optional[dict] = None):
        entry = {
            "movement_id": str(uuid.uuid4())[:12],
            "type": movement_type.value,
            "sku_id": sku_id,
            "node_name": node_name,
            "quantity": quantity,
            "timestamp": time.time(),
            "details": details or {},
        }
        self._movements.append(entry)
        if len(self._movements) > self._max_movements:
            self._movements = self._movements[-self._max_movements:]

    # ── Stats ───────────────────────────────────────────

    def get_stats(self) -> dict:
        total_skus = len(self._skus)
        total_locations = sum(1 for l in self._locations.values() if l.quantity > 0)
        total_units = sum(l.quantity for l in self._locations.values())
        levels = self.get_stock_levels()
        below_reorder = sum(1 for l in levels if l["below_reorder"])
        below_min = sum(1 for l in levels if l["below_min"])
        above_max = sum(1 for l in levels if l["above_max"])

        return {
            "total_skus": total_skus,
            "active_locations": total_locations,
            "total_units": total_units,
            "below_reorder": below_reorder,
            "below_min": below_min,
            "above_max": above_max,
            "total_movements": len(self._movements),
        }

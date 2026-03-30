"""
LayoutGenerator — automated warehouse layout utilities.

Provides:
  auto_generate_edges  — connect nearby nodes within max_distance
  auto_detect_zones    — cluster nodes into zones by position + type
  generate_from_template — scale a template warehouse up/down
  validate_connectivity — BFS reachability check
  suggest_charge_stations — recommend charge station count + placement
  calculate_metrics     — aisle count, total area, pick-to-ship distance

Called from: app/routes/designer.py (Phase 15 endpoints).
"""

import math
from collections import defaultdict, deque
from typing import Any


class LayoutGenerator:
    """Warehouse layout generation and analysis utilities."""

    # ── auto_generate_edges ──────────────────────────────────────

    @staticmethod
    def auto_generate_edges(
        nodes: list[dict], max_distance: float
    ) -> list[dict]:
        """
        Auto-connect nearby nodes with edges.

        For every pair of nodes whose Euclidean distance is <= max_distance,
        creates a bidirectional edge (stored once, from lower index to higher).

        Args:
            nodes: List of node dicts, each with 'name', 'x', 'y'.
            max_distance: Maximum Euclidean distance for auto-connection.

        Returns:
            List of edge dicts [{"from": ..., "to": ...}, ...].
        """
        if max_distance <= 0:
            return []

        edges: list[dict] = []
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                dx = float(nodes[i]["x"]) - float(nodes[j]["x"])
                dy = float(nodes[i]["y"]) - float(nodes[j]["y"])
                dist = math.sqrt(dx * dx + dy * dy)
                if dist <= max_distance:
                    edges.append({
                        "from": nodes[i]["name"],
                        "to": nodes[j]["name"],
                    })
        return edges

    # ── auto_detect_zones ────────────────────────────────────────

    @staticmethod
    def auto_detect_zones(nodes: list[dict]) -> list[dict]:
        """
        Cluster nodes into zones by position + type.

        Algorithm:
        1. Group nodes by type.
        2. Within each type group, cluster spatially using simple grid-cell bucketing.
           Nodes sharing the same 10x10 grid cell are in the same cluster.
        3. Each cluster becomes a zone.

        Args:
            nodes: List of node dicts with 'name', 'x', 'y', 'type'.

        Returns:
            List of zone dicts [{"name": ..., "type": ..., "nodes": [...]}, ...].
        """
        if not nodes:
            return []

        CELL_SIZE = 10.0  # grid cell size for spatial clustering

        # Group by type
        type_groups: dict[str, list[dict]] = defaultdict(list)
        for node in nodes:
            node_type = node.get("type", "unknown")
            type_groups[node_type].append(node)

        zones: list[dict] = []
        for node_type, group in sorted(type_groups.items()):
            # Cluster by grid cell within each type
            cells: dict[tuple[int, int], list[str]] = defaultdict(list)
            for node in group:
                cx = int(float(node["x"]) // CELL_SIZE)
                cy = int(float(node["y"]) // CELL_SIZE)
                cells[(cx, cy)].append(node["name"])

            for cell_idx, (cell, node_names) in enumerate(sorted(cells.items())):
                zone_name = f"{node_type.capitalize()}_Zone_{cell_idx + 1}"
                zones.append({
                    "name": zone_name,
                    "type": node_type,
                    "nodes": sorted(node_names),
                })

        return zones

    # ── generate_from_template ───────────────────────────────────

    @staticmethod
    def generate_from_template(
        template: dict, scale_factor: float
    ) -> dict:
        """
        Scale a template warehouse up/down.

        Multiplies all node x/y coordinates and grid_spacing_m by scale_factor.
        Node names, types, edges, and zones are preserved.

        Args:
            template: Full warehouse config dict.
            scale_factor: Multiplier (>1 = bigger, <1 = smaller). Must be > 0.

        Returns:
            New config dict with scaled coordinates.

        Raises:
            ValueError: If scale_factor <= 0.
        """
        if scale_factor <= 0:
            raise ValueError(f"scale_factor must be > 0, got {scale_factor}")

        result = dict(template)  # shallow copy top level
        result["name"] = f"{template.get('name', 'Unnamed')} (x{scale_factor})"

        # Scale nodes
        scaled_nodes = []
        for node in template.get("nodes", []):
            scaled_node = dict(node)
            scaled_node["x"] = round(float(node["x"]) * scale_factor, 3)
            scaled_node["y"] = round(float(node["y"]) * scale_factor, 3)
            scaled_nodes.append(scaled_node)
        result["nodes"] = scaled_nodes

        # Preserve edges as-is (they reference node names, not positions)
        result["edges"] = list(template.get("edges", []))

        # Preserve zones as-is
        result["zones"] = list(template.get("zones", []))

        # Scale grid spacing
        if "grid_spacing_m" in template:
            result["grid_spacing_m"] = round(
                float(template["grid_spacing_m"]) * scale_factor, 3
            )

        return result

    # ── validate_connectivity ────────────────────────────────────

    @staticmethod
    def validate_connectivity(
        nodes: list[dict], edges: list[dict]
    ) -> dict:
        """
        Check all nodes reachable via BFS.

        Args:
            nodes: List of node dicts with 'name'.
            edges: List of edge dicts with 'from' and 'to'.

        Returns:
            {
                "connected": bool,
                "total_nodes": int,
                "reachable_nodes": int,
                "unreachable": [list of unreachable node names],
                "components": int  (number of connected components),
            }
        """
        if not nodes:
            return {
                "connected": True,
                "total_nodes": 0,
                "reachable_nodes": 0,
                "unreachable": [],
                "components": 0,
            }

        node_names = {n["name"] for n in nodes}

        # Build adjacency (undirected)
        adjacency: dict[str, set[str]] = defaultdict(set)
        for edge in edges:
            f, t = edge.get("from", ""), edge.get("to", "")
            if f in node_names and t in node_names:
                adjacency[f].add(t)
                adjacency[t].add(f)

        # BFS from first node to find reachable set
        start = next(iter(node_names))
        reachable_from_start: set[str] = set()
        queue: deque[str] = deque([start])
        reachable_from_start.add(start)
        while queue:
            current = queue.popleft()
            for neighbor in adjacency.get(current, set()):
                if neighbor not in reachable_from_start:
                    reachable_from_start.add(neighbor)
                    queue.append(neighbor)

        unreachable = sorted(node_names - reachable_from_start)

        # Count total connected components
        all_visited: set[str] = set()
        components = 0
        remaining = set(node_names)
        while remaining:
            components += 1
            seed = next(iter(remaining))
            comp_queue: deque[str] = deque([seed])
            all_visited.add(seed)
            remaining.discard(seed)
            while comp_queue:
                current = comp_queue.popleft()
                for neighbor in adjacency.get(current, set()):
                    if neighbor not in all_visited:
                        all_visited.add(neighbor)
                        remaining.discard(neighbor)
                        comp_queue.append(neighbor)

        return {
            "connected": components <= 1,
            "total_nodes": len(node_names),
            "reachable_nodes": len(reachable_from_start),
            "unreachable": unreachable,
            "components": components,
        }

    # ── suggest_charge_stations ──────────────────────────────────

    @staticmethod
    def suggest_charge_stations(
        nodes: list[dict], fleet_size: int
    ) -> dict:
        """
        Recommend charge station count and placement.

        Heuristic:
        - 1 charge station per 3 robots (minimum 1, maximum = node count).
        - Prefer placing charge stations near the perimeter (low x or y).
        - Prioritize nodes of type 'aisle' that are at edges of the layout.

        Args:
            nodes: List of node dicts with 'name', 'x', 'y', 'type'.
            fleet_size: Number of robots.

        Returns:
            {
                "recommended_count": int,
                "suggested_nodes": [node names],
                "fleet_size": int,
                "ratio": str (e.g. "1:3"),
            }
        """
        if fleet_size <= 0 or not nodes:
            return {
                "recommended_count": 0,
                "suggested_nodes": [],
                "fleet_size": fleet_size,
                "ratio": "N/A",
            }

        # 1 charger per 3 robots
        recommended = max(1, math.ceil(fleet_size / 3))
        recommended = min(recommended, len(nodes))

        # Find perimeter candidates: prefer low x or y (dock area)
        # Score: lower sum of (x + y) = closer to origin = better dock position
        candidates = []
        for node in nodes:
            score = float(node["x"]) + float(node["y"])
            candidates.append((score, node["name"]))
        candidates.sort()

        suggested = [name for _, name in candidates[:recommended]]

        return {
            "recommended_count": recommended,
            "suggested_nodes": suggested,
            "fleet_size": fleet_size,
            "ratio": f"1:{min(fleet_size, 3)}",
        }

    # ── calculate_metrics ────────────────────────────────────────

    @staticmethod
    def calculate_metrics(config: dict) -> dict:
        """
        Calculate warehouse layout metrics.

        Computes:
        - aisle_count: number of nodes with type 'aisle'
        - shelf_count: number of nodes with type 'shelf'
        - total_nodes: total node count
        - total_edges: total edge count
        - total_area_m2: bounding box area (width * height)
        - pick_to_ship_distance_m: min Euclidean distance from any pick node to any drop node
        - charge_station_count: number of nodes with type 'charge'
        - zone_count: number of zones defined

        Args:
            config: Full warehouse config dict.

        Returns:
            Dict of computed metrics.
        """
        nodes = config.get("nodes", [])
        edges = config.get("edges", [])
        zones = config.get("zones", [])

        # Type counts
        type_counts: dict[str, int] = defaultdict(int)
        for node in nodes:
            type_counts[node.get("type", "unknown")] += 1

        # Bounding box area
        if nodes:
            xs = [float(n["x"]) for n in nodes]
            ys = [float(n["y"]) for n in nodes]
            width = max(xs) - min(xs)
            height = max(ys) - min(ys)
            total_area = round(width * height, 2)
        else:
            total_area = 0.0

        # Pick-to-ship distance (min distance from any pick to any drop)
        pick_nodes = [n for n in nodes if n.get("type") == "pick"]
        drop_nodes = [n for n in nodes if n.get("type") == "drop"]

        if pick_nodes and drop_nodes:
            min_dist = float("inf")
            for p in pick_nodes:
                for d in drop_nodes:
                    dx = float(p["x"]) - float(d["x"])
                    dy = float(p["y"]) - float(d["y"])
                    dist = math.sqrt(dx * dx + dy * dy)
                    if dist < min_dist:
                        min_dist = dist
            pick_to_ship = round(min_dist, 2)
        else:
            pick_to_ship = 0.0

        return {
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "aisle_count": type_counts.get("aisle", 0),
            "shelf_count": type_counts.get("shelf", 0),
            "charge_station_count": type_counts.get("charge", 0),
            "pick_count": type_counts.get("pick", 0),
            "drop_count": type_counts.get("drop", 0),
            "total_area_m2": total_area,
            "pick_to_ship_distance_m": pick_to_ship,
            "zone_count": len(zones),
        }

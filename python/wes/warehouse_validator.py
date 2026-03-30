"""
Warehouse configuration validator.

Validates warehouse JSON configs for structural correctness:
  - Node field completeness (name, x, y, type)
  - Edge reference validity
  - Graph connectivity (BFS)
  - Required node types (charge, pick, drop)
  - No duplicate names
  - Overlapping position warnings

Also provides auto_edges() for generating edges between nearby nodes.

Called from: app/routes/designer.py (validate + export endpoints).
"""

import math
from collections import defaultdict, deque


class WarehouseValidator:
    """Static methods for warehouse config validation."""

    REQUIRED_NODE_FIELDS = {"name", "x", "y", "type"}

    @staticmethod
    def validate(config: dict) -> dict:
        """
        Validate warehouse config.

        Checks:
        1. All nodes have name, x, y, type
        2. All edges reference valid nodes
        3. Graph is connected (BFS from any node reaches all)
        4. At least 1 charge node exists
        5. At least 1 pick node and 1 drop node exist
        6. No duplicate node names
        7. No overlapping positions (warning)

        Returns:
            {valid: bool, errors: [...], warnings: [...]}
        """
        errors: list[str] = []
        warnings: list[str] = []

        nodes = config.get("nodes", [])
        edges = config.get("edges", [])

        if not nodes:
            errors.append("No nodes defined in config")
            return {"valid": False, "errors": errors, "warnings": warnings}

        # 1. Check required fields on every node
        for i, node in enumerate(nodes):
            missing = WarehouseValidator.REQUIRED_NODE_FIELDS - set(node.keys())
            if missing:
                errors.append(
                    f"Node at index {i} missing required fields: {', '.join(sorted(missing))}"
                )

        # If nodes have structural problems, bail early
        if errors:
            return {"valid": False, "errors": errors, "warnings": warnings}

        # Build name set and check for duplicates
        node_names: set[str] = set()
        for node in nodes:
            name = node["name"]
            if name in node_names:
                errors.append(f"Duplicate node name: {name}")
            node_names.add(name)

        # 6. (already checked above)

        # 7. Check overlapping positions (warning only)
        positions: dict[tuple[float, float], list[str]] = defaultdict(list)
        for node in nodes:
            pos = (float(node["x"]), float(node["y"]))
            positions[pos].append(node["name"])
        for pos, names in positions.items():
            if len(names) > 1:
                warnings.append(
                    f"Overlapping position ({pos[0]}, {pos[1]}): {', '.join(names)}"
                )

        # 2. Check edge references
        for edge in edges:
            from_node = edge.get("from", "")
            to_node = edge.get("to", "")
            if from_node not in node_names:
                errors.append(f"Edge references nonexistent node: {from_node}")
            if to_node not in node_names:
                errors.append(f"Edge references nonexistent node: {to_node}")

        # If edge reference errors, skip connectivity check
        if errors:
            return {"valid": False, "errors": errors, "warnings": warnings}

        # 3. Graph connectivity (BFS, undirected)
        adjacency: dict[str, set[str]] = defaultdict(set)
        for edge in edges:
            adjacency[edge["from"]].add(edge["to"])
            adjacency[edge["to"]].add(edge["from"])

        if node_names:
            start = next(iter(node_names))
            visited: set[str] = set()
            queue: deque[str] = deque([start])
            visited.add(start)
            while queue:
                current = queue.popleft()
                for neighbor in adjacency.get(current, set()):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)

            unreachable = node_names - visited
            if unreachable:
                errors.append(
                    f"Graph is not connected. Unreachable nodes: {', '.join(sorted(unreachable))}"
                )

        # 4. At least 1 charge node
        type_counts: dict[str, int] = defaultdict(int)
        for node in nodes:
            type_counts[node["type"]] += 1

        if type_counts.get("charge", 0) == 0:
            errors.append("No charge node found. At least 1 charge node is required.")

        # 5. At least 1 pick and 1 drop
        if type_counts.get("pick", 0) == 0:
            errors.append("No pick node found. At least 1 pick node is required.")
        if type_counts.get("drop", 0) == 0:
            errors.append("No drop node found. At least 1 drop node is required.")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    @staticmethod
    def auto_edges(nodes: list[dict], spacing: float) -> list[dict]:
        """
        Generate edges between nodes within spacing distance.

        Uses Euclidean distance. Produces one edge per pair (no duplicates).
        Edges go from lower-index node to higher-index node.

        Args:
            nodes: List of node dicts with x, y fields.
            spacing: Maximum distance for auto-connection.

        Returns:
            List of edge dicts {from, to}.
        """
        edges: list[dict] = []
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                dx = float(nodes[i]["x"]) - float(nodes[j]["x"])
                dy = float(nodes[i]["y"]) - float(nodes[j]["y"])
                dist = math.sqrt(dx * dx + dy * dy)
                if dist <= spacing:
                    edges.append({
                        "from": nodes[i]["name"],
                        "to": nodes[j]["name"],
                    })
        return edges

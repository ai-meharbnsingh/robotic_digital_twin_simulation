"""
Map endpoints.
GET /api/map — full map (nodes + edges + zones)
GET /api/map/nodes — list nodes
GET /api/map/path — compute path between two nodes (A* from MongoDB)
GET /api/map/zones — list zones
"""

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/map", tags=["map"])


def _get_warehouse_config() -> dict:
    from app.main import app_state
    return app_state.get("warehouse_config") or {}


def _get_db():
    from app.main import app_state
    return app_state.get("mongo_db")


@router.get("")
async def get_map():
    """Return the full warehouse map."""
    wh = _get_warehouse_config()
    return {
        "name": wh.get("name", ""),
        "description": wh.get("description", ""),
        "grid_spacing_m": wh.get("grid_spacing_m", 0),
        "nodes": wh.get("nodes", []),
        "edges": wh.get("edges", []),
        "zones": wh.get("zones", []),
    }


@router.get("/nodes")
async def list_nodes():
    """Return all map nodes."""
    wh = _get_warehouse_config()
    return wh.get("nodes", [])


@router.get("/path")
async def get_path(
    start: str = Query(..., description="Start node name"),
    end: str = Query(..., description="End node name"),
):
    """
    Compute A* path between two nodes.
    Uses the warehouse config adjacency graph.
    """
    wh = _get_warehouse_config()
    nodes = {n["name"]: n for n in wh.get("nodes", [])}
    edges = wh.get("edges", [])

    if start not in nodes:
        return {"error": f"Start node '{start}' not found", "path": [], "distance": 0}
    if end not in nodes:
        return {"error": f"End node '{end}' not found", "path": [], "distance": 0}

    # Build adjacency list
    adj: dict[str, list[str]] = {}
    for e in edges:
        f, t = e.get("from", e.get("from_node", "")), e.get("to", e.get("to_node", ""))
        adj.setdefault(f, []).append(t)
        if e.get("bidirectional", True):
            adj.setdefault(t, []).append(f)

    # Simple A* with Euclidean heuristic
    import heapq
    import math

    def heuristic(a: str, b: str) -> float:
        na, nb = nodes[a], nodes[b]
        return math.sqrt((na["x"] - nb["x"]) ** 2 + (na["y"] - nb["y"]) ** 2)

    open_set = [(0.0, start)]
    came_from: dict[str, str] = {}
    g_score: dict[str, float] = {start: 0.0}

    while open_set:
        _, current = heapq.heappop(open_set)
        if current == end:
            # Reconstruct path
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()
            return {
                "path": path,
                "distance": round(g_score[end], 2),
                "hops": len(path) - 1,
            }

        for neighbor in adj.get(current, []):
            cost = heuristic(current, neighbor)
            tentative = g_score[current] + cost
            if tentative < g_score.get(neighbor, float("inf")):
                came_from[neighbor] = current
                g_score[neighbor] = tentative
                heapq.heappush(open_set, (tentative + heuristic(neighbor, end), neighbor))

    return {"path": [], "distance": 0, "hops": 0, "error": "No path found"}


@router.get("/zones")
async def list_zones():
    """Return all map zones."""
    wh = _get_warehouse_config()
    return wh.get("zones", [])

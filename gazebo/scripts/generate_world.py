#!/usr/bin/env python3
"""
Generate Gazebo Fortress SDF world from warehouse JSON config.

Reads the same warehouse JSON used by C++ GraphMap and generates a complete
Gazebo Fortress (gz-sim7) SDF world file with:
  - Ground plane sized to warehouse bounds
  - Perimeter walls
  - Shelf models along edges forming aisles
  - Charging station at "charge" type nodes
  - Pick/drop station markers
  - Floor barcode grid at 0.8m intervals
  - Node position markers (colored spheres)

Usage:
  python3 gazebo/scripts/generate_world.py configs/warehouses/simple_grid.json
  python3 gazebo/scripts/generate_world.py configs/warehouses/botvalley.json

Output: gazebo/worlds/{warehouse_name}.sdf
"""

import json
import math
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.dom import minidom


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _indent_xml(elem: ET.Element) -> str:
    """Pretty-print an ElementTree element as a string."""
    rough = ET.tostring(elem, encoding="unicode")
    parsed = minidom.parseString(rough)
    return parsed.toprettyxml(indent="  ", encoding=None)


def _safe_name(name: str) -> str:
    """Sanitise a node name for use as an SDF model name."""
    return name.replace("|", "_").replace(" ", "_")


# ---------------------------------------------------------------------------
# Node extraction (handles both simple_grid and botvalley formats)
# ---------------------------------------------------------------------------

class WarehouseNode:
    """Unified representation of a warehouse node."""

    def __init__(self, name: str, x: float, y: float, z: float, node_type: str):
        self.name = name
        self.x = x
        self.y = y
        self.z = z
        self.node_type = node_type


def _load_nodes(data: dict) -> list[WarehouseNode]:
    """Extract nodes from warehouse JSON — supports both formats."""
    nodes: list[WarehouseNode] = []
    for n in data.get("nodes", []):
        name = n["name"]
        # BotValley format: pose.position.{x,y,z}
        if "pose" in n:
            pos = n["pose"]["position"]
            x, y, z = pos["x"], pos["y"], pos.get("z", 0.0)
        # Simple grid format: top-level x, y (z defaults to 0)
        else:
            x = n["x"]
            y = n["y"]
            z = n.get("z", 0.0)
        node_type = n.get("type", "none")
        nodes.append(WarehouseNode(name, x, y, z, node_type))
    return nodes


def _compute_bounds(nodes: list[WarehouseNode], margin: float = 2.0):
    """Return (min_x, min_y, max_x, max_y) with margin."""
    xs = [n.x for n in nodes]
    ys = [n.y for n in nodes]
    return (
        min(xs) - margin,
        min(ys) - margin,
        max(xs) + margin,
        max(ys) + margin,
    )


# ---------------------------------------------------------------------------
# SDF element builders
# ---------------------------------------------------------------------------

def _add_sub(parent: ET.Element, tag: str, text: str | None = None, **attribs) -> ET.Element:
    """Add a sub-element with optional text and attributes."""
    elem = ET.SubElement(parent, tag, **attribs)
    if text is not None:
        elem.text = str(text)
    return elem


def _pose_str(x: float, y: float, z: float, roll: float = 0, pitch: float = 0, yaw: float = 0) -> str:
    return f"{x} {y} {z} {roll} {pitch} {yaw}"


def _build_box_visual(parent: ET.Element, name: str, sx: float, sy: float, sz: float,
                       r: float, g: float, b: float, a: float = 1.0):
    """Add visual + collision box geometry to a link."""
    for kind in ("visual", "collision"):
        elem = _add_sub(parent, kind, name=name if kind == "visual" else f"{name}_collision")
        geom = _add_sub(elem, "geometry")
        box = _add_sub(geom, "box")
        _add_sub(box, "size", f"{sx} {sy} {sz}")
        if kind == "visual":
            mat = _add_sub(elem, "material")
            _add_sub(mat, "ambient", f"{r} {g} {b} {a}")
            _add_sub(mat, "diffuse", f"{r} {g} {b} {a}")


def _build_sphere_visual(parent: ET.Element, name: str, radius: float,
                          r: float, g: float, b: float, a: float = 1.0):
    """Add a small sphere visual to a link (no collision — marker only)."""
    vis = _add_sub(parent, "visual", name=name)
    geom = _add_sub(vis, "geometry")
    sphere = _add_sub(geom, "sphere")
    _add_sub(sphere, "radius", str(radius))
    mat = _add_sub(vis, "material")
    _add_sub(mat, "ambient", f"{r} {g} {b} {a}")
    _add_sub(mat, "diffuse", f"{r} {g} {b} {a}")


def _build_cylinder_visual(parent: ET.Element, name: str, radius: float, length: float,
                            r: float, g: float, b: float, a: float = 1.0):
    """Add a cylinder visual + collision to a link."""
    for kind in ("visual", "collision"):
        elem = _add_sub(parent, kind, name=name if kind == "visual" else f"{name}_collision")
        geom = _add_sub(elem, "geometry")
        cyl = _add_sub(geom, "cylinder")
        _add_sub(cyl, "radius", str(radius))
        _add_sub(cyl, "length", str(length))
        if kind == "visual":
            mat = _add_sub(elem, "material")
            _add_sub(mat, "ambient", f"{r} {g} {b} {a}")
            _add_sub(mat, "diffuse", f"{r} {g} {b} {a}")


# ---------------------------------------------------------------------------
# World construction
# ---------------------------------------------------------------------------

# Color palette for node markers
NODE_COLORS = {
    "charge":  (0.0, 0.8, 0.0),   # green
    "pick":    (0.0, 0.4, 1.0),   # blue
    "drop":    (1.0, 0.4, 0.0),   # orange
    "hub":     (1.0, 1.0, 0.0),   # yellow
    "shelf":   (0.6, 0.3, 0.0),   # brown
    "aisle":   (0.7, 0.7, 0.7),   # grey
    "predock": (0.0, 0.6, 0.4),   # teal
    "none":    (0.5, 0.5, 0.5),   # grey
}

SHELF_HEIGHT = 1.2       # metres
SHELF_DEPTH = 0.4        # metres
WALL_HEIGHT = 2.5        # metres
WALL_THICKNESS = 0.15    # metres
BARCODE_INTERVAL = 0.8   # metres
BARCODE_SIZE = 0.06      # metres (side of square)
NODE_MARKER_RADIUS = 0.08
NODE_MARKER_HEIGHT = 0.01  # just above ground
STATION_HEIGHT = 0.05
STATION_RADIUS = 0.3


def _build_ground_plane(world: ET.Element, min_x: float, min_y: float,
                         max_x: float, max_y: float):
    """Add a ground plane sized to warehouse bounds."""
    cx = (min_x + max_x) / 2
    cy = (min_y + max_y) / 2
    sx = max_x - min_x
    sy = max_y - min_y

    model = _add_sub(world, "model", name="ground_plane")
    _add_sub(model, "static", "true")
    _add_sub(model, "pose", _pose_str(cx, cy, 0))
    link = _add_sub(model, "link", name="ground_link")
    _build_box_visual(link, "ground_visual", sx, sy, 0.01, 0.85, 0.85, 0.85)

    # Collision for the ground
    col = _add_sub(link, "collision", name="ground_collision")
    geom = _add_sub(col, "geometry")
    plane = _add_sub(geom, "plane")
    _add_sub(plane, "normal", "0 0 1")
    _add_sub(plane, "size", f"{sx} {sy}")


def _build_perimeter_walls(world: ET.Element, min_x: float, min_y: float,
                            max_x: float, max_y: float):
    """Four walls around the warehouse perimeter."""
    cx = (min_x + max_x) / 2
    cy = (min_y + max_y) / 2
    sx = max_x - min_x
    sy = max_y - min_y

    walls = [
        # name, x, y, size_x, size_y
        ("wall_north", cx, max_y, sx + WALL_THICKNESS, WALL_THICKNESS),
        ("wall_south", cx, min_y, sx + WALL_THICKNESS, WALL_THICKNESS),
        ("wall_east",  max_x, cy, WALL_THICKNESS, sy + WALL_THICKNESS),
        ("wall_west",  min_x, cy, WALL_THICKNESS, sy + WALL_THICKNESS),
    ]
    for wname, wx, wy, wsx, wsy in walls:
        model = _add_sub(world, "model", name=wname)
        _add_sub(model, "static", "true")
        _add_sub(model, "pose", _pose_str(wx, wy, WALL_HEIGHT / 2))
        link = _add_sub(model, "link", name=f"{wname}_link")
        _build_box_visual(link, f"{wname}_visual", wsx, wsy, WALL_HEIGHT,
                          0.75, 0.75, 0.75)


def _build_shelves(world: ET.Element, nodes: list[WarehouseNode], data: dict):
    """Place shelf models at 'shelf' type nodes.

    For simple_grid: shelf nodes get a shelf box.
    For botvalley: no explicit shelf nodes, so we skip (shelves are inferred
    from zone boxes if present).
    """
    shelf_nodes = [n for n in nodes if n.node_type == "shelf"]

    for i, sn in enumerate(shelf_nodes):
        sname = f"shelf_{_safe_name(sn.name)}"
        model = _add_sub(world, "model", name=sname)
        _add_sub(model, "static", "true")
        _add_sub(model, "pose", _pose_str(sn.x, sn.y, SHELF_HEIGHT / 2))
        link = _add_sub(model, "link", name=f"{sname}_link")
        # Shelf box sits above ground, same XY as node
        _build_box_visual(link, f"{sname}_visual",
                          SHELF_DEPTH, SHELF_DEPTH, SHELF_HEIGHT,
                          0.55, 0.35, 0.15)  # brown

    # BotValley zones — render zone boxes as shelf rows if present
    for zone in data.get("zones", []):
        if not zone.get("boxes"):
            continue
        for bi, box_pts in enumerate(zone["boxes"]):
            if len(box_pts) < 2:
                continue
            # Compute bounding rectangle of the zone box
            zxs = [p["x"] for p in box_pts]
            zys = [p["y"] for p in box_pts]
            zmin_x, zmax_x = min(zxs), max(zxs)
            zmin_y, zmax_y = min(zys), max(zys)
            zcx = (zmin_x + zmax_x) / 2
            zcy = (zmin_y + zmax_y) / 2
            zsx = zmax_x - zmin_x
            zsy = zmax_y - zmin_y

            zname = f"zone_{_safe_name(zone['name'])}_{bi}"
            model = _add_sub(world, "model", name=zname)
            _add_sub(model, "static", "true")
            _add_sub(model, "pose", _pose_str(zcx, zcy, SHELF_HEIGHT / 2))
            link = _add_sub(model, "link", name=f"{zname}_link")
            _build_box_visual(link, f"{zname}_visual",
                              max(zsx, 0.2), max(zsy, 0.2), SHELF_HEIGHT,
                              0.55, 0.35, 0.15, 0.6)  # semi-transparent brown


def _build_charging_stations(world: ET.Element, nodes: list[WarehouseNode]):
    """Place charging station models at 'charge' type nodes."""
    for n in nodes:
        if n.node_type != "charge":
            continue
        sname = f"charger_{_safe_name(n.name)}"
        model = _add_sub(world, "model", name=sname)
        _add_sub(model, "static", "true")
        _add_sub(model, "pose", _pose_str(n.x, n.y, STATION_HEIGHT / 2))
        link = _add_sub(model, "link", name=f"{sname}_link")
        _build_cylinder_visual(link, f"{sname}_visual",
                               STATION_RADIUS, STATION_HEIGHT,
                               0.0, 0.8, 0.0)  # green


def _build_pick_drop_stations(world: ET.Element, nodes: list[WarehouseNode]):
    """Place pick/drop station markers."""
    for n in nodes:
        if n.node_type not in ("pick", "drop"):
            continue
        color = NODE_COLORS.get(n.node_type, (0.5, 0.5, 0.5))
        sname = f"station_{_safe_name(n.name)}"
        model = _add_sub(world, "model", name=sname)
        _add_sub(model, "static", "true")
        _add_sub(model, "pose", _pose_str(n.x, n.y, STATION_HEIGHT / 2))
        link = _add_sub(model, "link", name=f"{sname}_link")
        _build_cylinder_visual(link, f"{sname}_visual",
                               STATION_RADIUS, STATION_HEIGHT,
                               *color)


def _build_barcode_grid(world: ET.Element, min_x: float, min_y: float,
                         max_x: float, max_y: float):
    """Place barcode markers on the floor at BARCODE_INTERVAL spacing."""
    barcode_id = 0
    model = _add_sub(world, "model", name="barcode_grid")
    _add_sub(model, "static", "true")
    _add_sub(model, "pose", _pose_str(0, 0, 0.001))
    link = _add_sub(model, "link", name="barcode_grid_link")

    # Generate grid points
    x = min_x
    while x <= max_x:
        y = min_y
        while y <= max_y:
            bname = f"barcode_{barcode_id}"
            vis = _add_sub(link, "visual", name=bname)
            _add_sub(vis, "pose", _pose_str(x, y, 0))
            geom = _add_sub(vis, "geometry")
            box = _add_sub(geom, "box")
            _add_sub(box, "size", f"{BARCODE_SIZE} {BARCODE_SIZE} 0.001")
            mat = _add_sub(vis, "material")
            _add_sub(mat, "ambient", "0.1 0.1 0.1 1.0")
            _add_sub(mat, "diffuse", "0.1 0.1 0.1 1.0")
            barcode_id += 1
            y += BARCODE_INTERVAL
        x += BARCODE_INTERVAL

    return barcode_id


def _build_node_markers(world: ET.Element, nodes: list[WarehouseNode]):
    """Place small colored spheres at each node position."""
    model = _add_sub(world, "model", name="node_markers")
    _add_sub(model, "static", "true")
    _add_sub(model, "pose", _pose_str(0, 0, NODE_MARKER_HEIGHT))
    link = _add_sub(model, "link", name="markers_link")

    for n in nodes:
        color = NODE_COLORS.get(n.node_type, (0.5, 0.5, 0.5))
        mname = f"marker_{_safe_name(n.name)}"
        _add_sub(link, "pose", _pose_str(0, 0, 0))  # link pose at origin

        vis = _add_sub(link, "visual", name=mname)
        _add_sub(vis, "pose", _pose_str(n.x, n.y, 0))
        geom = _add_sub(vis, "geometry")
        sphere = _add_sub(geom, "sphere")
        _add_sub(sphere, "radius", str(NODE_MARKER_RADIUS))
        mat = _add_sub(vis, "material")
        _add_sub(mat, "ambient", f"{color[0]} {color[1]} {color[2]} 1.0")
        _add_sub(mat, "diffuse", f"{color[0]} {color[1]} {color[2]} 1.0")


def _build_sun_and_physics(world: ET.Element):
    """Add sun light and physics settings."""
    # Sun
    light = _add_sub(world, "light", name="sun", type="directional")
    _add_sub(light, "cast_shadows", "true")
    _add_sub(light, "pose", _pose_str(0, 0, 10, 0, 0, 0))
    _add_sub(light, "diffuse", "0.8 0.8 0.8 1")
    _add_sub(light, "specular", "0.2 0.2 0.2 1")
    direction = _add_sub(light, "direction")
    direction.text = "-0.5 0.1 -0.9"

    # Physics — real time factor 1.0
    physics = _add_sub(world, "physics", name="default_physics", type="ode")
    _add_sub(physics, "max_step_size", "0.001")
    _add_sub(physics, "real_time_factor", "1.0")
    _add_sub(physics, "real_time_update_rate", "1000")

    # Scene
    scene = _add_sub(world, "scene")
    _add_sub(scene, "ambient", "0.4 0.4 0.4 1.0")
    _add_sub(scene, "background", "0.7 0.7 0.9 1.0")
    _add_sub(scene, "shadows", "true")

    # Gravity
    _add_sub(world, "gravity", "0 0 -9.81")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def generate_world(json_path: str, output_dir: str | None = None) -> str:
    """
    Generate a Gazebo Fortress SDF world file from a warehouse JSON.

    Args:
        json_path: Path to the warehouse JSON config.
        output_dir: Directory for the output SDF. Defaults to gazebo/worlds/.

    Returns:
        Path to the generated SDF file.
    """
    json_path = Path(json_path).resolve()
    with open(json_path) as f:
        data = json.load(f)

    # Determine warehouse name
    warehouse_name = data.get("name", json_path.stem)
    warehouse_name = _safe_name(warehouse_name).lower().replace(" ", "_")

    # Output path
    if output_dir is None:
        # Resolve relative to project root (two levels up from scripts/)
        project_root = Path(__file__).resolve().parent.parent.parent
        output_dir = project_root / "gazebo" / "worlds"
    else:
        output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    sdf_path = output_dir / f"{warehouse_name}.sdf"

    # Parse nodes
    nodes = _load_nodes(data)
    if not nodes:
        raise ValueError(f"No nodes found in {json_path}")

    # Compute bounds
    min_x, min_y, max_x, max_y = _compute_bounds(nodes)

    # Build SDF tree
    sdf = ET.Element("sdf", version="1.9")
    world = _add_sub(sdf, "world", name=warehouse_name)

    # Sun, physics, scene
    _build_sun_and_physics(world)

    # Ground plane
    _build_ground_plane(world, min_x, min_y, max_x, max_y)

    # Perimeter walls
    _build_perimeter_walls(world, min_x, min_y, max_x, max_y)

    # Shelves
    _build_shelves(world, nodes, data)

    # Charging stations
    _build_charging_stations(world, nodes)

    # Pick/drop stations
    _build_pick_drop_stations(world, nodes)

    # Barcode grid
    barcode_count = _build_barcode_grid(world, min_x, min_y, max_x, max_y)

    # Node markers
    _build_node_markers(world, nodes)

    # Write SDF
    xml_str = _indent_xml(sdf)
    with open(sdf_path, "w") as f:
        f.write(xml_str)

    print(f"Generated: {sdf_path}")
    print(f"  Warehouse: {warehouse_name}")
    print(f"  Nodes: {len(nodes)}")
    print(f"  Bounds: x=[{min_x:.1f}, {max_x:.1f}] y=[{min_y:.1f}, {max_y:.1f}]")
    print(f"  Barcodes: {barcode_count}")
    print(f"  Shelves: {len([n for n in nodes if n.node_type == 'shelf'])}")
    print(f"  Chargers: {len([n for n in nodes if n.node_type == 'charge'])}")
    print(f"  Pick stations: {len([n for n in nodes if n.node_type == 'pick'])}")
    print(f"  Drop stations: {len([n for n in nodes if n.node_type == 'drop'])}")

    return str(sdf_path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <warehouse_json_path> [output_dir]")
        sys.exit(1)

    json_file = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else None
    generate_world(json_file, out_dir)

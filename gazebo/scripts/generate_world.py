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

WALL_HEIGHT = 2.5        # metres
WALL_THICKNESS = 0.15    # metres
BARCODE_INTERVAL = 0.8   # metres
BARCODE_SIZE = 0.06      # metres (side of square)
NODE_MARKER_RADIUS = 0.08
NODE_MARKER_HEIGHT = 0.01  # just above ground


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


def _build_zone_geometry(world: ET.Element, nodes: list[WarehouseNode], data: dict):
    """Place DISTINCT geometry per zone type so LiDAR sees different signatures.

    Uses zone specs (shelf_height, shelf_depth, has_gaps) from the JSON config
    instead of hardcoded dimensions, so each zone produces a unique LiDAR
    signature even when nodes share the same type.

    Zone types and their geometry:
      dock/charge: back wall + tall charger pillar, open front (wall height = zone shelf_height)
      aisle:       two long parallel shelf walls (corridor) (wall height = zone shelf_height)
      shelf:       dense racks (height = zone shelf_height, depth = zone shelf_depth)
                   if zone has_gaps: skip every other shelf rack
      cross/none:  OPEN junction, no obstacles nearby
      hub:         large open area, no obstacles
      lane/predock: wall on ONE side only
      pick:        low conveyor table + open approach (height from zone spec)
      drop:        low conveyor table + back wall (height from zone spec)
      ops:         mixed obstacles at medium distance
    """
    model_id = [0]  # mutable counter

    def _next_name(prefix):
        model_id[0] += 1
        return f"{prefix}_{model_id[0]:03d}"

    def _add_static_box(name, x, y, z, sx, sy, sz, r, g, b, yaw=0):
        model = _add_sub(world, "model", name=name)
        _add_sub(model, "static", "true")
        _add_sub(model, "pose", _pose_str(x, y, z, 0, 0, yaw))
        link = _add_sub(model, "link", name=f"{name}_link")
        _build_box_visual(link, f"{name}_vis", sx, sy, sz, r, g, b)

    def _add_static_cylinder(name, x, y, z, radius, length, r, g, b):
        model = _add_sub(world, "model", name=name)
        _add_sub(model, "static", "true")
        _add_sub(model, "pose", _pose_str(x, y, z, 0, 0, 0))
        link = _add_sub(model, "link", name=f"{name}_link")
        _build_cylinder_visual(link, f"{name}_vis", radius, length, r, g, b)

    # ── Build node_name → zone_spec lookup from data["zones"] ──
    # Each zone carries shelf_height, shelf_depth, has_gaps that override defaults.
    _node_zone_spec: dict[str, dict] = {}
    _default_spec = {"shelf_height": 2.0, "shelf_depth": 0.3, "has_gaps": False}
    for zone in data.get("zones", []):
        spec = {
            "shelf_height": zone.get("shelf_height", 2.0),
            "shelf_depth":  zone.get("shelf_depth", 0.3),
            "has_gaps":     zone.get("has_gaps", False),
        }
        for nn in zone.get("nodes", []):
            _node_zone_spec[nn] = spec

    # Track shelf rack index per node for has_gaps skip logic
    _shelf_rack_counter: dict[str, int] = {}

    for node in nodes:
        nx, ny = node.x, node.y
        nt = node.node_type
        nn = _safe_name(node.name)
        zspec = _node_zone_spec.get(node.name, _default_spec)
        sh = zspec["shelf_height"]
        sd = zspec["shelf_depth"]
        gaps = zspec["has_gaps"]

        if nt in ("charge", "dock"):
            # DOCK: back wall behind node (height from zone spec), charger pillar, open front
            _add_static_box(_next_name(f"dock_wall_{nn}"),
                            nx, ny - 0.8, sh / 2, 2.0, 0.15, sh, 0.6, 0.6, 0.6)
            # Charger pillar: tall narrow next to node
            _add_static_box(_next_name(f"charger_{nn}"),
                            nx + 0.5, ny - 0.3, 0.75, 0.3, 0.3, 1.5, 0.0, 0.8, 0.0)

        elif nt == "aisle":
            # AISLE: two long parallel walls forming corridor
            # Wall height from zone's shelf_height
            _add_static_box(_next_name(f"aisle_L_{nn}"),
                            nx - 0.9, ny, sh / 2, 0.15, 3.0, sh, 0.55, 0.35, 0.15)
            _add_static_box(_next_name(f"aisle_R_{nn}"),
                            nx + 0.9, ny, sh / 2, 0.15, 3.0, sh, 0.55, 0.35, 0.15)

        elif nt == "shelf":
            # SHELF: dense racks using zone's shelf_height and shelf_depth
            # If zone has_gaps: skip every other shelf rack (leave periodic gaps)
            if gaps:
                # Count this shelf node within its zone for gap logic
                zone_key = node.name.rsplit("_S", 1)[0] if "_S" in node.name else node.name
                idx = _shelf_rack_counter.get(zone_key, 0)
                _shelf_rack_counter[zone_key] = idx + 1
                if idx % 2 == 1:
                    # Skip this rack — leave a gap (just a floor marker)
                    _add_static_cylinder(_next_name(f"gap_{nn}"),
                                         nx, ny, 0.01, 0.15, 0.02, 0.9, 0.9, 0.2)
                    continue

            # Multiple short shelf segments around the node
            for dx, dy, length, h_frac in [
                (-0.6, -0.5, 1.0, 1.0),   # left-back rack (full height)
                (-0.6,  0.5, 1.0, 1.0),   # left-front rack
                ( 0.6, -0.5, 1.0, 1.0),   # right-back rack
                ( 0.6,  0.5, 1.0, 1.0),   # right-front rack
                ( 0.0, -0.8, 0.8, 0.75),  # back center (shorter)
            ]:
                rack_h = sh * h_frac
                _add_static_box(_next_name(f"rack_{nn}"),
                                nx + dx, ny + dy, rack_h / 2,
                                sd, length, rack_h, 0.55, 0.35, 0.15)

        elif nt in ("cross", "none"):
            # CROSS/INTERSECTION: OPEN — no obstacles within 1.5m
            _add_static_cylinder(_next_name(f"cross_{nn}"),
                                 nx, ny, 0.01, 0.15, 0.02, 0.9, 0.9, 0.2)

        elif nt == "hub":
            # HUB: large open area — no obstacles within 3m
            _add_static_cylinder(_next_name(f"hub_{nn}"),
                                 nx, ny, 0.01, 0.4, 0.02, 1.0, 1.0, 0.0)

        elif nt in ("lane", "predock"):
            # LANE: wall on ONE side only (left), open on right
            _add_static_box(_next_name(f"lane_wall_{nn}"),
                            nx - 0.9, ny, 1.0, 0.15, 3.0, 2.0, 0.55, 0.35, 0.15)

        elif nt == "pick":
            # PICK: low conveyor table in front (height from zone spec), open sides
            _add_static_box(_next_name(f"pick_table_{nn}"),
                            nx, ny + 0.6, sh / 2, 1.5, 0.5, sh, 0.0, 0.4, 1.0)
            # Shelves behind
            _add_static_box(_next_name(f"pick_shelf_{nn}"),
                            nx, ny - 0.8, sh, 1.5, 0.15, sh * 2, 0.55, 0.35, 0.15)

        elif nt == "drop":
            # DROP: conveyor close in front (height from zone spec), wall behind, open sides
            _add_static_box(_next_name(f"drop_conv_{nn}"),
                            nx, ny + 0.4, sh / 2, 1.5, 0.5, sh, 1.0, 0.4, 0.0)
            _add_static_box(_next_name(f"drop_wall_{nn}"),
                            nx, ny - 0.8, sh, 2.0, 0.15, sh * 2, 0.6, 0.6, 0.6)

        elif nt == "ops":
            # OPS: mixed obstacles at medium distance
            _add_static_box(_next_name(f"ops_eq_{nn}"),
                            nx + 0.8, ny, 0.75, 0.6, 0.6, 1.5, 0.4, 0.4, 0.5)
            _add_static_box(_next_name(f"ops_bench_{nn}"),
                            nx - 0.5, ny + 0.5, 0.5, 1.2, 0.4, 1.0, 0.5, 0.5, 0.4)

        else:
            # Unknown type: single small obstacle
            _add_static_box(_next_name(f"obs_{nn}"),
                            nx + 0.5, ny, 0.5, 0.3, 0.3, 1.0, 0.5, 0.5, 0.5)

    # BotValley zones — render zone boxes as shelf rows if present
    for zone in data.get("zones", []):
        if not zone.get("boxes"):
            continue
        for bi, box_pts in enumerate(zone["boxes"]):
            if len(box_pts) < 2:
                continue
            zxs = [p["x"] for p in box_pts]
            zys = [p["y"] for p in box_pts]
            zcx = (min(zxs) + max(zxs)) / 2
            zcy = (min(zys) + max(zys)) / 2
            zsx = max(zxs) - min(zxs)
            zsy = max(zys) - min(zys)
            _add_static_box(_next_name(f"zone_{_safe_name(zone['name'])}"),
                            zcx, zcy, 0.6, max(zsx, 0.2), max(zsy, 0.2), 1.2,
                            0.55, 0.35, 0.15)


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

    # System plugins for sensor simulation
    _add_sub(world, "plugin", filename="gz-sim-physics-system",
             name="gz::sim::systems::Physics")
    sensors_plugin = _add_sub(world, "plugin", filename="gz-sim-sensors-system",
                              name="gz::sim::systems::Sensors")
    _add_sub(sensors_plugin, "render_engine", "ogre2")
    _add_sub(world, "plugin", filename="gz-sim-scene-broadcaster-system",
             name="gz::sim::systems::SceneBroadcaster")

    # Sun, physics, scene
    _build_sun_and_physics(world)

    # Ground plane
    _build_ground_plane(world, min_x, min_y, max_x, max_y)

    # Perimeter walls
    _build_perimeter_walls(world, min_x, min_y, max_x, max_y)

    # Zone-type-specific geometry (distinct LiDAR signatures per type)
    _build_zone_geometry(world, nodes, data)

    # Barcode grid — skip for large worlds (>200 nodes) to avoid overwhelming renderer
    if len(nodes) <= 200:
        barcode_count = _build_barcode_grid(world, min_x, min_y, max_x, max_y)
    else:
        barcode_count = 0
        print(f"  Skipping barcode grid ({len(nodes)} nodes > 200) — too many visuals for renderer")

    # Node markers — skip for large worlds
    if len(nodes) <= 200:
        _build_node_markers(world, nodes)
    else:
        print(f"  Skipping node markers ({len(nodes)} nodes > 200) — not needed for LiDAR")

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

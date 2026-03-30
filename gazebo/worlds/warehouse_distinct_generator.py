"""
Generate a Gazebo SDF world with PHYSICALLY DISTINCT zone geometry.

Each zone MUST have at least one geometric feature that produces a
distinctive LiDAR signature. This fixes the BotValley problem where
57/63 nodes had identical floor markers.

Zone geometry:
  charging:     Charger station model + back wall + pillar
  storage_a:    Parallel shelf walls, aisle width 1.2m
  storage_b:    Perpendicular shelves, aisle width 1.5m
  operations:   Wide open + pickup table models (scattered)
  corridor:     Wide corridor 3m + wall markers at intervals
  staging:      Half-wall barriers + dock door model
  maintenance:  Workbench models + tool rack walls

Output: warehouse_distinct.sdf

Usage:
    python warehouse_distinct_generator.py
    # Produces gazebo/worlds/warehouse_distinct.sdf
"""

import json
import math
from pathlib import Path
from typing import Optional

# World dimensions
WORLD_W = 40.0  # meters (x-axis)
WORLD_H = 30.0  # meters (y-axis)
WALL_HEIGHT = 3.0
WALL_THICKNESS = 0.15
SHELF_HEIGHT = 2.0
SHELF_DEPTH = 0.5
SHELF_WIDTH = 2.0
TABLE_HEIGHT = 0.8
TABLE_SIZE = 0.6


def _box_model(name: str, x: float, y: float, z: float,
               sx: float, sy: float, sz: float,
               r: float = 0.5, g: float = 0.5, b: float = 0.5) -> str:
    """Generate SDF for a static box model with collision."""
    return f"""
    <model name="{name}">
      <static>true</static>
      <pose>{x} {y} {z} 0 0 0</pose>
      <link name="link">
        <collision name="collision">
          <geometry><box><size>{sx} {sy} {sz}</size></box></geometry>
        </collision>
        <visual name="visual">
          <geometry><box><size>{sx} {sy} {sz}</size></box></geometry>
          <material>
            <ambient>{r} {g} {b} 1</ambient>
            <diffuse>{r} {g} {b} 1</diffuse>
          </material>
        </visual>
      </link>
    </model>"""


def _cylinder_model(name: str, x: float, y: float, z: float,
                    radius: float, length: float,
                    r: float = 0.5, g: float = 0.5, b: float = 0.5) -> str:
    """Generate SDF for a static cylinder model."""
    return f"""
    <model name="{name}">
      <static>true</static>
      <pose>{x} {y} {z} 0 0 0</pose>
      <link name="link">
        <collision name="collision">
          <geometry><cylinder><radius>{radius}</radius><length>{length}</length></cylinder></geometry>
        </collision>
        <visual name="visual">
          <geometry><cylinder><radius>{radius}</radius><length>{length}</length></cylinder></geometry>
          <material>
            <ambient>{r} {g} {b} 1</ambient>
            <diffuse>{r} {g} {b} 1</diffuse>
          </material>
        </visual>
      </link>
    </model>"""


def generate_perimeter_walls() -> str:
    """Generate 4 perimeter walls around the warehouse."""
    models = []
    hw = WORLD_W / 2
    hh = WORLD_H / 2
    wt = WALL_THICKNESS
    wh = WALL_HEIGHT

    # North wall
    models.append(_box_model("wall_north", 0, hh, wh / 2, WORLD_W, wt, wh, 0.3, 0.3, 0.3))
    # South wall
    models.append(_box_model("wall_south", 0, -hh, wh / 2, WORLD_W, wt, wh, 0.3, 0.3, 0.3))
    # East wall
    models.append(_box_model("wall_east", hw, 0, wh / 2, wt, WORLD_H, wh, 0.3, 0.3, 0.3))
    # West wall
    models.append(_box_model("wall_west", -hw, 0, wh / 2, wt, WORLD_H, wh, 0.3, 0.3, 0.3))

    return "\n".join(models)


def generate_charging_zone(base_x: float, base_y: float) -> tuple[str, list[dict]]:
    """Charging zone: charger stations + back wall + pillar.

    Distinctive: back wall 0.5m + charger pillar cylinders.
    LiDAR sees: open front, wall back, pillar on one side.
    """
    models = []
    nodes = []
    zone_w, zone_h = 6.0, 4.0

    # Back wall
    models.append(_box_model(
        "charge_back_wall", base_x, base_y - zone_h / 2, WALL_HEIGHT / 2,
        zone_w, WALL_THICKNESS, WALL_HEIGHT, 0.2, 0.6, 0.2
    ))

    # 3 charger pillars
    for i, dx in enumerate([-2.0, 0.0, 2.0]):
        models.append(_cylinder_model(
            f"charger_pillar_{i}", base_x + dx, base_y - zone_h / 2 + 0.5,
            0.5, 0.15, 1.0, 0.0, 0.8, 0.0
        ))
        nodes.append({
            "name": f"CHARGE_{i}", "x": base_x + dx, "y": base_y,
            "type": "charge",
        })

    return "\n".join(models), nodes


def generate_storage_a_zone(base_x: float, base_y: float) -> tuple[str, list[dict]]:
    """Storage A: parallel shelf rows, 1.2m aisle width.

    Distinctive: tight parallel walls, periodic gaps.
    LiDAR sees: 1.2m walls on both sides, gaps every ~2m.
    """
    models = []
    nodes = []
    n_rows = 4
    aisle_width = 1.2
    shelf_spacing = aisle_width + SHELF_DEPTH

    for row in range(n_rows):
        y = base_y + row * shelf_spacing
        for col in range(3):
            x = base_x + col * (SHELF_WIDTH + 0.3)
            models.append(_box_model(
                f"shelf_a_{row}_{col}", x, y, SHELF_HEIGHT / 2,
                SHELF_WIDTH, SHELF_DEPTH, SHELF_HEIGHT, 0.6, 0.4, 0.2
            ))

        # Nodes in aisles between rows
        if row < n_rows - 1:
            for col in range(3):
                nx = base_x + col * (SHELF_WIDTH + 0.3)
                ny = y + shelf_spacing / 2
                nodes.append({
                    "name": f"STOR_A_{row}_{col}", "x": nx, "y": ny,
                    "type": "shelf",
                })

    return "\n".join(models), nodes


def generate_storage_b_zone(base_x: float, base_y: float) -> tuple[str, list[dict]]:
    """Storage B: perpendicular shelves, 1.5m aisle width.

    Distinctive: shelves run left-right (rotated 90 deg vs storage A).
    LiDAR sees: narrow front/back, open sides (perpendicular view).
    """
    models = []
    nodes = []
    n_cols = 4
    aisle_width = 1.5
    shelf_spacing = aisle_width + SHELF_DEPTH

    for col in range(n_cols):
        x = base_x + col * shelf_spacing
        for row in range(3):
            y = base_y + row * (SHELF_WIDTH + 0.3)
            # Rotated 90 degrees: swap width/depth
            models.append(_box_model(
                f"shelf_b_{col}_{row}", x, y, SHELF_HEIGHT / 2,
                SHELF_DEPTH, SHELF_WIDTH, SHELF_HEIGHT, 0.4, 0.3, 0.6
            ))

        if col < n_cols - 1:
            for row in range(3):
                nx = x + shelf_spacing / 2
                ny = base_y + row * (SHELF_WIDTH + 0.3)
                nodes.append({
                    "name": f"STOR_B_{col}_{row}", "x": nx, "y": ny,
                    "type": "shelf",
                })

    return "\n".join(models), nodes


def generate_operations_zone(base_x: float, base_y: float) -> tuple[str, list[dict]]:
    """Operations: wide open area with pick/drop table models.

    Distinctive: large open space with scattered obstacles at 90-deg intervals.
    LiDAR sees: mostly far returns with periodic close table reflections.
    """
    models = []
    nodes = []

    # Pick tables
    for i in range(3):
        tx = base_x + i * 3.0 - 3.0
        ty = base_y + 1.5
        models.append(_box_model(
            f"pick_table_{i}", tx, ty, TABLE_HEIGHT / 2,
            TABLE_SIZE, TABLE_SIZE, TABLE_HEIGHT, 0.0, 0.7, 0.7
        ))
        nodes.append({
            "name": f"PICK_{i}", "x": tx, "y": ty - 1.0,
            "type": "pick",
        })

    # Drop tables
    for i in range(2):
        tx = base_x + i * 4.0 - 2.0
        ty = base_y - 1.5
        models.append(_box_model(
            f"drop_table_{i}", tx, ty, TABLE_HEIGHT / 2,
            TABLE_SIZE * 1.2, TABLE_SIZE, TABLE_HEIGHT, 0.7, 0.0, 0.0
        ))
        nodes.append({
            "name": f"DROP_{i}", "x": tx, "y": ty + 1.0,
            "type": "drop",
        })

    # Center hub node
    nodes.append({
        "name": "OPS_HUB", "x": base_x, "y": base_y,
        "type": "hub",
    })

    return "\n".join(models), nodes


def generate_corridor_zone(base_x: float, base_y: float,
                           length: float = 15.0) -> tuple[str, list[dict]]:
    """Corridor: wide transit (3m) with wall markers every 3m.

    Distinctive: wider than aisles (3m vs 1.2m), periodic marker bumps.
    LiDAR sees: long forward/backward, 3m sides, small bumps every 60 deg.
    """
    models = []
    nodes = []
    corridor_width = 3.0

    # Left wall
    models.append(_box_model(
        "corridor_wall_left", base_x - corridor_width / 2, base_y, WALL_HEIGHT / 2,
        WALL_THICKNESS, length, WALL_HEIGHT, 0.35, 0.35, 0.35
    ))
    # Right wall
    models.append(_box_model(
        "corridor_wall_right", base_x + corridor_width / 2, base_y, WALL_HEIGHT / 2,
        WALL_THICKNESS, length, WALL_HEIGHT, 0.35, 0.35, 0.35
    ))

    # Wall markers (small pillars) every 3m on both sides
    n_markers = int(length / 3.0)
    for i in range(n_markers):
        my = base_y - length / 2 + i * 3.0 + 1.5
        models.append(_cylinder_model(
            f"marker_left_{i}", base_x - corridor_width / 2 + 0.2, my,
            0.5, 0.08, 1.0, 0.8, 0.8, 0.0
        ))
        models.append(_cylinder_model(
            f"marker_right_{i}", base_x + corridor_width / 2 - 0.2, my,
            0.5, 0.08, 1.0, 0.8, 0.8, 0.0
        ))
        nodes.append({
            "name": f"CORR_{i}", "x": base_x, "y": my,
            "type": "none",
        })

    return "\n".join(models), nodes


def generate_staging_zone(base_x: float, base_y: float) -> tuple[str, list[dict]]:
    """Staging: half-wall barriers + dock door model.

    Distinctive: partial wall in front, open behind, pillar on one side.
    LiDAR sees: half wall at 2m front, open 6m behind, dock pillar at 1m.
    """
    models = []
    nodes = []

    # Half-wall barrier
    models.append(_box_model(
        "staging_halfwall", base_x, base_y + 2.0, 0.75,
        4.0, WALL_THICKNESS, 1.5, 0.5, 0.5, 0.3
    ))

    # Dock door pillars
    models.append(_cylinder_model(
        "dock_pillar_left", base_x - 1.5, base_y + 2.5, 1.0,
        0.2, 2.0, 0.4, 0.4, 0.4
    ))
    models.append(_cylinder_model(
        "dock_pillar_right", base_x + 1.5, base_y + 2.5, 1.0,
        0.2, 2.0, 0.4, 0.4, 0.4
    ))

    for i in range(3):
        nodes.append({
            "name": f"STAGE_{i}", "x": base_x + (i - 1) * 2.0, "y": base_y,
            "type": "predock",
        })

    return "\n".join(models), nodes


def generate_maintenance_zone(base_x: float, base_y: float) -> tuple[str, list[dict]]:
    """Maintenance: workbench + tool rack = asymmetric clutter.

    Distinctive: tool rack wall very close (1m) on one side, open exit opposite.
    LiDAR sees: asymmetric — workbench 2m, rack 1m, open 3.5m, equipment 1.5m.
    """
    models = []
    nodes = []

    # Workbench (long table)
    models.append(_box_model(
        "workbench", base_x + 1.5, base_y, TABLE_HEIGHT / 2,
        3.0, 0.8, TABLE_HEIGHT, 0.5, 0.3, 0.1
    ))

    # Tool rack (close wall with shelves)
    models.append(_box_model(
        "tool_rack", base_x - 2.0, base_y, 1.5,
        0.3, 4.0, 3.0, 0.3, 0.3, 0.5
    ))

    # Equipment on wall
    models.append(_box_model(
        "equipment", base_x, base_y - 2.0, 0.75,
        2.0, 0.4, 1.5, 0.4, 0.4, 0.3
    ))

    nodes.append({
        "name": "MAINT_0", "x": base_x, "y": base_y,
        "type": "none",
    })
    nodes.append({
        "name": "MAINT_1", "x": base_x, "y": base_y + 1.5,
        "type": "none",
    })

    return "\n".join(models), nodes


def generate_edges(all_nodes: list[dict]) -> list[dict]:
    """Generate edges connecting nodes within and between zones.

    Simple approach: connect nodes that are within 4m of each other.
    """
    edges = []
    seen = set()

    for i, n1 in enumerate(all_nodes):
        for j, n2 in enumerate(all_nodes):
            if i >= j:
                continue
            dx = n1["x"] - n2["x"]
            dy = n1["y"] - n2["y"]
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < 4.0:
                key = (n1["name"], n2["name"])
                if key not in seen:
                    edges.append({"from": n1["name"], "to": n2["name"]})
                    seen.add(key)

    return edges


def generate_warehouse_config() -> dict:
    """Generate the warehouse config JSON with distinct zones."""
    all_models = []
    all_nodes = []
    zones = []

    # Zone layout (x, y positions in the 40x30m world):
    #
    #  Charging (-15, 10)    Corridor (0, 10 to 0, -5)   Staging (15, 10)
    #  Storage_A (-12, 0)    Operations (0, 0)            Storage_B (12, 0)
    #  Maintenance (-12, -10)                              (open)

    # Charging zone (top-left)
    m, n = generate_charging_zone(-14.0, 10.0)
    all_models.append(m)
    all_nodes.extend(n)
    zones.append({"name": "Charging", "type": "charging", "nodes": [nd["name"] for nd in n]})

    # Storage A (mid-left)
    m, n = generate_storage_a_zone(-13.0, 0.0)
    all_models.append(m)
    all_nodes.extend(n)
    zones.append({"name": "Storage_A", "type": "storage_a", "nodes": [nd["name"] for nd in n]})

    # Storage B (mid-right)
    m, n = generate_storage_b_zone(10.0, 0.0)
    all_models.append(m)
    all_nodes.extend(n)
    zones.append({"name": "Storage_B", "type": "storage_b", "nodes": [nd["name"] for nd in n]})

    # Operations (center)
    m, n = generate_operations_zone(0.0, 0.0)
    all_models.append(m)
    all_nodes.extend(n)
    zones.append({"name": "Operations", "type": "operations", "nodes": [nd["name"] for nd in n]})

    # Corridor (center vertical)
    m, n = generate_corridor_zone(0.0, 6.0, length=12.0)
    all_models.append(m)
    all_nodes.extend(n)
    zones.append({"name": "Corridor", "type": "corridor", "nodes": [nd["name"] for nd in n]})

    # Staging (top-right)
    m, n = generate_staging_zone(14.0, 10.0)
    all_models.append(m)
    all_nodes.extend(n)
    zones.append({"name": "Staging", "type": "staging", "nodes": [nd["name"] for nd in n]})

    # Maintenance (bottom-left)
    m, n = generate_maintenance_zone(-12.0, -10.0)
    all_models.append(m)
    all_nodes.extend(n)
    zones.append({"name": "Maintenance", "type": "maintenance", "nodes": [nd["name"] for nd in n]})

    edges = generate_edges(all_nodes)

    config = {
        "name": "warehouse_distinct",
        "description": "Warehouse with physically distinct zone geometry for io-gita cold start testing",
        "width_m": WORLD_W,
        "height_m": WORLD_H,
        "nodes": all_nodes,
        "edges": edges,
        "zones": zones,
    }

    return config, "\n".join(all_models)


def generate_sdf(models_sdf: str) -> str:
    """Generate complete SDF world file."""
    perimeter = generate_perimeter_walls()

    return f"""<?xml version="1.0" ?>
<sdf version="1.8">
  <world name="warehouse_distinct">
    <physics name="1ms" type="ode">
      <max_step_size>0.001</max_step_size>
      <real_time_factor>1.0</real_time_factor>
    </physics>

    <plugin filename="libignition-gazebo-physics-system.so" name="ignition::gazebo::systems::Physics"/>
    <plugin filename="libignition-gazebo-scene-broadcaster-system.so" name="ignition::gazebo::systems::SceneBroadcaster"/>
    <plugin filename="libignition-gazebo-sensors-system.so" name="ignition::gazebo::systems::Sensors"/>

    <light type="directional" name="sun">
      <cast_shadows>true</cast_shadows>
      <pose>0 0 10 0 0 0</pose>
      <diffuse>0.8 0.8 0.8 1</diffuse>
      <specular>0.2 0.2 0.2 1</specular>
      <direction>-0.5 0.1 -0.9</direction>
    </light>

    <!-- Ground plane -->
    <model name="ground_plane">
      <static>true</static>
      <link name="link">
        <collision name="collision">
          <geometry>
            <plane><normal>0 0 1</normal><size>{WORLD_W} {WORLD_H}</size></plane>
          </geometry>
          <surface>
            <friction><ode><mu>0.8</mu><mu2>0.8</mu2></ode></friction>
          </surface>
        </collision>
        <visual name="visual">
          <geometry>
            <plane><normal>0 0 1</normal><size>{WORLD_W} {WORLD_H}</size></plane>
          </geometry>
          <material>
            <ambient>0.7 0.7 0.7 1</ambient>
            <diffuse>0.7 0.7 0.7 1</diffuse>
          </material>
        </visual>
      </link>
    </model>

    <!-- Perimeter walls -->
{perimeter}

    <!-- Zone geometry -->
{models_sdf}

  </world>
</sdf>"""


def main():
    """Generate both the SDF world and warehouse config JSON."""
    output_dir = Path(__file__).parent
    config_dir = output_dir.parent.parent / "configs" / "warehouses"

    config, models_sdf = generate_warehouse_config()
    sdf = generate_sdf(models_sdf)

    # Write SDF
    sdf_path = output_dir / "warehouse_distinct.sdf"
    sdf_path.write_text(sdf)
    print(f"SDF world: {sdf_path} ({len(sdf)} bytes)")

    # Write config JSON
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "warehouse_distinct.json"
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2, default=str)
    print(f"Config: {config_path}")
    print(f"  Zones: {len(config['zones'])}")
    print(f"  Nodes: {len(config['nodes'])}")
    print(f"  Edges: {len(config['edges'])}")

    for zone in config["zones"]:
        print(f"  {zone['name']} ({zone['type']}): {len(zone['nodes'])} nodes")


if __name__ == "__main__":
    main()

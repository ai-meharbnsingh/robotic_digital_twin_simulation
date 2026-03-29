#!/usr/bin/env python3
"""
Generate Gazebo models for a mixed fleet from a fleet manifest JSON.

Reads the fleet manifest (configs/fleets/*.json) and the warehouse config,
generates a robot SDF model for each unique robot type (via generate_robot.py),
then spawns each robot instance at a dock node in the warehouse.

Usage:
  python3 gazebo/scripts/generate_fleet.py \
    configs/fleets/default_mixed.json \
    configs/warehouses/simple_grid.json

Output:
  gazebo/models/{robot_type}/model.sdf   — one per unique robot config
  gazebo/fleet_spawn.json                — spawn positions for each robot instance
"""

import json
import sys
from pathlib import Path

import yaml

# Import generate_robot from the same directory
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_robot import generate_robot  # noqa: E402


def _load_dock_positions(warehouse_path: str) -> list[dict]:
    """Extract dock/charge node positions from warehouse JSON for robot spawning."""
    with open(warehouse_path) as f:
        data = json.load(f)

    dock_nodes = []
    # Build a zone→type lookup
    zone_types = {}
    for zone in data.get("zones", []):
        for node_name in zone.get("nodes", []):
            zone_types[node_name] = zone.get("type", "")

    # Find all charge/dock type nodes
    for node in data.get("nodes", []):
        name = node.get("name", "")
        node_type = node.get("type", zone_types.get(name, ""))

        if node_type in ("charge", "dock"):
            # Handle both flat and nested pose formats
            if "pose" in node and "position" in node["pose"]:
                x = node["pose"]["position"].get("x", 0)
                y = node["pose"]["position"].get("y", 0)
            else:
                x = node.get("x", 0)
                y = node.get("y", 0)

            dock_nodes.append({"name": name, "x": x, "y": y})

    return dock_nodes


def generate_fleet(fleet_manifest_path: str, warehouse_path: str,
                   output_dir: str | None = None) -> str:
    """
    Generate robot models and a spawn configuration for a mixed fleet.

    Args:
        fleet_manifest_path: Path to fleet manifest JSON
        warehouse_path: Path to warehouse JSON (for spawn positions)
        output_dir: Optional output directory (default: gazebo/ relative to project root)

    Returns:
        Path to the generated fleet_spawn.sdf snippet
    """
    project_root = Path(__file__).resolve().parent.parent.parent

    with open(fleet_manifest_path) as f:
        manifest = json.load(f)

    fleet_name = manifest.get("name", "unnamed_fleet")
    entries = manifest.get("robots", [])
    if not entries:
        raise ValueError(f"No robot entries in fleet manifest: {fleet_manifest_path}")

    # Load dock positions for spawning
    docks = _load_dock_positions(warehouse_path)
    if not docks:
        print("  WARNING: No dock/charge nodes found — robots will spawn at origin")
        docks = [{"name": "origin", "x": 0, "y": 0}]

    print(f"Fleet: {fleet_name}")
    print(f"  Dock positions available: {len(docks)}")

    # Step 1: Generate SDF model for each unique robot config
    generated_models = {}
    for entry in entries:
        config_path = entry["config"]
        if config_path in generated_models:
            continue

        # Resolve config path relative to project root
        abs_config = project_root / config_path
        if not abs_config.exists():
            raise FileNotFoundError(f"Robot config not found: {abs_config}")

        print(f"  Generating model from: {config_path}")
        model_path = generate_robot(str(abs_config))
        generated_models[config_path] = model_path

    # Step 2: Build spawn list — assign each robot instance to a dock position
    spawn_list = []
    dock_idx = 0
    spacing = 1.5  # meters between robots at same dock

    for entry in entries:
        id_prefix = entry["id_prefix"]
        count = entry.get("count", 1)
        config_path = entry["config"]

        # Get the model directory name from the generated model path
        model_dir = Path(generated_models[config_path]).parent
        model_name = model_dir.name

        for i in range(1, count + 1):
            robot_id = f"{id_prefix}_{i:03d}"

            # Assign to a dock position (cycle through available docks)
            dock = docks[dock_idx % len(docks)]

            # Offset within dock to avoid overlap when multiple robots share a dock
            robots_at_dock = dock_idx // len(docks)
            x_offset = robots_at_dock * spacing

            spawn_list.append({
                "robot_id": robot_id,
                "model_name": model_name,
                "model_uri": f"model://{model_name}",
                "x": dock["x"] + x_offset,
                "y": dock["y"],
                "z": 0.0,
                "dock_node": dock["name"],
            })

            dock_idx += 1

    # Step 3: Write spawn configuration as a simple JSON (consumed by launch scripts)
    if output_dir is None:
        out_path = project_root / "gazebo" / "fleet_spawn.json"
    else:
        out_path = Path(output_dir) / "fleet_spawn.json"

    out_path.parent.mkdir(parents=True, exist_ok=True)

    spawn_data = {
        "fleet_name": fleet_name,
        "total_robots": len(spawn_list),
        "robots": spawn_list,
    }

    with open(out_path, "w") as f:
        json.dump(spawn_data, f, indent=2)

    print(f"\nGenerated: {out_path}")
    print(f"  Fleet: {fleet_name}")
    print(f"  Total robots: {len(spawn_list)}")
    for entry in entries:
        print(f"    {entry['id_prefix']}: {entry.get('count', 1)} robots")

    return str(out_path)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <fleet_manifest.json> <warehouse.json> [output_dir]")
        sys.exit(1)

    fleet_file = sys.argv[1]
    warehouse_file = sys.argv[2]
    out = sys.argv[3] if len(sys.argv) > 3 else None
    generate_fleet(fleet_file, warehouse_file, out)

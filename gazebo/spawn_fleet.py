#!/usr/bin/env python3
"""
Spawn a namespaced multi-robot fleet in Gazebo.

Each robot gets:
  /robot_NN/cmd_vel   — velocity commands (DiffDrive)
  /robot_NN/odom      — odometry
  /robot_NN/lidar     — LiDAR (config-dependent FOV/range)
  /robot_NN/imu       — IMU sensor

Robot models organized by manufacturer:
  gazebo/models/addverb/   — Dynamo, Veloce, Quadron, AMR500, Zippy10
  gazebo/models/generic/   — DiffDrive AMR, Unidirectional AGV

Usage:
    python3 spawn_fleet.py --count 5                              # 5 generic AMRs
    python3 spawn_fleet.py --count 3 --model addverb/addverb_dynamo  # 3 Dynamo AGVs
    python3 spawn_fleet.py --fleet configs/fleets/addverb_mixed.json # mixed Addverb fleet
    python3 spawn_fleet.py --list-models                          # show available models
"""

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
MODELS_DIR = os.path.join(SCRIPT_DIR, "models")
DEFAULT_MODEL = "generic/diffdrive_amr"
CONFIG_PATH = os.path.join(PROJECT_ROOT, "configs", "warehouses", "warehouse_distinct.json")

# Map robot YAML config type to SDF model path
ROBOT_CONFIG_TO_MODEL = {
    "addverb_dynamo": "addverb/addverb_dynamo",
    "addverb_veloce": "addverb/addverb_veloce",
    "addverb_quadron": "addverb/addverb_quadron",
    "amr500": "addverb/amr500",
    "zippy10": "addverb/zippy10",
    "differential_drive": "generic/diffdrive_amr",
    "unidirectional": "generic/uni_agv",
}


def resolve_model_sdf(model_name: str) -> str:
    """Resolve model name to SDF file path."""
    # Try direct path first (e.g., addverb/addverb_dynamo)
    sdf_path = os.path.join(MODELS_DIR, model_name, "model.sdf")
    if os.path.exists(sdf_path):
        return sdf_path
    # Try config name mapping (e.g., addverb_dynamo)
    mapped = ROBOT_CONFIG_TO_MODEL.get(model_name)
    if mapped:
        return os.path.join(MODELS_DIR, mapped, "model.sdf")
    # Try legacy flat path (e.g., diffdrive_amr)
    legacy = os.path.join(MODELS_DIR, model_name, "model.sdf")
    if os.path.exists(legacy):
        return legacy
    raise FileNotFoundError(f"No SDF model found for '{model_name}'. Run --list-models to see available.")


def list_models():
    """List all available robot models."""
    print("Available robot models:\n")
    for manufacturer in sorted(os.listdir(MODELS_DIR)):
        mfg_dir = os.path.join(MODELS_DIR, manufacturer)
        if not os.path.isdir(mfg_dir):
            continue
        sdf = os.path.join(mfg_dir, "model.sdf")
        if os.path.exists(sdf):
            # Legacy flat model
            continue
        for robot in sorted(os.listdir(mfg_dir)):
            robot_sdf = os.path.join(mfg_dir, robot, "model.sdf")
            if os.path.exists(robot_sdf):
                print(f"  {manufacturer}/{robot}")
    print(f"\nUsage: --model <manufacturer>/<robot_name>")


BASE_SDF = os.path.join(MODELS_DIR, DEFAULT_MODEL, "model.sdf")


def generate_namespaced_sdf(robot_name: str, model_sdf_path: str = None) -> str:
    """Generate SDF with all topics prefixed by /robot_name/."""
    sdf_path = model_sdf_path or BASE_SDF
    with open(sdf_path) as f:
        sdf = f.read()

    # Replace model name (handles any model name in the SDF)
    import re
    sdf = re.sub(r'<model name="[^"]*">', f'<model name="{robot_name}">', sdf, count=1)

    # Namespace all topics
    sdf = sdf.replace('<topic>cmd_vel</topic>', f'<topic>/{robot_name}/cmd_vel</topic>')
    sdf = sdf.replace('<odom_topic>odom</odom_topic>', f'<odom_topic>/{robot_name}/odom</odom_topic>')
    sdf = sdf.replace('<tf_topic>tf</tf_topic>', f'<tf_topic>/{robot_name}/tf</tf_topic>')
    sdf = sdf.replace('<topic>lidar</topic>', f'<topic>/{robot_name}/lidar</topic>')
    sdf = sdf.replace('<topic>imu</topic>', f'<topic>/{robot_name}/imu</topic>')

    # Unique visual colors per robot (slight variation)
    import hashlib
    h = int(hashlib.md5(robot_name.encode()).hexdigest()[:6], 16)
    r = 0.2 + (h % 256) / 512.0
    g = 0.2 + ((h >> 8) % 256) / 512.0
    b = 0.2 + ((h >> 16) % 256) / 512.0
    sdf = sdf.replace(
        '<ambient>0.2 0.2 0.8 1.0</ambient>',
        f'<ambient>{r:.2f} {g:.2f} {b:.2f} 1.0</ambient>', 1
    )
    sdf = sdf.replace(
        '<diffuse>0.2 0.2 0.8 1.0</diffuse>',
        f'<diffuse>{r:.2f} {g:.2f} {b:.2f} 1.0</diffuse>', 1
    )

    return sdf


def gz_cmd(args, timeout=10):
    try:
        r = subprocess.run(["gz"] + args, capture_output=True, text=True, timeout=timeout)
        return r.stdout
    except Exception:
        return ""


def detect_world():
    for t in gz_cmd(["topic", "-l"]).strip().split("\n"):
        t = t.strip()
        if t.startswith("/world/") and t.endswith("/clock"):
            return t.split("/")[2]
    return None


def spawn_robot(world_name: str, robot_name: str, x: float, y: float, yaw: float = 0.0, model_sdf: str = None):
    """Spawn a namespaced robot at (x, y) in the Gazebo world."""
    sdf_content = generate_namespaced_sdf(robot_name, model_sdf)

    # Write to /tmp/ (Gazebo needs accessible path)
    tmp_path = f"/tmp/{robot_name}.sdf"
    with open(tmp_path, 'w') as f:
        f.write(sdf_content)
    class _tmp:
        name = tmp_path
    tmp = _tmp()

    qz = math.sin(yaw / 2)
    qw = math.cos(yaw / 2)
    req = (f"sdf_filename: '{tmp.name}', name: '{robot_name}', "
           f"pose: {{position: {{x: {x}, y: {y}, z: 0.0}}, "
           f"orientation: {{z: {qz:.6f}, w: {qw:.6f}}}}}")

    result = gz_cmd(["service", "-s", f"/world/{world_name}/create",
                     "--reqtype", "gz.msgs.EntityFactory",
                     "--reptype", "gz.msgs.Boolean",
                     "--timeout", "10000", "--req", req], timeout=15)

    return "true" in result.lower()


def main():
    parser = argparse.ArgumentParser(description="Spawn namespaced robot fleet in Gazebo")
    parser.add_argument("--count", type=int, default=5, help="Number of robots")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Robot model (e.g., addverb/addverb_dynamo)")
    parser.add_argument("--fleet", default=None, help="Fleet manifest JSON (overrides --count and --model)")
    parser.add_argument("--world", default=None, help="World name (auto-detect if not set)")
    parser.add_argument("--list-models", action="store_true", help="List available robot models")
    args = parser.parse_args()

    if args.list_models:
        list_models()
        sys.exit(0)

    model_sdf = resolve_model_sdf(args.model)

    world = args.world or detect_world()
    if not world:
        print("ERROR: No Gazebo world detected. Start Gazebo first.")
        sys.exit(1)

    print(f"World: {world}")
    print(f"Spawning {args.count} robots...\n")

    # Load warehouse config for spawn positions
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    nodes = config["nodes"]

    spawned = []
    for i in range(args.count):
        name = f"robot_{i+1:02d}"
        node = nodes[i % len(nodes)]
        x, y = node["x"], node["y"]
        # Offset slightly to avoid stacking
        x += (i % 3 - 1) * 0.5
        y += (i // 3 % 3 - 1) * 0.5

        ok = spawn_robot(world, name, x, y, model_sdf=model_sdf)
        status = "OK" if ok else "FAIL"
        print(f"  {name} at ({x:.1f}, {y:.1f}) — {status}")
        if ok:
            spawned.append(name)
        time.sleep(0.5)  # Give Gazebo time between spawns

    print(f"\nSpawned: {len(spawned)}/{args.count}")
    print(f"\nVerifying topics...")
    time.sleep(2)

    topics = gz_cmd(["topic", "-l"]).strip().split("\n")
    for name in spawned:
        lidar = any(f"/{name}/lidar" in t and "points" not in t for t in topics)
        cmd = any(f"/{name}/cmd_vel" in t for t in topics)
        odom = any(f"/{name}/odom" in t for t in topics)
        print(f"  {name}: lidar={'OK' if lidar else 'MISSING'}  "
              f"cmd_vel={'OK' if cmd else 'MISSING'}  "
              f"odom={'OK' if odom else 'MISSING'}")

    print(f"\nFleet ready. Each robot has:")
    print(f"  /{name}/cmd_vel  — DiffDrive velocity")
    print(f"  /{name}/lidar    — 360-ray GPU LiDAR")
    print(f"  /{name}/odom     — odometry")
    print(f"  /{name}/imu      — IMU sensor")


if __name__ == "__main__":
    main()

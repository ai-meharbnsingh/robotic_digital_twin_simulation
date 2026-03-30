#!/usr/bin/env python3
"""
Spawn a namespaced multi-robot fleet in Gazebo.

Each robot gets:
  /robot_NN/cmd_vel   — velocity commands (DiffDrive)
  /robot_NN/odom      — odometry
  /robot_NN/lidar     — 360-ray GPU LiDAR
  /robot_NN/imu       — IMU sensor

Usage:
    python3 spawn_fleet.py --count 5 --world warehouse_distinct
    python3 spawn_fleet.py --count 15 --world warehouse_distinct
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
BASE_SDF = os.path.join(SCRIPT_DIR, "models", "diffdrive_amr", "model.sdf")
CONFIG_PATH = os.path.join(PROJECT_ROOT, "configs", "warehouses", "warehouse_distinct.json")


def generate_namespaced_sdf(robot_name: str) -> str:
    """Generate SDF with all topics prefixed by /robot_name/."""
    with open(BASE_SDF) as f:
        sdf = f.read()

    # Replace model name
    sdf = sdf.replace('name="diffdrive_amr"', f'name="{robot_name}"', 1)

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


def spawn_robot(world_name: str, robot_name: str, x: float, y: float, yaw: float = 0.0):
    """Spawn a namespaced robot at (x, y) in the Gazebo world."""
    sdf_content = generate_namespaced_sdf(robot_name)

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
    parser.add_argument("--world", default=None, help="World name (auto-detect if not set)")
    args = parser.parse_args()

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

        ok = spawn_robot(world, name, x, y)
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

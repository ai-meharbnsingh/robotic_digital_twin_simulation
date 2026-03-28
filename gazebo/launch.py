#!/usr/bin/env python3
"""
Gazebo launch script — launches Gazebo Fortress with a generated warehouse
world, spawns N robots at specified positions, and optionally connects to
the C++ FMS server via TCP.

Usage:
  python3 gazebo/launch.py --warehouse simple_grid --robot differential_drive --num-robots 3
  python3 gazebo/launch.py --warehouse botvalley --robot unidirectional --num-robots 10 --headless
  python3 gazebo/launch.py --warehouse simple_grid --robot differential_drive --fms-host 127.0.0.1 --fms-port 5555

Arguments:
  --warehouse   Name of warehouse config (without .json extension) or full path
  --robot       Name of robot config (without .yaml extension) or full path
  --num-robots  Number of robots to spawn (default: 1)
  --headless    Run in headless mode (no GUI)
  --fms-host    FMS server TCP host (optional, for bridge mode)
  --fms-port    FMS server TCP port (optional, default: 5555)
  --verbose     Enable verbose logging
"""

import argparse
import json
import math
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

# Project root — two levels up from gazebo/launch.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _find_config(name: str, config_dir: str, extension: str) -> Path:
    """Resolve a config name to a file path."""
    # If it's already a valid path, use it
    p = Path(name)
    if p.exists():
        return p.resolve()
    # Try configs/{config_dir}/{name}{extension}
    cfg_path = PROJECT_ROOT / "configs" / config_dir / f"{name}{extension}"
    if cfg_path.exists():
        return cfg_path
    raise FileNotFoundError(
        f"Config not found: {name} (tried {p} and {cfg_path})")


def _ensure_world(warehouse_path: Path) -> Path:
    """Generate the SDF world if it doesn't exist yet, return its path."""
    # Import the world generator
    sys.path.insert(0, str(PROJECT_ROOT / "gazebo" / "scripts"))
    from generate_world import generate_world

    warehouse_name = json.loads(warehouse_path.read_text()).get("name", warehouse_path.stem)
    safe_name = warehouse_name.replace("|", "_").replace(" ", "_").lower()
    sdf_path = PROJECT_ROOT / "gazebo" / "worlds" / f"{safe_name}.sdf"

    if not sdf_path.exists() or sdf_path.stat().st_mtime < warehouse_path.stat().st_mtime:
        print(f"[launch] Generating world from {warehouse_path} ...")
        generate_world(str(warehouse_path))
    else:
        print(f"[launch] World up to date: {sdf_path}")

    return sdf_path


def _ensure_robot(robot_path: Path) -> Path:
    """Generate the robot SDF model if it doesn't exist, return its path."""
    sys.path.insert(0, str(PROJECT_ROOT / "gazebo" / "scripts"))
    from generate_robot import generate_robot

    import yaml
    with open(robot_path) as f:
        cfg = yaml.safe_load(f)
    robot_name = cfg["name"].replace(" ", "_").lower()
    model_sdf = PROJECT_ROOT / "gazebo" / "models" / robot_name / "model.sdf"

    if not model_sdf.exists() or model_sdf.stat().st_mtime < robot_path.stat().st_mtime:
        print(f"[launch] Generating robot model from {robot_path} ...")
        generate_robot(str(robot_path))
    else:
        print(f"[launch] Robot model up to date: {model_sdf}")

    return model_sdf


def _get_spawn_positions(warehouse_path: Path, num_robots: int) -> list[tuple[float, float, float]]:
    """
    Determine spawn positions for N robots.
    Prefer 'charge' type nodes, then 'aisle'/'none' nodes, spaced apart.
    """
    with open(warehouse_path) as f:
        data = json.load(f)

    nodes = data.get("nodes", [])
    if not nodes:
        # Fallback: spawn at origin
        return [(i * 1.5, 0, 0) for i in range(num_robots)]

    # Extract positions + types
    parsed = []
    for n in nodes:
        if "pose" in n:
            pos = n["pose"]["position"]
            x, y = pos["x"], pos["y"]
        else:
            x, y = n["x"], n["y"]
        parsed.append((x, y, n.get("type", "none")))

    # Prefer charge nodes first, then aisle/none nodes
    charge_nodes = [(x, y) for x, y, t in parsed if t == "charge"]
    other_nodes = [(x, y) for x, y, t in parsed if t in ("aisle", "none", "hub")]

    candidates = charge_nodes + other_nodes
    if not candidates:
        candidates = [(x, y) for x, y, _ in parsed]

    # Pick up to num_robots positions, trying to space them out
    positions = []
    used = set()
    for i in range(min(num_robots, len(candidates))):
        if i < len(candidates):
            positions.append((*candidates[i], 0.0))
            used.add(i)

    # If we need more robots than candidates, offset from first positions
    while len(positions) < num_robots:
        base = positions[len(positions) % len(candidates)]
        offset = len(positions) * 0.5
        positions.append((base[0] + offset, base[1] + offset, 0.0))

    return positions


def _spawn_robot_cmd(robot_sdf: Path, robot_name: str,
                     x: float, y: float, z: float) -> list[str]:
    """Build gz service command to spawn a robot model."""
    model_dir = robot_sdf.parent
    return [
        "gz", "service",
        "-s", "/world/default/create",
        "--reqtype", "gz.msgs.EntityFactory",
        "--reptype", "gz.msgs.Boolean",
        "--timeout", "5000",
        "--req",
        f'sdf_filename: "{robot_sdf}" '
        f'name: "{robot_name}" '
        f'pose: {{ position: {{ x: {x} y: {y} z: {z} }} }}'
    ]


def _connect_fms(host: str, port: int) -> socket.socket | None:
    """Attempt TCP connection to FMS server."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect((host, port))
        print(f"[launch] Connected to FMS at {host}:{port}")
        return sock
    except (ConnectionRefusedError, socket.timeout, OSError) as e:
        print(f"[launch] WARNING: Could not connect to FMS at {host}:{port}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Launch Gazebo Fortress with warehouse world and robots")
    parser.add_argument("--warehouse", required=True,
                        help="Warehouse config name or path (e.g. simple_grid)")
    parser.add_argument("--robot", required=True,
                        help="Robot config name or path (e.g. differential_drive)")
    parser.add_argument("--num-robots", type=int, default=1,
                        help="Number of robots to spawn (default: 1)")
    parser.add_argument("--headless", action="store_true",
                        help="Run without GUI")
    parser.add_argument("--fms-host", default=None,
                        help="FMS TCP server host (optional)")
    parser.add_argument("--fms-port", type=int, default=5555,
                        help="FMS TCP server port (default: 5555)")
    parser.add_argument("--verbose", action="store_true",
                        help="Enable verbose output")
    args = parser.parse_args()

    # Resolve configs
    warehouse_path = _find_config(args.warehouse, "warehouses", ".json")
    robot_path = _find_config(args.robot, "robots", ".yaml")

    print(f"[launch] Warehouse: {warehouse_path}")
    print(f"[launch] Robot: {robot_path}")
    print(f"[launch] Robots: {args.num_robots}")

    # Generate world + robot model
    world_sdf = _ensure_world(warehouse_path)
    robot_sdf = _ensure_robot(robot_path)

    # Compute spawn positions
    positions = _get_spawn_positions(warehouse_path, args.num_robots)

    # Set GZ_SIM_RESOURCE_PATH so Gazebo can find our models
    models_dir = str(PROJECT_ROOT / "gazebo" / "models")
    plugins_dir = str(PROJECT_ROOT / "gazebo" / "plugins" / "build")
    existing_resource = os.environ.get("GZ_SIM_RESOURCE_PATH", "")
    existing_plugin = os.environ.get("GZ_SIM_SYSTEM_PLUGIN_PATH", "")
    env = os.environ.copy()
    env["GZ_SIM_RESOURCE_PATH"] = f"{models_dir}:{existing_resource}"
    env["GZ_SIM_SYSTEM_PLUGIN_PATH"] = f"{plugins_dir}:{existing_plugin}"

    # Launch Gazebo
    gz_cmd = ["gz", "sim", "-r", str(world_sdf)]
    if args.headless:
        gz_cmd.append("-s")  # server only, no GUI
    if args.verbose:
        gz_cmd.extend(["-v", "4"])

    print(f"[launch] Starting Gazebo: {' '.join(gz_cmd)}")
    gz_proc = subprocess.Popen(gz_cmd, env=env)

    # Wait for Gazebo to initialise
    print("[launch] Waiting for Gazebo to start ...")
    time.sleep(5)

    if gz_proc.poll() is not None:
        print(f"[launch] ERROR: Gazebo exited with code {gz_proc.returncode}")
        sys.exit(1)

    # Spawn robots
    import yaml
    with open(robot_path) as f:
        robot_cfg = yaml.safe_load(f)
    robot_base_name = robot_cfg["name"].replace(" ", "_").lower()

    for i, (x, y, z) in enumerate(positions):
        rname = f"{robot_base_name}_{i}" if args.num_robots > 1 else robot_base_name
        print(f"[launch] Spawning {rname} at ({x:.2f}, {y:.2f}, {z:.2f})")
        cmd = _spawn_robot_cmd(robot_sdf, rname, x, y, z)
        try:
            subprocess.run(cmd, env=env, timeout=10, check=False,
                           capture_output=not args.verbose)
        except subprocess.TimeoutExpired:
            print(f"[launch] WARNING: Spawn timeout for {rname}")

    print(f"[launch] {args.num_robots} robot(s) spawned.")

    # Optional FMS connection
    fms_sock = None
    if args.fms_host:
        fms_sock = _connect_fms(args.fms_host, args.fms_port)

    # Wait for Gazebo to exit
    def _shutdown(signum, frame):
        print("\n[launch] Shutting down ...")
        gz_proc.terminate()
        if fms_sock:
            fms_sock.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    print("[launch] Gazebo running. Press Ctrl+C to stop.")
    try:
        gz_proc.wait()
    except KeyboardInterrupt:
        _shutdown(None, None)

    print(f"[launch] Gazebo exited with code {gz_proc.returncode}")
    if fms_sock:
        fms_sock.close()


if __name__ == "__main__":
    main()

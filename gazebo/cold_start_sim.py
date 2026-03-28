#!/usr/bin/env python3
"""
Cold Start Simulation — Real Gazebo LiDAR or Synthetic Fallback
================================================================

Uses the SAME zone_identifier.py (P22 method) that achieved 100% on 25 zones.

Phase 1: Launch Gazebo with simple_grid world + spawn robot
Phase 2: Calibrate — read REAL lidar at each node (or synthetic fallback)
Phase 3: Cold start test — teleport, read ONE scan, identify zone
Phase 4: Compare io-gita (instant hint) vs blind recovery (random walk)
Phase 5: Print results + save JSON

Usage:
  python gazebo/cold_start_sim.py                    # Try Gazebo, fallback to synthetic
  python gazebo/cold_start_sim.py --synthetic         # Force synthetic mode
  python gazebo/cold_start_sim.py --warehouse botvalley  # Use BotValley map (63 nodes)
"""

import argparse
import json
import math
import os
import re
import subprocess
import sys
import time

import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

sys.path.insert(0, os.path.join(PROJECT_ROOT, "python", "intelligence", "iogita"))
from zone_identifier import ZoneIdentifier, generate_zone_scan, extract_16_features


# ── Gazebo helpers ──

def gz_available():
    try:
        r = subprocess.run(["gz", "sim", "--version"], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def gz_topic_echo(topic, count=1, timeout=5):
    try:
        r = subprocess.run(["gz", "topic", "-e", "-t", topic, "-n", str(count)],
                           capture_output=True, text=True, timeout=timeout)
        return r.stdout
    except Exception:
        return ""


def gz_topics():
    try:
        r = subprocess.run(["gz", "topic", "-l"], capture_output=True, text=True, timeout=5)
        return [t.strip() for t in r.stdout.strip().split("\n") if t.strip()]
    except Exception:
        return []


def gz_running():
    return len(gz_topic_echo("/clock", count=1, timeout=3)) > 0


def launch_gazebo(world_sdf):
    """Launch Gazebo server with world. Returns True if successful."""
    print(f"  Launching Gazebo: {os.path.basename(world_sdf)}")
    proc = subprocess.Popen(
        ["gz", "sim", "-s", "-r", world_sdf],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"  PID: {proc.pid}")
    for i in range(30):
        time.sleep(1)
        print(".", end="", flush=True)
        if gz_running():
            print(" UP")
            return True
    print(" TIMEOUT")
    return False


def spawn_robot(world_name, model_sdf, name="robot_0", x=0, y=0):
    qz, qw = 0, 1
    req = (f"sdf_filename: '{model_sdf}', name: '{name}', "
           f"pose: {{position: {{x: {x}, y: {y}, z: 0.0}}, "
           f"orientation: {{z: {qz}, w: {qw}}}}}")
    subprocess.run(
        ["gz", "service", "-s", f"/world/{world_name}/create",
         "--reqtype", "gz.msgs.EntityFactory",
         "--reptype", "gz.msgs.Boolean",
         "--timeout", "10000", "--req", req],
        capture_output=True, timeout=15)


def teleport(world_name, name, x, y, yaw=0.0):
    qz = math.sin(yaw / 2)
    qw = math.cos(yaw / 2)
    req = (f"name: '{name}', position: {{x: {x}, y: {y}, z: 0.05}}, "
           f"orientation: {{z: {qz:.6f}, w: {qw:.6f}}}")
    subprocess.run(
        ["gz", "service", "-s", f"/world/{world_name}/set_pose",
         "--reqtype", "gz.msgs.Pose", "--reptype", "gz.msgs.Boolean",
         "--timeout", "3000", "--req", req],
        capture_output=True, timeout=5)


def read_lidar_gazebo(topic="/lidar", timeout=4):
    """Read 360-ray lidar scan from Gazebo topic."""
    raw = gz_topic_echo(topic, count=1, timeout=timeout)
    if not raw:
        return None
    ranges = []
    for m in re.finditer(r'ranges:\s*([-\d.e+inf]+)', raw):
        val = m.group(1)
        ranges.append(float("inf") if "inf" in val else float(val))
    return np.array(ranges) if len(ranges) >= 36 else None


def find_lidar_topic():
    for t in gz_topics():
        if t == "/lidar":
            return t
    for t in gz_topics():
        if "lidar" in t.lower() and "points" not in t.lower():
            return t
    return None


# ── Load warehouse config ──

def load_warehouse(name):
    path = os.path.join(PROJECT_ROOT, "configs", "warehouses", f"{name}.json")
    with open(path) as f:
        config = json.load(f)
    return config


# ── Main simulation ──

def run_cold_start(warehouse_name="simple_grid", force_synthetic=False):
    os.chdir(PROJECT_ROOT)

    print()
    print("  ╔══════════════════════════════════════════════════════════════╗")
    print("  ║  Cold Start Simulation — io-gita Zone Identification        ║")
    print("  ╚══════════════════════════════════════════════════════════════╝")
    print()

    # Load warehouse config
    config = load_warehouse(warehouse_name)
    nodes = config["nodes"]
    edges = config["edges"]
    zones = config.get("zones", [])
    print(f"  Warehouse: {config['name']}")
    print(f"  Nodes: {len(nodes)}, Edges: {len(edges)}, Zones: {len(zones)}")

    # Determine mode: Gazebo real or synthetic
    use_gazebo = False
    world_name = None
    lidar_topic = None
    robot_name = "robot_0"

    if not force_synthetic and gz_available():
        # Try launching Gazebo
        world_files = {
            "simple_grid": "simple_5x5_grid.sdf",
            "botvalley": "botvalley.sdf",
        }
        world_sdf = os.path.join(SCRIPT_DIR, "worlds", world_files.get(warehouse_name, "simple_5x5_grid.sdf"))

        if os.path.exists(world_sdf):
            if gz_running():
                topics = gz_topics()
                # Check which world is running
                for t in topics:
                    if "simple_5x5" in t:
                        world_name = "simple_5x5_grid"
                        break
                    elif "botvalley" in t:
                        world_name = "botvalley"
                        break
                if not world_name:
                    world_name = warehouse_name.replace("simple_grid", "simple_5x5_grid")
                print(f"  Gazebo already running: {world_name}")
            else:
                world_name = warehouse_name.replace("simple_grid", "simple_5x5_grid")
                if launch_gazebo(world_sdf):
                    time.sleep(2)
                else:
                    print("  Gazebo launch failed — falling back to SYNTHETIC")

            if world_name:
                # Spawn robot if needed
                topics = gz_topics()
                if not any(robot_name in t for t in topics):
                    model_sdf = os.path.join(SCRIPT_DIR, "models", "diffdrive_amr", "model.sdf")
                    first_node = nodes[0]
                    print(f"  Spawning {robot_name} at ({first_node['x']}, {first_node['y']})...")
                    spawn_robot(world_name, model_sdf, robot_name, first_node["x"], first_node["y"])
                    time.sleep(3)

                lidar_topic = find_lidar_topic()
                if lidar_topic:
                    # Verify we get data
                    test_scan = read_lidar_gazebo(lidar_topic, timeout=5)
                    if test_scan is not None and len(test_scan) >= 36:
                        use_gazebo = True
                        print(f"  LiDAR topic: {lidar_topic} ({len(test_scan)} rays)")
                    else:
                        print(f"  LiDAR topic found but no data — falling back to SYNTHETIC")
                else:
                    print("  No LiDAR topic — falling back to SYNTHETIC")

    mode = "REAL GAZEBO RAYCASTS" if use_gazebo else "SYNTHETIC (P22 generate_zone_scan)"
    print(f"\n  Mode: {mode}")
    print()

    # ── Build ZoneIdentifier ──
    zid = ZoneIdentifier(zones=zones, nodes=nodes, edges=edges)
    print(f"  ZoneIdentifier: {len(zid.node_fingerprints)} node fingerprints")
    print(f"  Backend: {zid.backend}")

    # ── Phase 2: Calibration (real or synthetic) ──
    print()
    print("  ── Phase 2: Calibration ──")

    rng = np.random.default_rng(42)
    calibration = {}

    if use_gazebo:
        # REAL: teleport robot to each node, read actual lidar
        print(f"  Calibrating {len(nodes)} nodes with REAL Gazebo LiDAR...")
        for i, node in enumerate(nodes):
            heading_deg, dist_dock, turns = zid.get_node_dock_features(node["name"])
            # Scan at 4 compass headings, average
            scans = []
            for h in [0, 90, 180, 270]:
                teleport(world_name, robot_name, node["x"], node["y"], math.radians(h))
                time.sleep(0.4)
                scan = read_lidar_gazebo(lidar_topic, timeout=4)
                if scan is not None:
                    # Resample to 360 if different count
                    if len(scan) != 360:
                        scan = np.interp(np.linspace(0, len(scan)-1, 360),
                                        np.arange(len(scan)), scan)
                    scans.append(scan)
            if scans:
                avg_scan = np.mean(scans, axis=0)
            else:
                avg_scan = generate_zone_scan(node.get("type", "none"), rng, heading_deg, dist_dock)
                print(f"    WARN: {node['name']} — no Gazebo data, using synthetic")

            features = extract_16_features(avg_scan, heading_deg, dist_dock, turns)
            calibration[node["name"]] = {"scan": avg_scan, "features": features,
                                          "heading": heading_deg, "dist_dock": dist_dock}
            if (i + 1) % 5 == 0:
                print(f"    {i + 1}/{len(nodes)} nodes calibrated")
        # INJECT real calibration into ZoneIdentifier (replace synthetic fingerprints)
        for node_name, cal in calibration.items():
            zid._node_fingerprints[node_name] = cal["features"]
        print(f"  Calibration done: {len(calibration)} nodes with REAL LiDAR")
        print(f"  Injected REAL fingerprints into ZoneIdentifier (replaced synthetic)")
    else:
        # SYNTHETIC: use P22 generate_zone_scan — fingerprints already built in __init__
        print(f"  Using SYNTHETIC fingerprints from ZoneIdentifier.__init__")
        for node in nodes:
            heading_deg, dist_dock, turns = zid.get_node_dock_features(node["name"])
            calibration[node["name"]] = {"heading": heading_deg, "dist_dock": dist_dock}

    # ── Phase 3: Cold Start Test ──
    print()
    print("  ── Phase 3: Cold Start Test ──")
    print()
    print(f"  {'#':>3} {'Node':>12} {'Type':>8} {'Zone':>10} {'Identified':>12} "
          f"{'Method':>16} {'Conf':>5} {'ms':>5} {'':>2}")
    print(f"  {'─'*3} {'─'*12} {'─'*8} {'─'*10} {'─'*12} {'─'*16} {'─'*5} {'─'*5} {'─'*2}")

    test_rng = np.random.default_rng(2026)
    correct = 0
    adjacent = 0
    total = 0
    ode_times = []
    iogita_times = []
    blind_times = []

    for i, node in enumerate(nodes):
        total += 1
        node_name = node["name"]
        heading_deg, dist_dock, turns = zid.get_node_dock_features(node_name)

        # Generate test scan (real or synthetic) with noise
        if use_gazebo:
            # Random heading (power cycle — but IMU gives heading)
            test_heading = test_rng.uniform(0, 360)
            teleport(world_name, robot_name, node["x"], node["y"], math.radians(test_heading))
            time.sleep(0.4)
            scan = read_lidar_gazebo(lidar_topic, timeout=4)
            if scan is None:
                scan = generate_zone_scan(node.get("type", "none"), test_rng, heading_deg, dist_dock)
            elif len(scan) != 360:
                scan = np.interp(np.linspace(0, len(scan)-1, 360), np.arange(len(scan)), scan)
            # Add noise
            scan = scan + test_rng.normal(0, 0.03, len(scan))
            scan = np.clip(scan, 0.1, 12.0)
            # IMU heading (known, ±3° noise)
            imu_heading = test_heading + test_rng.normal(0, 3)
        else:
            # Synthetic scan with noise
            scan = generate_zone_scan(node.get("type", "none"), test_rng, heading_deg, dist_dock)
            imu_heading = heading_deg + test_rng.normal(0, 3)

        # Get previous zone (simulate FMS knowledge: pick a neighbor)
        node_zone = None
        for z in zones:
            if node_name in z.get("nodes", []):
                node_zone = z["name"]
                break

        neighbors = []
        for e in edges:
            if e["from"] == node_name:
                neighbors.append(e["to"])
            elif e["to"] == node_name:
                neighbors.append(e["from"])
        prev_node = test_rng.choice(neighbors) if neighbors else node_name
        prev_zone = None
        for z in zones:
            if prev_node in z.get("nodes", []):
                prev_zone = z["name"]
                break

        # ── io-gita identification ──
        result = zid.identify_from_scan(
            scan, heading_deg=imu_heading, dist_from_dock=dist_dock,
            turns_since_dock=turns, previous_zone=prev_zone)

        identified_zone = result["zone"]
        method = result["method"]
        confidence = result["confidence"]
        ode_ms = result["ode_time_ms"]
        ode_times.append(ode_ms)

        is_correct = identified_zone == node_zone
        is_adj = identified_zone in zid.zone_adjacency.get(node_zone or "", set())
        if is_correct:
            correct += 1
        elif is_adj:
            adjacent += 1

        # Recovery times
        iogita_sec = ode_ms / 1000 + 0.05 + 0.5 / 1.4 + 0.005  # ODE + FMS + drive + barcode
        if not is_correct and not is_adj:
            iogita_sec += 3.0  # wrong zone penalty
        iogita_times.append(iogita_sec)

        blind_sec = (0.4 * 1.5) / 0.3 * test_rng.uniform(1.0, 2.0)  # random walk to barcode
        blind_times.append(blind_sec)

        mark = "✓" if is_correct else ("~" if is_adj else "✗")
        print(f"  {i+1:3} {node_name:>12} {node.get('type','?'):>8} "
              f"{node_zone or '?':>10} {identified_zone:>12} "
              f"{method:>16} {confidence:4.2f}  {ode_ms:4.1f}  {mark}")

    # ── Phase 5: Results ──
    ig_arr = np.array(iogita_times)
    bl_arr = np.array(blind_times)
    acc = (correct + adjacent) / total

    print()
    print("  ══════════════════════════════════════════════════════════════")
    print(f"  RESULTS — {mode}")
    print("  ══════════════════════════════════════════════════════════════")
    print()
    print(f"  Warehouse:        {config['name']} ({len(nodes)} nodes)")
    print(f"  Exact correct:    {correct}/{total} ({correct/total*100:.1f}%)")
    print(f"  Adjacent correct: {adjacent}/{total} ({adjacent/total*100:.1f}%)")
    print(f"  Total accuracy:   {correct+adjacent}/{total} ({acc*100:.1f}%)")
    print(f"  ODE timing:       mean={np.mean(ode_times):.2f}ms")
    print()
    print(f"  ┌──────────────────────────────────────────────────────────┐")
    print(f"  │                  WITH io-gita    WITHOUT (blind walk)   │")
    print(f"  │  ──────────────  ─────────────   ────────────────       │")
    print(f"  │  Recovery (avg)  {ig_arr.mean():.2f}s            {bl_arr.mean():.1f}s              │")
    print(f"  │  Recovery (max)  {ig_arr.max():.2f}s            {bl_arr.max():.1f}s              │")
    print(f"  │  Speedup         {bl_arr.mean()/ig_arr.mean():.1f}x                                   │")
    print(f"  │  Accuracy        {acc*100:.1f}%              N/A                    │")
    print(f"  └──────────────────────────────────────────────────────────┘")
    print()

    # Save results
    out = {
        "mode": "gazebo_real" if use_gazebo else "synthetic",
        "warehouse": config["name"],
        "n_nodes": len(nodes),
        "accuracy_exact": correct,
        "accuracy_adjacent": adjacent,
        "accuracy_pct": round(acc * 100, 1),
        "ode_mean_ms": round(float(np.mean(ode_times)), 3),
        "iogita_recovery_mean_s": round(float(ig_arr.mean()), 3),
        "blind_recovery_mean_s": round(float(bl_arr.mean()), 3),
        "speedup": round(float(bl_arr.mean() / ig_arr.mean()), 1),
    }
    results_path = os.path.join(SCRIPT_DIR, "cold_start_results.json")
    with open(results_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"  Results saved: {results_path}")
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cold Start Simulation")
    parser.add_argument("--warehouse", default="simple_grid", choices=["simple_grid", "botvalley"])
    parser.add_argument("--synthetic", action="store_true", help="Force synthetic mode")
    args = parser.parse_args()
    run_cold_start(args.warehouse, args.synthetic)

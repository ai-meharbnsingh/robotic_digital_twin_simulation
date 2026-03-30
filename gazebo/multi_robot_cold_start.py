#!/usr/bin/env python3
"""
MULTI-ROBOT COLD START TEST — Real Gazebo Raycasts
====================================================

Simulates a 5-robot fleet cold start using the io-gita engine.

Test 1: Simultaneous cold start — all 5 robots recover at once
Test 2: Fleet learning — Robot_1 calibrates, robots 2-5 reuse its data
Test 3: Bottleneck prediction — detect 3+ robots converging on same zone
Test 4: Recovery with obstacle — blocked direct path, fallback to 2nd candidate

Implementation note: We teleport a SINGLE Gazebo robot (robot_0) to
different positions to simulate each "robot". Each position represents
a different robot in the fleet.

Requirements:
  - Gazebo running with warehouse_distinct.sdf
  - Robot spawned with 360-ray GPU LiDAR on /lidar topic
  - gz CLI available (gz topic, gz service)
"""

import json
import math
import os
import re
import subprocess
import sys
import time
from collections import Counter

import numpy as np

# ── Path setup ───────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

sys.path.insert(0, os.path.join(PROJECT_ROOT, "python"))

from intelligence.iogita.zone_identifier import (
    HierarchicalZoneIdentifier,
    extract_16_features,
    extract_zone_features,
)

# ── Constants ────────────────────────────────────────────────────────

DEFAULT_WORLD_NAME = "warehouse_distinct"
CONFIG_PATH = os.path.join(PROJECT_ROOT, "configs", "warehouses", "warehouse_distinct.json")
MODEL_SDF = os.path.join(SCRIPT_DIR, "models", "diffdrive_amr", "model.sdf")
ROBOT_NAME = "robot_0"
WORLD_NAME = DEFAULT_WORLD_NAME  # may be overridden by auto-detection

NUM_ROBOTS = 5
ROBOT_NAMES = [f"robot_{i+1}" for i in range(NUM_ROBOTS)]


# ── Gazebo helper functions (from full_flow_cold_start_v4.py) ────────

def gz_cmd(args, timeout=10):
    try:
        r = subprocess.run(["gz"] + args, capture_output=True, text=True, timeout=timeout)
        return r.stdout
    except Exception:
        return ""


def gz_running():
    return len(gz_cmd(["topic", "-e", "-t", "/clock", "-n", "1"], timeout=3)) > 0


def gz_topics():
    return [t.strip() for t in gz_cmd(["topic", "-l"]).strip().split("\n") if t.strip()]


def teleport(x, y, yaw=0.0):
    qz, qw = math.sin(yaw / 2), math.cos(yaw / 2)
    req = (f"name: '{ROBOT_NAME}', position: {{x: {x}, y: {y}, z: 0.05}}, "
           f"orientation: {{z: {qz:.6f}, w: {qw:.6f}}}")
    gz_cmd(["service", "-s", f"/world/{WORLD_NAME}/set_pose",
            "--reqtype", "gz.msgs.Pose", "--reptype", "gz.msgs.Boolean",
            "--timeout", "3000", "--req", req], timeout=5)


def read_lidar(topic="/lidar", timeout=4):
    raw = gz_cmd(["topic", "-e", "-t", topic, "-n", "1"], timeout=timeout)
    if not raw:
        return None
    ranges = []
    for m in re.finditer(r'ranges:\s*([-\d.e+inf]+)', raw):
        val = m.group(1)
        ranges.append(float("inf") if "inf" in val else float(val))
    if not ranges or len(ranges) < 36:
        return None
    arr = np.array(ranges, dtype=np.float64)
    if len(arr) != 360:
        arr = np.interp(np.linspace(0, len(arr) - 1, 360), np.arange(len(arr)), arr)
    arr = np.where(np.isfinite(arr), arr, 12.0)
    arr = np.clip(arr, 0.1, 12.0)
    return arr


def scan_changed(old_scan, new_scan, threshold=0.1):
    if old_scan is None or new_scan is None:
        return True
    return float(np.mean(np.abs(old_scan - new_scan))) > threshold


def teleport_and_wait(x, y, yaw, lidar_topic, timeout=5.0):
    old_scan = read_lidar(lidar_topic, timeout=2)
    teleport(x, y, yaw)
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(0.15)
        new_scan = read_lidar(lidar_topic, timeout=2)
        if new_scan is not None and scan_changed(old_scan, new_scan, threshold=0.05):
            time.sleep(0.1)
            final = read_lidar(lidar_topic, timeout=2)
            return final if final is not None else new_scan
    return read_lidar(lidar_topic, timeout=2)


def detect_world_name():
    for t in gz_topics():
        if t.startswith("/world/") and t.endswith("/clock"):
            return t.split("/")[2]
    return None


def find_lidar_topic():
    for t in gz_topics():
        if t == "/lidar":
            return t
    for t in gz_topics():
        if "lidar" in t.lower() and "points" not in t.lower():
            return t
    return None


def spawn_robot(x, y):
    req = (f"sdf_filename: '{MODEL_SDF}', name: '{ROBOT_NAME}', "
           f"pose: {{position: {{x: {x}, y: {y}, z: 0.0}}}}")
    gz_cmd(["service", "-s", f"/world/{WORLD_NAME}/create",
            "--reqtype", "gz.msgs.EntityFactory",
            "--reptype", "gz.msgs.Boolean",
            "--timeout", "10000", "--req", req], timeout=15)


# ── Utility ──────────────────────────────────────────────────────────

def print_header(title):
    width = 64
    print()
    print(f"  {'=' * width}")
    print(f"  {title}")
    print(f"  {'=' * width}")
    print()


def print_table_row(cols, widths):
    """Print a row with fixed-width columns."""
    parts = []
    for col, w in zip(cols, widths):
        parts.append(f"{col:>{w}}" if isinstance(col, str) else f"{col:>{w}}")
    print("  " + "  ".join(parts))


# ── Phase 0: Calibration ────────────────────────────────────────────

def calibrate(zi, nodes, lidar_topic):
    """Phase 0: Visit every node, collect 1 scan, build fingerprints.

    This is the fast calibration mode: 1 heading per node.
    Returns number of successfully calibrated nodes.
    """
    print("  Calibrating: 1 heading per node (fast mode)")
    print()

    cal_ok = 0
    failed = []

    for i, node in enumerate(nodes):
        heading_deg, dist_dock, turns = zi.get_node_dock_features(node["name"])

        scan = teleport_and_wait(node["x"], node["y"], 0.0, lidar_topic)

        if scan is not None:
            zi.set_node_fingerprint(node["name"], scan, heading_deg, dist_dock, turns)
            cal_ok += 1
            status = "ok"
        else:
            failed.append(node["name"])
            status = "FAIL"

        if (i + 1) % 10 == 0 or i == 0 or i == len(nodes) - 1:
            print(f"    {i+1:3}/{len(nodes)} {node['name']:>14} -- {status}")

    zi.rebuild_hopfield()

    print(f"\n  Calibration complete: {cal_ok}/{len(nodes)} nodes")
    if failed:
        print(f"  Failed: {failed}")

    return cal_ok, failed


# ── Test 1: Simultaneous Cold Start ─────────────────────────────────

def test_1_simultaneous_cold_start(zi, nodes, zones, node_to_zone, lidar_topic, rng):
    """Test 1: 5 robots cold start simultaneously at random positions.

    Each robot gets a random node, teleported there, reads LiDAR,
    and runs recover_from_last_known() with +/-1m noise and random heading.

    Targets: 88%+ zone accuracy, all 5 recover within 10 seconds.
    """
    print_header("TEST 1: Simultaneous Cold Start (5 robots)")

    # Pick 5 random node positions for the fleet
    indices = rng.choice(len(nodes), size=NUM_ROBOTS, replace=False)
    assigned_nodes = [nodes[i] for i in indices]

    print(f"  Robot assignments:")
    for i, node in enumerate(assigned_nodes):
        zone = node_to_zone.get(node["name"], "?")
        print(f"    {ROBOT_NAMES[i]:>10} -> {node['name']:>14} (zone: {zone})")
    print()

    widths = [10, 14, 14, 14, 5, 6, 2]
    header = ["Robot", "TrueNode", "TrueZone", "PredZone", "Conf", "ms", ""]
    print_table_row(header, widths)
    print("  " + "  ".join(["-" * w for w in widths]))

    fleet_start = time.time()
    results = []

    for i, node in enumerate(assigned_nodes):
        robot_name = ROBOT_NAMES[i]
        true_zone = node_to_zone.get(node["name"], "?")

        # Add position noise (+/-1m)
        noise_x = float(rng.normal(0, 1.0))
        noise_y = float(rng.normal(0, 1.0))
        last_x = node["x"] + noise_x
        last_y = node["y"] + noise_y

        # Random heading (simulating unknown orientation after crash)
        heading = float(rng.uniform(0, 360))

        # Teleport to actual node position and read real LiDAR
        t0 = time.time()
        scan = teleport_and_wait(node["x"], node["y"],
                                 math.radians(heading), lidar_topic)

        if scan is None:
            print(f"  {robot_name:>10} -- NO LIDAR")
            results.append({"robot": robot_name, "zone_ok": False, "time_s": 0})
            continue

        # Add sensor noise
        scan = scan + rng.normal(0, 0.03, len(scan))
        scan = np.clip(scan, 0.1, 12.0)

        # Run recovery
        r = zi.recover_from_last_known(scan, last_x, last_y,
                                       heading_deg=heading, k=8)
        elapsed_ms = (time.time() - t0) * 1000

        pred_zone = r["zone"]
        conf = r["confidence"]
        zone_ok = pred_zone == true_zone
        mark = "Y" if zone_ok else "X"

        print_table_row([robot_name, node["name"], true_zone, pred_zone,
                         f"{conf:.2f}", f"{elapsed_ms:.0f}", mark], widths)

        results.append({
            "robot": robot_name,
            "true_node": node["name"],
            "true_zone": true_zone,
            "pred_zone": pred_zone,
            "pred_node": r["node"],
            "confidence": conf,
            "zone_ok": zone_ok,
            "time_ms": elapsed_ms,
        })

    fleet_time = time.time() - fleet_start

    # Summary
    zone_correct = sum(1 for r in results if r.get("zone_ok", False))
    zone_accuracy = zone_correct / len(results) * 100 if results else 0
    print()
    print(f"  Zone accuracy:      {zone_correct}/{len(results)} ({zone_accuracy:.1f}%)")
    print(f"  Fleet recovery:     {fleet_time:.2f}s total")
    print(f"  Target:             88%+ zone accuracy, <10s fleet recovery")
    print(f"  GATE zone>=88%:     {'PASS' if zone_accuracy >= 88 else 'FAIL'}")
    print(f"  GATE fleet<10s:     {'PASS' if fleet_time < 10 else 'FAIL'}")

    return {
        "test": "simultaneous_cold_start",
        "num_robots": NUM_ROBOTS,
        "zone_accuracy_pct": round(zone_accuracy, 1),
        "zone_correct": zone_correct,
        "zone_total": len(results),
        "fleet_recovery_s": round(fleet_time, 2),
        "gate_zone_88": zone_accuracy >= 88,
        "gate_fleet_10s": fleet_time < 10,
        "per_robot": results,
    }


# ── Test 2: Fleet Learning ──────────────────────────────────────────

def test_2_fleet_learning(zi, nodes, zones, node_to_zone, lidar_topic, rng):
    """Test 2: Robot_1 calibrates; robots 2-5 reuse its calibration.

    Robot_1 already calibrated in Phase 0 (all nodes visited).
    Robots 2-5 "crash" at DIFFERENT random positions than calibration
    and use Robot_1's zi object (same fingerprints) to recover.

    Target: >75% zone accuracy for uncalibrated robots.
    """
    print_header("TEST 2: Fleet Learning (shared calibration)")

    # Pick 4 random positions for robots 2-5 (different from each other)
    indices = rng.choice(len(nodes), size=NUM_ROBOTS - 1, replace=False)
    crash_nodes = [nodes[i] for i in indices]

    print(f"  Robot_1: calibrated (Phase 0)")
    for i, node in enumerate(crash_nodes):
        zone = node_to_zone.get(node["name"], "?")
        print(f"    {ROBOT_NAMES[i+1]:>10} crashes at {node['name']:>14} (zone: {zone})")
    print()

    widths = [10, 14, 14, 14, 5, 2]
    header = ["Robot", "CrashNode", "TrueZone", "PredZone", "Conf", ""]
    print_table_row(header, widths)
    print("  " + "  ".join(["-" * w for w in widths]))

    results = []

    for i, node in enumerate(crash_nodes):
        robot_name = ROBOT_NAMES[i + 1]
        true_zone = node_to_zone.get(node["name"], "?")

        # Position noise
        last_x = node["x"] + float(rng.normal(0, 1.0))
        last_y = node["y"] + float(rng.normal(0, 1.0))
        heading = float(rng.uniform(0, 360))

        scan = teleport_and_wait(node["x"], node["y"],
                                 math.radians(heading), lidar_topic)

        if scan is None:
            print(f"  {robot_name:>10} -- NO LIDAR")
            results.append({"robot": robot_name, "zone_ok": False})
            continue

        scan = scan + rng.normal(0, 0.03, len(scan))
        scan = np.clip(scan, 0.1, 12.0)

        # Use Robot_1's calibration (same zi object, no re-calibration)
        r = zi.recover_from_last_known(scan, last_x, last_y,
                                       heading_deg=heading, k=8)

        pred_zone = r["zone"]
        conf = r["confidence"]
        zone_ok = pred_zone == true_zone
        mark = "Y" if zone_ok else "X"

        print_table_row([robot_name, node["name"], true_zone, pred_zone,
                         f"{conf:.2f}", mark], widths)

        results.append({
            "robot": robot_name,
            "crash_node": node["name"],
            "true_zone": true_zone,
            "pred_zone": pred_zone,
            "pred_node": r["node"],
            "confidence": conf,
            "zone_ok": zone_ok,
        })

    zone_correct = sum(1 for r in results if r.get("zone_ok", False))
    zone_accuracy = zone_correct / len(results) * 100 if results else 0
    print()
    print(f"  Zone accuracy (shared cal): {zone_correct}/{len(results)} ({zone_accuracy:.1f}%)")
    print(f"  Target:                     >75%")
    print(f"  GATE zone>75%:              {'PASS' if zone_accuracy > 75 else 'FAIL'}")

    return {
        "test": "fleet_learning",
        "calibrator": "robot_1",
        "learners": ROBOT_NAMES[1:],
        "zone_accuracy_pct": round(zone_accuracy, 1),
        "zone_correct": zone_correct,
        "zone_total": len(results),
        "gate_zone_75": zone_accuracy > 75,
        "per_robot": results,
    }


# ── Test 3: Bottleneck Prediction ───────────────────────────────────

def test_3_bottleneck_prediction(zi, nodes, zones, node_to_zone, lidar_topic, rng):
    """Test 3: Detect when 3+ robots converge on the same zone.

    Assign 3 robots to nodes in Storage_A, 2 to other zones.
    Each robot identifies its zone. If 3+ robots identify the same zone
    within 2 seconds, flag a bottleneck.

    Report: was bottleneck detected? How many robots in congested zone?
    """
    print_header("TEST 3: Bottleneck Prediction")

    # Find Storage_A nodes
    storage_a_zone = None
    for z in zones:
        if z["name"] == "Storage_A":
            storage_a_zone = z
            break
    if storage_a_zone is None:
        print("  ERROR: Storage_A zone not found in config")
        return {"test": "bottleneck_prediction", "error": "no_storage_a"}

    sa_node_names = storage_a_zone["nodes"]
    sa_nodes = [n for n in nodes if n["name"] in sa_node_names]

    # Pick 3 Storage_A nodes for the congested robots
    sa_sample_idx = rng.choice(len(sa_nodes), size=min(3, len(sa_nodes)), replace=False)
    congested_nodes = [sa_nodes[i] for i in sa_sample_idx]

    # Pick 2 nodes from other zones for the non-congested robots
    other_nodes = [n for n in nodes if n["name"] not in sa_node_names]
    other_idx = rng.choice(len(other_nodes), size=min(2, len(other_nodes)), replace=False)
    spread_nodes = [other_nodes[i] for i in other_idx]

    all_assignments = congested_nodes + spread_nodes
    robot_labels = ROBOT_NAMES[:len(all_assignments)]

    print(f"  Setup: 3 robots in Storage_A, 2 in other zones")
    for i, node in enumerate(all_assignments):
        zone = node_to_zone.get(node["name"], "?")
        print(f"    {robot_labels[i]:>10} -> {node['name']:>14} (zone: {zone})")
    print()

    # Each robot identifies zone
    zone_identifications = []
    bottleneck_window_start = time.time()

    for i, node in enumerate(all_assignments):
        robot_name = robot_labels[i]
        heading = float(rng.uniform(0, 360))

        last_x = node["x"] + float(rng.normal(0, 1.0))
        last_y = node["y"] + float(rng.normal(0, 1.0))

        scan = teleport_and_wait(node["x"], node["y"],
                                 math.radians(heading), lidar_topic)

        if scan is None:
            print(f"  {robot_name}: NO LIDAR")
            continue

        scan = scan + rng.normal(0, 0.03, len(scan))
        scan = np.clip(scan, 0.1, 12.0)

        r = zi.recover_from_last_known(scan, last_x, last_y,
                                       heading_deg=heading, k=8)

        zone_identifications.append({
            "robot": robot_name,
            "pred_zone": r["zone"],
            "true_zone": node_to_zone.get(node["name"], "?"),
            "time": time.time(),
        })
        print(f"    {robot_name}: identified zone = {r['zone']} "
              f"(true: {node_to_zone.get(node['name'], '?')})")

    bottleneck_window_elapsed = time.time() - bottleneck_window_start

    # Bottleneck detection: 3+ robots in same zone within 2-second window
    zone_counts = Counter(z["pred_zone"] for z in zone_identifications)
    bottleneck_zones = {z: c for z, c in zone_counts.items() if c >= 3}
    bottleneck_detected = len(bottleneck_zones) > 0

    print()
    print(f"  Zone distribution: {dict(zone_counts)}")
    print(f"  Detection window:  {bottleneck_window_elapsed:.2f}s")
    print(f"  Bottleneck found:  {'YES' if bottleneck_detected else 'NO'}")
    if bottleneck_zones:
        for z, c in bottleneck_zones.items():
            print(f"    CONGESTION: {z} has {c} robots")
    else:
        print(f"    No zone has 3+ robots (threshold not met)")

    # The test passes if the system correctly detects the congestion
    # (3 robots were placed in Storage_A, so if zone ID works, we should detect it)
    correct_bottleneck = "Storage_A" in bottleneck_zones
    print()
    print(f"  Expected bottleneck in Storage_A: {'DETECTED' if correct_bottleneck else 'MISSED'}")

    return {
        "test": "bottleneck_prediction",
        "bottleneck_detected": bottleneck_detected,
        "bottleneck_zones": {z: int(c) for z, c in bottleneck_zones.items()},
        "zone_distribution": {z: int(c) for z, c in zone_counts.items()},
        "detection_window_s": round(bottleneck_window_elapsed, 2),
        "correct_storage_a": correct_bottleneck,
        "per_robot": zone_identifications,
    }


# ── Test 4: Recovery with Obstacle ──────────────────────────────────

def test_4_recovery_with_obstacle(zi, nodes, zones, node_to_zone, lidar_topic, rng):
    """Test 4: Robot crashes, zone correct, but direct path is blocked.

    1. Robot crashes at a random position
    2. recover_from_last_known identifies top-k candidates
    3. Mark the #1 candidate node as "blocked"
    4. Robot should fall back to #2 candidate
    5. Measure: does robot reach correct zone via alternative? Time delta?

    This simulates an obstacle blocking the direct route to the nearest node.
    """
    print_header("TEST 4: Recovery with Obstacle (blocked direct path)")

    # Pick a random crash node
    crash_idx = int(rng.choice(len(nodes)))
    crash_node = nodes[crash_idx]
    true_zone = node_to_zone.get(crash_node["name"], "?")

    heading = float(rng.uniform(0, 360))
    last_x = crash_node["x"] + float(rng.normal(0, 1.0))
    last_y = crash_node["y"] + float(rng.normal(0, 1.0))

    print(f"  Crash position:   ({crash_node['x']}, {crash_node['y']})")
    print(f"  True node:        {crash_node['name']}")
    print(f"  True zone:        {true_zone}")
    print(f"  Noisy last_known: ({last_x:.1f}, {last_y:.1f})")
    print(f"  Heading:          {heading:.0f} deg")
    print()

    # Step 1: Normal recovery (no obstacle)
    scan = teleport_and_wait(crash_node["x"], crash_node["y"],
                             math.radians(heading), lidar_topic)

    if scan is None:
        print("  ERROR: No LiDAR scan")
        return {"test": "recovery_with_obstacle", "error": "no_lidar"}

    scan = scan + rng.normal(0, 0.03, len(scan))
    scan = np.clip(scan, 0.1, 12.0)

    t0 = time.time()
    r_normal = zi.recover_from_last_known(scan, last_x, last_y,
                                          heading_deg=heading, k=8)
    normal_time_ms = (time.time() - t0) * 1000

    normal_node = r_normal["node"]
    normal_zone = r_normal["zone"]
    candidates = r_normal.get("candidates", [])

    print(f"  Normal recovery:")
    print(f"    Best node:      {normal_node} (zone: {normal_zone})")
    print(f"    Confidence:     {r_normal['confidence']:.2f}")
    print(f"    Time:           {normal_time_ms:.1f}ms")
    print(f"    Candidates:     {[c[0] for c in candidates[:5]]}")
    print()

    # Step 2: Block the #1 candidate and pick #2
    if len(candidates) < 2:
        print("  Only 1 candidate -- cannot test obstacle fallback")
        return {
            "test": "recovery_with_obstacle",
            "error": "insufficient_candidates",
            "normal_node": normal_node,
            "normal_zone": normal_zone,
        }

    blocked_node = candidates[0][0]
    fallback_node = candidates[1][0]
    fallback_zone = node_to_zone.get(fallback_node, "unknown")

    print(f"  Obstacle simulation:")
    print(f"    BLOCKED:        {blocked_node} (direct path obstructed)")
    print(f"    Fallback:       {fallback_node} (zone: {fallback_zone})")

    # Compute time penalty for taking the fallback route
    blocked_data = zi.nodes_by_name.get(blocked_node, {})
    fallback_data = zi.nodes_by_name.get(fallback_node, {})

    if blocked_data and fallback_data:
        # Distance from crash to blocked node
        d_blocked = math.sqrt(
            (blocked_data["x"] - crash_node["x"]) ** 2 +
            (blocked_data["y"] - crash_node["y"]) ** 2
        )
        # Distance from crash to fallback node
        d_fallback = math.sqrt(
            (fallback_data["x"] - crash_node["x"]) ** 2 +
            (fallback_data["y"] - crash_node["y"]) ** 2
        )
        # Assume robot speed 1.0 m/s
        time_blocked = d_blocked / 1.0
        time_fallback = d_fallback / 1.0
        time_delta = time_fallback - time_blocked
    else:
        d_blocked = 0
        d_fallback = 0
        time_delta = 0

    # Does the fallback still reach the correct zone?
    fallback_zone_correct = fallback_zone == true_zone

    print()
    print(f"  Results:")
    print(f"    Normal zone correct:    {'YES' if normal_zone == true_zone else 'NO'}")
    print(f"    Fallback zone correct:  {'YES' if fallback_zone_correct else 'NO'}")
    print(f"    Distance to blocked:    {d_blocked:.1f}m")
    print(f"    Distance to fallback:   {d_fallback:.1f}m")
    print(f"    Time delta:             +{max(0, time_delta):.2f}s")
    print(f"    Fallback in same zone:  {'YES' if fallback_zone_correct else f'NO ({fallback_zone} vs {true_zone})'}")

    return {
        "test": "recovery_with_obstacle",
        "crash_node": crash_node["name"],
        "true_zone": true_zone,
        "normal_node": normal_node,
        "normal_zone": normal_zone,
        "normal_zone_correct": normal_zone == true_zone,
        "blocked_node": blocked_node,
        "fallback_node": fallback_node,
        "fallback_zone": fallback_zone,
        "fallback_zone_correct": fallback_zone_correct,
        "distance_blocked_m": round(d_blocked, 2),
        "distance_fallback_m": round(d_fallback, 2),
        "time_delta_s": round(max(0, time_delta), 2),
        "normal_time_ms": round(normal_time_ms, 1),
        "candidates": [(c[0], round(c[1], 4)) for c in candidates[:5]],
    }


# ── Main ─────────────────────────────────────────────────────────────

def main():
    os.chdir(PROJECT_ROOT)
    rng = np.random.default_rng(2026)

    print()
    print("  +================================================================+")
    print("  |  MULTI-ROBOT COLD START TEST -- Real Gazebo Raycasts           |")
    print("  |                                                                |")
    print("  |  Test 1: Simultaneous cold start (5 robots)                    |")
    print("  |  Test 2: Fleet learning (shared calibration)                   |")
    print("  |  Test 3: Bottleneck prediction (zone congestion)               |")
    print("  |  Test 4: Recovery with obstacle (blocked path fallback)        |")
    print("  +================================================================+")
    print()

    # Load config
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    nodes = config["nodes"]
    edges = config["edges"]
    zones = config["zones"]
    print(f"  Warehouse: {config['name']}")
    print(f"  Nodes: {len(nodes)}, Edges: {len(edges)}, Zones: {len(zones)}")
    for z in zones:
        print(f"    {z['name']} ({z['type']}): {len(z['nodes'])} nodes")

    # Build lookup maps
    node_to_zone = {}
    for z in zones:
        for nn in z.get("nodes", []):
            node_to_zone[nn] = z["name"]

    # ── Gazebo check ──
    global WORLD_NAME
    if not gz_running():
        print("\n  ERROR: Gazebo is not running.")
        print("  Start it with:")
        print(f"    gz sim -s -r {os.path.join(SCRIPT_DIR, 'worlds', 'warehouse_distinct.sdf')}")
        print("  Then re-run this script.")
        sys.exit(1)

    detected = detect_world_name()
    if detected:
        WORLD_NAME = detected
        print(f"\n  Gazebo: RUNNING (world: {WORLD_NAME})")
    else:
        print(f"\n  Gazebo: RUNNING (world name unknown, using '{DEFAULT_WORLD_NAME}')")

    # Spawn robot if needed
    if not any(ROBOT_NAME in t for t in gz_topics()):
        start_node = nodes[0]
        print(f"  Spawning {ROBOT_NAME} at ({start_node['x']}, {start_node['y']})...")
        spawn_robot(start_node["x"], start_node["y"])
        time.sleep(3)

    lidar_topic = find_lidar_topic()
    if not lidar_topic:
        print("\n  ERROR: No LiDAR topic found.")
        print("  Available topics:")
        for t in gz_topics():
            print(f"    {t}")
        sys.exit(1)
    print(f"  LiDAR topic: {lidar_topic}")

    # ── Build ZoneIdentifier ──
    zi = HierarchicalZoneIdentifier(zones=zones, nodes=nodes, edges=edges)

    # ══════════════════════════════════════════════════════════════════
    # PHASE 0: Calibrate all nodes (Robot_1 does the calibration run)
    # ══════════════════════════════════════════════════════════════════
    print_header("PHASE 0: Calibration (Robot_1 visits all nodes)")
    cal_ok, cal_failed = calibrate(zi, nodes, lidar_topic)

    if cal_ok == 0:
        print("  FATAL: Zero nodes calibrated. Cannot proceed.")
        sys.exit(1)

    # ══════════════════════════════════════════════════════════════════
    # RUN TESTS
    # ══════════════════════════════════════════════════════════════════

    results = {}

    results["test_1"] = test_1_simultaneous_cold_start(
        zi, nodes, zones, node_to_zone, lidar_topic, rng)

    results["test_2"] = test_2_fleet_learning(
        zi, nodes, zones, node_to_zone, lidar_topic, rng)

    results["test_3"] = test_3_bottleneck_prediction(
        zi, nodes, zones, node_to_zone, lidar_topic, rng)

    results["test_4"] = test_4_recovery_with_obstacle(
        zi, nodes, zones, node_to_zone, lidar_topic, rng)

    # ══════════════════════════════════════════════════════════════════
    # SUMMARY
    # ══════════════════════════════════════════════════════════════════
    print_header("SUMMARY")

    t1 = results["test_1"]
    t2 = results["test_2"]
    t3 = results["test_3"]
    t4 = results["test_4"]

    widths_s = [36, 12, 8]
    print_table_row(["Metric", "Result", "Gate"], widths_s)
    print("  " + "  ".join(["-" * w for w in widths_s]))

    print_table_row([
        "T1 zone accuracy",
        f"{t1.get('zone_accuracy_pct', 0):.1f}%",
        "PASS" if t1.get("gate_zone_88", False) else "FAIL",
    ], widths_s)
    print_table_row([
        "T1 fleet recovery time",
        f"{t1.get('fleet_recovery_s', 0):.2f}s",
        "PASS" if t1.get("gate_fleet_10s", False) else "FAIL",
    ], widths_s)
    print_table_row([
        "T2 shared cal zone accuracy",
        f"{t2.get('zone_accuracy_pct', 0):.1f}%",
        "PASS" if t2.get("gate_zone_75", False) else "FAIL",
    ], widths_s)
    print_table_row([
        "T3 bottleneck detected",
        "YES" if t3.get("bottleneck_detected", False) else "NO",
        "PASS" if t3.get("correct_storage_a", False) else "FAIL",
    ], widths_s)
    print_table_row([
        "T4 fallback zone correct",
        "YES" if t4.get("fallback_zone_correct", False) else "NO",
        "PASS" if t4.get("fallback_zone_correct", False) else "FAIL",
    ], widths_s)

    # Overall gate
    all_pass = (
        t1.get("gate_zone_88", False) and
        t1.get("gate_fleet_10s", False) and
        t2.get("gate_zone_75", False) and
        t3.get("correct_storage_a", False) and
        t4.get("fallback_zone_correct", False)
    )
    print()
    print(f"  OVERALL: {'ALL GATES PASS' if all_pass else 'SOME GATES FAILED'}")

    # Save results
    results["calibration"] = {
        "nodes_calibrated": cal_ok,
        "nodes_failed": cal_failed,
        "total_nodes": len(nodes),
    }
    results["overall_pass"] = all_pass

    results_path = os.path.join(SCRIPT_DIR, "multi_robot_results.json")
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Results saved: {results_path}")
    print()


if __name__ == "__main__":
    main()

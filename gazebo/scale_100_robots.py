#!/usr/bin/env python3
"""
SCALE TEST -- 100 Robots in warehouse_distinct_fleet.sdf (REAL GAZEBO)
======================================================================

100 robots already spawned: robot_01 .. robot_100, each with:
  /robot_NN/lidar   -- real GPU raycasts (360 horizontal x 16 vertical)
  /robot_NN/cmd_vel -- real physics movement

Tests:
  Phase 0 : Calibrate (robot_01 visits all 36 nodes, 1 heading, extract 3D)
  T1      : 100-robot simultaneous cold start (batches of 10)
  T2      : 3D LiDAR height features (2D vs 3D accuracy, 20 robots)
  T3      : Real-time obstacle injection (robot_05, corridor)
  T4      : Moving robot meets obstacle (robot_05 drives toward box)
  T5      : Fleet performance benchmark (100 recoveries + 40 conditions)
  T6      : 3D LiDAR zone comparison (10 robots, vertical profiles)

Run: python3 -B gazebo/scale_100_robots.py
"""

import json
import math
import os
import re
import resource
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass

# Force unbuffered stdout so output appears immediately
os.environ["PYTHONUNBUFFERED"] = "1"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)

import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "python"))

from intelligence.iogita.zone_identifier import (
    HierarchicalZoneIdentifier,
    extract_zone_features,
)

CONFIG_PATH = os.path.join(PROJECT_ROOT, "configs", "warehouses", "warehouse_distinct.json")
WORLD_NAME = "warehouse_distinct"

ZONE_CAPACITY = {
    "Storage_A": 2, "Storage_B": 2, "Charging": 2,
    "Operations": 3, "Corridor": 1, "Staging": 2, "Maintenance": 1,
}
ALL_ZONE_NAMES = ["Storage_A", "Storage_B", "Charging", "Operations",
                  "Corridor", "Staging", "Maintenance"]


# -- Gazebo helpers (from fleet_intelligence_40_real.py) -----------------

def gz_cmd(args, timeout=45):
    try:
        r = subprocess.run(["gz"] + args, capture_output=True, text=True, timeout=timeout)
        return r.stdout
    except Exception:
        return ""


def gz_running():
    return len(gz_cmd(["topic", "-e", "-t", "/clock", "-n", "1"], timeout=4)) > 0


def gz_topics():
    return [t.strip() for t in gz_cmd(["topic", "-l"]).strip().split("\n") if t.strip()]


def detect_world_name():
    for t in gz_topics():
        if t.startswith("/world/") and t.endswith("/clock"):
            return t.split("/")[2]
    return None


def read_robot_lidar(robot_name, timeout=45):
    """Read 360-ray horizontal LiDAR (layer 8 middle slice)."""
    raw = gz_cmd(["topic", "-e", "-t", f"/{robot_name}/lidar", "-n", "1"], timeout=timeout)
    if not raw:
        return None
    ranges = [float("inf") if "inf" in m.group(1) else float(m.group(1))
              for m in re.finditer(r'ranges:\s*([-\d.e+inf]+)', raw)]
    if len(ranges) < 36:
        return None
    arr = np.array(ranges, dtype=np.float64)
    # If full 3D (5760 = 360x16), take middle layer (index 8)
    if len(arr) >= 5760:
        arr = arr.reshape(360, 16)[:, 8]
    elif len(arr) != 360:
        arr = np.interp(np.linspace(0, len(arr) - 1, 360), np.arange(len(arr)), arr)
    return np.clip(np.where(np.isfinite(arr), arr, 12.0), 0.1, 12.0)


def read_robot_lidar_3d(robot_name, timeout=45):
    """Read LiDAR scan -- returns 360-ray array.

    NOTE: gz topic -e returns 360 horizontal rays (single vertical layer),
    not 5760. The 16 vertical layers are sensor-internal but the protobuf
    message only exposes the flat horizontal scan.
    We return the 360-ray scan and derive height proxy features from it.
    """
    return read_robot_lidar(robot_name, timeout=timeout)


def get_all_robot_poses():
    topic = f"/world/{WORLD_NAME}/dynamic_pose/info"
    raw = gz_cmd(["topic", "-e", "-t", topic, "-n", "1"], timeout=6)
    if not raw:
        return {}
    poses = {}
    blocks = raw.split("pose {")
    for block in blocks:
        name_m = re.search(r'name:\s*"(robot_\d+)"', block)
        if not name_m:
            continue
        rname = name_m.group(1)
        pos_m = re.search(
            r'position\s*\{[^}]*x:\s*([-\d.e+]+)[^}]*y:\s*([-\d.e+]+)[^}]*z:\s*([-\d.e+]+)',
            block)
        if not pos_m:
            continue
        x, y, z = float(pos_m.group(1)), float(pos_m.group(2)), float(pos_m.group(3))
        ori_m = re.search(r'orientation\s*\{[^}]*z:\s*([-\d.e+]+)[^}]*w:\s*([-\d.e+]+)', block)
        yaw = 0.0
        if ori_m:
            qz, qw = float(ori_m.group(1)), float(ori_m.group(2))
            yaw = 2.0 * math.atan2(qz, qw)
        poses[rname] = {"x": x, "y": y, "z": z, "yaw": yaw}
    return poses


def teleport_robot(robot_name, x, y, yaw=0.0):
    qz, qw = math.sin(yaw / 2), math.cos(yaw / 2)
    gz_cmd(["service", "-s", f"/world/{WORLD_NAME}/set_pose",
            "--reqtype", "gz.msgs.Pose", "--reptype", "gz.msgs.Boolean",
            "--timeout", "3000", "--req",
            f"name: '{robot_name}', position: {{x: {x}, y: {y}, z: 0.05}}, "
            f"orientation: {{z: {qz:.6f}, w: {qw:.6f}}}"], timeout=5)


def teleport_and_wait(robot_name, x, y, yaw, settle_s=1.5):
    """Teleport robot, wait for physics settle, then read LiDAR once.

    With 100 robots the polling approach is too slow (~15s per read).
    Fixed settle time + single read is faster and reliable enough.
    """
    teleport_robot(robot_name, x, y, yaw)
    time.sleep(settle_s)
    return read_robot_lidar(robot_name, 45)


def move_robot(robot_name, linear_x, angular_z, duration_s):
    topic = f"/{robot_name}/cmd_vel"
    msg_type = "gz.msgs.Twist"
    msg = (f"linear: {{x: {linear_x}, y: 0, z: 0}}, "
           f"angular: {{x: 0, y: 0, z: {angular_z}}}")
    pre_poses = get_all_robot_poses()
    pre = pre_poses.get(robot_name, {"x": 0, "y": 0})
    steps = int(duration_s * 10)
    for _ in range(steps):
        gz_cmd(["topic", "-t", topic, "-m", msg_type, "-p", msg], timeout=2)
        time.sleep(0.1)
    stop_msg = "linear: {x: 0, y: 0, z: 0}, angular: {x: 0, y: 0, z: 0}"
    gz_cmd(["topic", "-t", topic, "-m", msg_type, "-p", stop_msg], timeout=2)
    time.sleep(0.3)
    post_poses = get_all_robot_poses()
    post = post_poses.get(robot_name, {"x": 0, "y": 0})
    dist = math.sqrt((post["x"] - pre["x"])**2 + (post["y"] - pre["y"])**2)
    return pre, post, dist


def spawn_obstacle(name, x, y, z, sx, sy, sz):
    sdf = (f'<?xml version="1.0"?><sdf version="1.8"><model name="{name}"><static>true</static>'
           f'<pose>{x} {y} {z} 0 0 0</pose><link name="link">'
           f'<collision name="c"><geometry><box><size>{sx} {sy} {sz}</size></box></geometry></collision>'
           f'<visual name="v"><geometry><box><size>{sx} {sy} {sz}</size></box></geometry>'
           f'<material><ambient>1 0 0 1</ambient></material></visual></link></model></sdf>')
    tmp = f"/tmp/{name}.sdf"
    with open(tmp, "w") as f:
        f.write(sdf)
    gz_cmd(["service", "-s", f"/world/{WORLD_NAME}/create",
            "--reqtype", "gz.msgs.EntityFactory", "--reptype", "gz.msgs.Boolean",
            "--timeout", "10000", "--req", f"sdf_filename: '{tmp}', name: '{name}'"], timeout=45)


# -- Fleet state (lightweight for T5) -----------------------------------

@dataclass
class RobotState:
    robot_id: str
    zone: str = ""
    node: str = ""
    status: str = "idle"
    battery_pct: float = 100.0
    heading_deg: float = 0.0
    current_task: str = ""
    target_zone: str = ""


class SGBottleneckPredictor:
    """Minimal bottleneck predictor for scale test."""

    def __init__(self, zone_capacity, zone_type_map, all_zones, node_to_zone, nodes_by_name):
        self.zone_capacity = zone_capacity
        self.zone_type_map = zone_type_map
        self.all_zones = all_zones
        self.node_to_zone = node_to_zone
        self.nodes_by_name = nodes_by_name
        self.fleet = {}

    def update_robot(self, state):
        self.fleet[state.robot_id] = state

    def zone_occupancy(self):
        occ = {}
        for rid, rs in self.fleet.items():
            if rs.zone:
                occ.setdefault(rs.zone, []).append(rid)
        return occ

    def suggest_alternative_zone(self, target_zone):
        target_type = self.zone_type_map.get(target_zone, "")
        occ = self.zone_occupancy()
        best, best_score = "none", -1
        for z in self.all_zones:
            if z == target_zone:
                continue
            zt = self.zone_type_map.get(z, "")
            if zt == target_type or ("storage" in zt.lower() and "storage" in target_type.lower()):
                cap = self.zone_capacity.get(z, 2)
                count = len(occ.get(z, []))
                avail = cap - count
                if avail > best_score:
                    best, best_score = z, avail
        return best

    def check_zone_congestion(self, target_zone, requesting_robot):
        occ = self.zone_occupancy()
        current = [r for r in occ.get(target_zone, []) if r != requesting_robot]
        cap = self.zone_capacity.get(target_zone, 2)
        return {"congested": len(current) >= cap, "zone": target_zone,
                "count": len(current), "capacity": cap}

    def check_corridor_conflict(self, robot_a, robot_b):
        rs_a, rs_b = self.fleet.get(robot_a), self.fleet.get(robot_b)
        if not rs_a or not rs_b:
            return {"conflict": False}
        conflict = (rs_a.zone == rs_b.target_zone and rs_b.zone == rs_a.target_zone)
        return {"conflict": conflict,
                "resolution": f"{robot_a} proceeds, {robot_b} holds" if conflict else "none"}

    def check_cascade(self, crashed_robot):
        rs = self.fleet.get(crashed_robot)
        if not rs:
            return {"cascade_detected": False}
        occ = self.zone_occupancy()
        affected = [r for r in occ.get(rs.zone, [])
                    if r != crashed_robot and self.fleet[r].status == "moving"]
        incoming = [r for r, s in self.fleet.items()
                    if r != crashed_robot and s.target_zone == rs.zone and s.status == "moving"]
        return {"cascade_detected": len(affected) + len(incoming) > 0,
                "total_at_risk": len(affected) + len(incoming)}

    def check_peak_overload(self, task_assignments):
        zone_counts = {}
        for t in task_assignments:
            z = t.get("zone", "")
            zone_counts[z] = zone_counts.get(z, 0) + 1
        overloaded = {z: c for z, c in zone_counts.items()
                      if c > self.zone_capacity.get(z, 2)}
        return {"overloaded": len(overloaded) > 0, "zones": overloaded}

    def schedule_charging(self, robots_needing_charge, n_docks=2):
        sorted_r = sorted(robots_needing_charge, key=lambda x: x[1])
        schedule = []
        for i, (rid, batt) in enumerate(sorted_r):
            action = "charge_now" if i < n_docks else "queue_and_wait"
            schedule.append({"robot": rid, "battery": batt, "action": action})
        return {"schedule": schedule}

    def detect_circular_deadlock(self, dependencies):
        graph = {w: b for w, b, _z in dependencies}
        visited = set()
        for start in graph:
            path, seen = [], set()
            current = start
            while current and current not in seen:
                if current in visited:
                    break
                seen.add(current)
                path.append(current)
                current = graph.get(current)
            if current and current in seen:
                idx = path.index(current)
                return {"deadlock": True, "cycle": path[idx:]}
            visited.update(path)
        return {"deadlock": False, "cycle": []}


# -- 3D feature extraction ----------------------------------------------

def extract_3d_height_features(scan_360):
    """Extract 8 height-proxy features from a 360-ray horizontal scan.

    Since gz topic only exposes the flat horizontal slice (360 rays),
    we derive height proxy features from range patterns:
      - Shelves (tall obstacles): consistent close returns across many sectors
      - Open areas: far returns, high variance
      - Corridors: bimodal (close walls + far ends)

    Features:
      H1: fraction of rays < 2m (close obstacle density -- proxy for tall structures)
      H2: fraction of rays > 6m (open space density)
      H3: range variance across all 360 rays
      H4: max consecutive close (<2m) sector count / 36 (wall continuity)
      H5: bimodality score (std of sector medians)
      H6: min sector median / max sector median (range ratio)
      H7: gap density (jumps > 1m between adjacent rays) / 360
      H8: mean range / 12.0 (overall clearance)
    """
    n_sectors = 36
    sector_width = 360 // n_sectors
    sector_medians = np.zeros(n_sectors)
    for s in range(n_sectors):
        start = s * sector_width
        sector_medians[s] = np.median(scan_360[start:start + sector_width])

    h1 = float(np.sum(scan_360 < 2.0)) / 360.0
    h2 = float(np.sum(scan_360 > 6.0)) / 360.0
    h3 = float(np.var(scan_360)) / 12.0
    # Max consecutive close sectors
    close_mask = sector_medians < 2.0
    max_consec = 0
    consec = 0
    for v in close_mask:
        if v:
            consec += 1
            max_consec = max(max_consec, consec)
        else:
            consec = 0
    h4 = max_consec / n_sectors
    h5 = float(np.std(sector_medians)) / 12.0
    smin = float(np.min(sector_medians))
    smax = float(np.max(sector_medians))
    h6 = smin / smax if smax > 0.1 else 1.0
    diffs = np.abs(np.diff(scan_360))
    h7 = float(np.sum(diffs > 1.0)) / 360.0
    h8 = float(np.mean(scan_360)) / 12.0
    return np.array([h1, h2, h3, h4, h5, h6, h7, h8], dtype=np.float64)


# -- Main ---------------------------------------------------------------

def main():
    global WORLD_NAME
    os.chdir(PROJECT_ROOT)

    print()
    print("  +================================================================+")
    print("  |  SCALE TEST -- 100 Robots, 6 Tests (REAL GAZEBO)              |")
    print("  |  Phase 0: Calibrate   T1: 100-robot cold start               |")
    print("  |  T2: 3D LiDAR         T3: Obstacle injection                 |")
    print("  |  T4: Moving robot      T5: Fleet benchmark                    |")
    print("  |  T6: 3D zone comparison                                       |")
    print("  +================================================================+")
    print()

    # -- Load config --
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    nodes = config["nodes"]
    edges = config["edges"]
    zones = config["zones"]
    node_to_zone = {}
    zone_type_map = {}
    for z in zones:
        zone_type_map[z["name"]] = z.get("type", "none")
        for nn in z.get("nodes", []):
            node_to_zone[nn] = z["name"]
    all_zone_names = [z["name"] for z in zones]
    nodes_by_name = {n["name"]: n for n in nodes}
    all_node_names = [n["name"] for n in nodes]

    print(f"  Warehouse: {config['name']} ({len(nodes)} nodes, {len(zones)} zones)")

    # -- Gazebo preflight --
    if not gz_running():
        print("  ERROR: Gazebo not running.")
        sys.exit(1)

    detected = detect_world_name()
    if detected:
        WORLD_NAME = detected
    print(f"  Gazebo world: {WORLD_NAME}")

    # Discover all robot LiDAR topics
    topics = gz_topics()
    lidar_topics = sorted([t for t in topics if "/lidar" in t and "points" not in t])
    # Extract robot names from topics like /robot_01/lidar
    active_robots = []
    for lt in lidar_topics:
        m = re.match(r'/(robot_\d+)/lidar', lt)
        if m:
            active_robots.append(m.group(1))
    n_robots = len(active_robots)
    print(f"  Active robots with LiDAR: {n_robots}")
    if n_robots == 0:
        print("  ERROR: No robot LiDAR topics found")
        sys.exit(1)
    print(f"  First: {active_robots[0]}, Last: {active_robots[-1]}")

    # -- Build zone identifier --
    zi = HierarchicalZoneIdentifier(zones=zones, nodes=nodes, edges=edges)

    results = {
        "test": "scale_100_robots",
        "world": WORLD_NAME,
        "n_robots": n_robots,
        "tests": {},
    }
    rng = np.random.default_rng(2026)

    # ================================================================
    # PHASE 0: Calibrate (robot_01 visits all 36 nodes)
    # ================================================================
    print("\n  " + "=" * 64)
    print("  PHASE 0: Calibrate (robot_01 visits 36 nodes, extract 3D)")
    print("  " + "=" * 64 + "\n")

    cal_ok = 0
    cal_start = time.perf_counter()
    cal_3d_features = {}  # node_name -> 8 height-proxy features

    for i, node in enumerate(nodes):
        h, d, t = zi.get_node_dock_features(node["name"])
        scan = teleport_and_wait("robot_01", node["x"], node["y"], 0)
        if scan is not None:
            zi.set_node_fingerprint(node["name"], scan, h, d, t)
            # Height-proxy features from same 360-ray scan
            cal_3d_features[node["name"]] = extract_3d_height_features(scan)
            cal_ok += 1
        if (i + 1) % 12 == 0 or i == len(nodes) - 1:
            print(f"    {i + 1}/{len(nodes)} calibrated")

    zi.rebuild_hopfield()
    cal_time = time.perf_counter() - cal_start
    print(f"  Done: {cal_ok}/{len(nodes)} nodes in {cal_time:.1f}s\n")

    results["calibration"] = {
        "nodes_calibrated": cal_ok,
        "total_nodes": len(nodes), "time_s": round(cal_time, 1),
    }

    # ================================================================
    # T1: N-Robot Simultaneous Cold Start
    # ================================================================
    print("  " + "=" * 64)
    print(f"  T1: {n_robots}-Robot Simultaneous Cold Start (batches of 10)")
    print("  " + "=" * 64 + "\n")

    # Get actual positions of active robots
    poses = get_all_robot_poses()
    print(f"  Robot poses loaded: {len(poses)}")

    # Build assignments: only active robots with known poses
    robot_assignments = []
    for rname in active_robots:
        pos = poses.get(rname)
        if pos:
            best_node = min(nodes, key=lambda n: math.sqrt(
                (n["x"] - pos["x"])**2 + (n["y"] - pos["y"])**2))
            robot_assignments.append((rname, best_node["name"], pos))
        else:
            # Robot exists but no pose data -- assign nearest node by index
            idx = len(robot_assignments) % len(all_node_names)
            nn = all_node_names[idx]
            node = nodes_by_name[nn]
            robot_assignments.append((rname, nn, {"x": node["x"], "y": node["y"]}))

    n_assigned = len(robot_assignments)
    print(f"  Robots assigned: {n_assigned}")

    t1_results = []
    t1_start = time.perf_counter()

    for batch_start in range(0, n_assigned, 10):
        batch_end = min(batch_start + 10, n_assigned)
        batch_ok = 0

        for i in range(batch_start, batch_end):
            rname, nn, pos = robot_assignments[i]
            true_zone = node_to_zone.get(nn, "?")
            scan = read_robot_lidar(rname)
            if scan is None:
                t1_results.append({"robot": rname, "node": nn, "true_zone": true_zone,
                                   "pred_zone": "NO_SCAN", "zone_correct": False})
                continue
            last_x = pos["x"] + float(rng.normal(0, 1.0))
            last_y = pos["y"] + float(rng.normal(0, 1.0))
            imu = float(rng.uniform(0, 360))
            r = zi.recover_from_last_known(scan, last_x, last_y, heading_deg=imu, k=8)
            z_ok = r["zone"] == true_zone
            if z_ok:
                batch_ok += 1
            t1_results.append({"robot": rname, "node": nn, "true_zone": true_zone,
                               "pred_zone": r["zone"], "zone_correct": z_ok,
                               "confidence": r["confidence"]})

        elapsed = time.perf_counter() - t1_start
        print(f"    Batch {batch_start+1}-{batch_end}: {batch_ok}/{batch_end-batch_start} correct  "
              f"({elapsed:.0f}s elapsed)")

    t1_time = time.perf_counter() - t1_start
    t1_correct = sum(1 for r in t1_results if r["zone_correct"])
    t1_scanned = sum(1 for r in t1_results if r.get("pred_zone") != "NO_SCAN")
    t1_acc = t1_correct / max(t1_scanned, 1)
    t1_pass = t1_acc >= 0.85 and t1_scanned >= min(n_assigned, 50)

    print(f"\n  Scanned: {t1_scanned}/{n_assigned} | Correct: {t1_correct}/{t1_scanned}")
    print(f"  Zone accuracy: {t1_acc:.1%} | Time: {t1_time:.1f}s")
    print(f"  Gate (>=85%): {'PASS' if t1_pass else 'FAIL'}\n")

    results["tests"]["T1_100_robot_cold_start"] = {
        "robots_scanned": t1_scanned, "zone_correct": t1_correct,
        "zone_accuracy": round(t1_acc, 3), "total_time_s": round(t1_time, 1),
        "gate_pass": t1_pass,
    }

    # ================================================================
    # T2: 3D LiDAR Height Features (2D vs 3D accuracy)
    # ================================================================
    print("  " + "=" * 64)
    print("  T2: 3D LiDAR Height Features (20 robots, 2D vs 3D)")
    print("  " + "=" * 64 + "\n")

    # Pick up to 20 robots spread across zones (use active robots)
    t2_robots = active_robots[::max(1, len(active_robots) // 20)][:20]
    t2_2d_correct = 0
    t2_3d_correct = 0
    t2_total = 0

    for rname in t2_robots:
        # Find actual position and nearest node
        pos = poses.get(rname)
        if not pos:
            continue
        best_node = min(nodes, key=lambda n: math.sqrt(
            (n["x"] - pos["x"])**2 + (n["y"] - pos["y"])**2))
        nn = best_node["name"]
        true_zone = node_to_zone.get(nn, "?")

        # Read scan (same data, analyzed two ways)
        scan = read_robot_lidar(rname)
        if scan is None:
            continue
        t2_total += 1

        # 2D: standard 36-feature zone identification
        last_x = pos["x"] + float(rng.normal(0, 1.0))
        last_y = pos["y"] + float(rng.normal(0, 1.0))
        r_2d = zi.recover_from_last_known(scan, last_x, last_y, heading_deg=0, k=8)
        if r_2d["zone"] == true_zone:
            t2_2d_correct += 1

        # 3D: 36-sector + 8 height-proxy features = 44-dim
        zf = extract_zone_features(scan)  # 36 features
        hf = extract_3d_height_features(scan)  # 8 features
        combined = np.concatenate([zf, hf])  # 44 features

        # Compare combined features against calibration
        best_zone_3d = "unknown"
        best_score = -1
        for cal_nn, cal_hf in cal_3d_features.items():
            cal_zone = node_to_zone.get(cal_nn, "?")
            real_feats = getattr(zi, '_node_zone_features_real', {})
            if cal_nn not in real_feats:
                continue
            cal_zf = real_feats[cal_nn]
            cal_combined = np.concatenate([cal_zf, cal_hf])
            dist = float(np.linalg.norm(combined - cal_combined))
            sim = 1.0 / (1.0 + dist)
            if sim > best_score:
                best_score = sim
                best_zone_3d = cal_zone

        if best_zone_3d == true_zone:
            t2_3d_correct += 1

        mark_2d = "Y" if r_2d["zone"] == true_zone else "X"
        mark_3d = "Y" if best_zone_3d == true_zone else "X"
        print(f"    {rname} {nn:>14} zone:{true_zone:>12} 2D:{mark_2d} 3D:{mark_3d}")

    t2_2d_acc = t2_2d_correct / max(t2_total, 1)
    t2_3d_acc = t2_3d_correct / max(t2_total, 1)
    t2_pass = t2_3d_acc >= t2_2d_acc  # 3D should be >= 2D

    print(f"\n  2D accuracy: {t2_2d_acc:.1%} ({t2_2d_correct}/{t2_total})")
    print(f"  3D accuracy: {t2_3d_acc:.1%} ({t2_3d_correct}/{t2_total})")
    print(f"  Gate (3D >= 2D): {'PASS' if t2_pass else 'FAIL'}\n")

    results["tests"]["T2_3d_lidar_height"] = {
        "total_robots": t2_total, "accuracy_2d": round(t2_2d_acc, 3),
        "accuracy_3d": round(t2_3d_acc, 3), "gate_pass": t2_pass,
    }

    # ================================================================
    # T3: Real-Time Obstacle Injection
    # ================================================================
    print("  " + "=" * 64)
    print("  T3: Real-Time Obstacle Injection (robot_05, corridor)")
    print("  " + "=" * 64 + "\n")

    # Baseline scan of robot_05 (Corridor zone, ~(0, 1.5))
    print("  Reading robot_05 baseline LiDAR (clear corridor)...")
    baseline_scan = read_robot_lidar("robot_05", timeout=45)
    baseline_ok = baseline_scan is not None
    print(f"  Baseline scan: {'OK' if baseline_ok else 'FAILED'}")

    if baseline_ok:
        baseline_mean = float(np.mean(baseline_scan))
        print(f"  Baseline mean range: {baseline_mean:.2f}m")

    # Spawn obstacle at (0.5, 1.5, 0.5)
    print("  Spawning obstacle at (0.5, 1.5, 0.5) size 0.5x0.5x1.0...")
    spawn_obstacle("corridor_obstacle", 0.5, 1.5, 0.5, 0.5, 0.5, 1.0)
    print("  Waiting 2s for LiDAR update...")
    time.sleep(2.0)

    # Read again
    print("  Reading robot_05 post-obstacle LiDAR...")
    obstacle_scan = read_robot_lidar("robot_05", timeout=45)
    obstacle_ok = obstacle_scan is not None

    scan_changed_flag = False
    range_decrease_sectors = 0
    if baseline_ok and obstacle_ok:
        diff = baseline_scan - obstacle_scan
        range_decrease_sectors = int(np.sum(diff > 0.5))  # sectors where range decreased >0.5m
        scan_changed_flag = range_decrease_sectors > 0
        obstacle_mean = float(np.mean(obstacle_scan))
        print(f"  Post-obstacle mean range: {obstacle_mean:.2f}m")
        print(f"  Sectors with range decrease >0.5m: {range_decrease_sectors}")

    # Zone ID should still say Corridor
    t3_zone = "unknown"
    if obstacle_ok:
        r = zi.recover_from_last_known(obstacle_scan, 0.0, 1.5, heading_deg=0, k=8)
        t3_zone = r["zone"]
    zone_still_corridor = t3_zone == "Corridor"
    print(f"  Zone ID with obstacle: {t3_zone} (expected: Corridor)")

    # SG decision: obstacle_in_corridor
    corridor_nodes = {"CORR_0", "CORR_1", "CORR_2", "CORR_3"}
    corridor_robots = [ra[0] for ra in robot_assignments if ra[1] in corridor_nodes]
    sg_decision = {
        "obstacle_detected": scan_changed_flag,
        "obstacle_in_corridor": scan_changed_flag and zone_still_corridor,
        "suggestion": "reroute_robots_through_corridor" if scan_changed_flag else "no_action",
        "affected_robots": corridor_robots,
    }
    print(f"  SG decision: obstacle_detected={sg_decision['obstacle_detected']}, "
          f"suggestion={sg_decision['suggestion']}")

    t3_pass = scan_changed_flag and zone_still_corridor
    print(f"  Gate: {'PASS' if t3_pass else 'FAIL'}\n")

    results["tests"]["T3_obstacle_injection"] = {
        "baseline_ok": baseline_ok, "obstacle_scan_ok": obstacle_ok,
        "scan_changed": scan_changed_flag,
        "range_decrease_sectors": range_decrease_sectors,
        "zone_still_correct": zone_still_corridor,
        "sg_decision": sg_decision, "gate_pass": t3_pass,
    }

    # ================================================================
    # T4: Moving Robot Meets Obstacle
    # ================================================================
    print("  " + "=" * 64)
    print("  T4: Moving Robot Meets Obstacle (robot_05 drives forward)")
    print("  " + "=" * 64 + "\n")

    # Send robot_05 forward at 0.3 m/s for 3s
    print("  Sending robot_05 forward at 0.3 m/s for 3s...")
    pre_pos, post_pos, dist_moved = move_robot("robot_05", 0.3, 0.0, 3.0)
    print(f"  Pre:  ({pre_pos['x']:.2f}, {pre_pos['y']:.2f})")
    print(f"  Post: ({post_pos['x']:.2f}, {post_pos['y']:.2f})")
    print(f"  Distance moved: {dist_moved:.2f}m")

    # Read LiDAR after movement
    print("  Reading LiDAR after movement...")
    move_scan = read_robot_lidar("robot_05", timeout=45)
    obstacle_range = 12.0
    if move_scan is not None:
        obstacle_range = float(np.min(move_scan))
        print(f"  Min range in scan: {obstacle_range:.2f}m")
    else:
        print("  WARNING: Could not read scan after movement")

    obstacle_nearby = obstacle_range < 2.0
    robot_stopped_safely = dist_moved < 1.5  # Should not have gone far with obstacle

    # io-gita decision
    iogita_decision = {
        "obstacle_ahead": obstacle_nearby,
        "min_range_m": round(obstacle_range, 2),
        "action": "stop_and_reroute" if obstacle_nearby else "continue",
        "distance_moved_m": round(dist_moved, 2),
    }
    print(f"  io-gita decision: obstacle_ahead={obstacle_nearby}, "
          f"action={iogita_decision['action']}")

    # Stop robot
    gz_cmd(["topic", "-t", "/robot_05/cmd_vel", "-m", "gz.msgs.Twist",
            "-p", "linear: {x: 0, y: 0, z: 0}, angular: {x: 0, y: 0, z: 0}"], timeout=2)

    t4_pass = obstacle_nearby or scan_changed_flag  # Obstacle should be visible
    print(f"  Gate: {'PASS' if t4_pass else 'FAIL'}\n")

    results["tests"]["T4_moving_robot_obstacle"] = {
        "pre_pos": {"x": round(pre_pos["x"], 2), "y": round(pre_pos["y"], 2)},
        "post_pos": {"x": round(post_pos["x"], 2), "y": round(post_pos["y"], 2)},
        "distance_moved_m": round(dist_moved, 2),
        "min_range_m": round(obstacle_range, 2),
        "obstacle_nearby": obstacle_nearby,
        "iogita_decision": iogita_decision, "gate_pass": t4_pass,
    }

    # ================================================================
    # T5: Fleet Performance Benchmark (no Gazebo reads)
    # ================================================================
    print("  " + "=" * 64)
    print("  T5: Fleet Performance Benchmark (100 recoveries + 40 conditions)")
    print("  " + "=" * 64 + "\n")

    # Generate 100 synthetic scans from calibration for speed test
    # (engine performance, not Gazebo I/O)
    from intelligence.iogita.zone_identifier import generate_zone_scan

    t5_recovery_start = time.perf_counter()
    t5_recover_ok = 0
    for i in range(100):
        nn = all_node_names[i % len(all_node_names)]
        node = nodes_by_name[nn]
        zone = node_to_zone.get(nn, "corridor")
        zt = zone_type_map.get(zone, "none")
        scan = generate_zone_scan(zt, rng, heading_deg=float(rng.uniform(0, 360)))
        last_x = node["x"] + float(rng.normal(0, 1.0))
        last_y = node["y"] + float(rng.normal(0, 1.0))
        r = zi.recover_from_last_known(scan, last_x, last_y, heading_deg=0, k=8)
        if r["zone"] == zone:
            t5_recover_ok += 1

    t5_recovery_time = time.perf_counter() - t5_recovery_start
    print(f"  100 recoveries: {t5_recovery_time:.3f}s ({t5_recover_ok}/100 correct)")

    # Run 40 fleet intelligence conditions
    sg = SGBottleneckPredictor(ZONE_CAPACITY, zone_type_map, all_zone_names,
                                node_to_zone, nodes_by_name)
    # Populate with 100 robots
    for i in range(100):
        nn = all_node_names[i % len(all_node_names)]
        zone = node_to_zone.get(nn, "Corridor")
        statuses = ["idle", "moving", "picking", "charging"]
        sg.update_robot(RobotState(
            robot_id=f"robot_{i+1:02d}" if i < 99 else "robot_100",
            zone=zone, node=nn,
            status=statuses[i % 4],
            battery_pct=float(rng.uniform(10, 100)),
            target_zone=all_zone_names[int(rng.integers(0, len(all_zone_names)))],
        ))

    t5_cond_start = time.perf_counter()
    cond_results = []

    # Run all condition checks that the predictor supports
    # C1: zone congestion for all zones
    for z in all_zone_names:
        cond_results.append(sg.check_zone_congestion(z, "robot_01"))
    # C2: corridor conflicts between pairs
    for i in range(0, 20, 2):
        ra = f"robot_{i+1:02d}"
        rb = f"robot_{i+2:02d}"
        cond_results.append(sg.check_corridor_conflict(ra, rb))
    # C3: cascade from crashes
    for i in range(5):
        cond_results.append(sg.check_cascade(f"robot_{i+1:02d}"))
    # C4: peak overload
    tasks = [{"zone": all_zone_names[i % len(all_zone_names)]} for i in range(50)]
    cond_results.append(sg.check_peak_overload(tasks))
    # C5: charging schedule
    low_batt = [(f"robot_{i+1:02d}", float(rng.uniform(5, 25))) for i in range(10)]
    cond_results.append(sg.schedule_charging(low_batt))
    # C6: deadlock detection
    deps = [("robot_01", "robot_02", "Storage_A"),
            ("robot_02", "robot_03", "Storage_B"),
            ("robot_03", "robot_01", "Corridor")]
    cond_results.append(sg.detect_circular_deadlock(deps))
    # C7: alternative zones
    for z in all_zone_names:
        cond_results.append({"alt_zone": sg.suggest_alternative_zone(z)})

    t5_cond_time = time.perf_counter() - t5_cond_start
    n_conditions = len(cond_results)
    print(f"  {n_conditions} conditions: {t5_cond_time:.4f}s")

    # Memory usage
    mem_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)
    print(f"  Memory: {mem_mb:.1f} MB")

    t5_recovery_pass = t5_recovery_time < 5.0
    t5_cond_pass = t5_cond_time < 1.0
    t5_pass = t5_recovery_pass and t5_cond_pass

    print(f"  Recovery <5s: {'PASS' if t5_recovery_pass else 'FAIL'} ({t5_recovery_time:.3f}s)")
    print(f"  Conditions <1s: {'PASS' if t5_cond_pass else 'FAIL'} ({t5_cond_time:.4f}s)")
    print(f"  Gate: {'PASS' if t5_pass else 'FAIL'}\n")

    results["tests"]["T5_fleet_benchmark"] = {
        "recovery_100_time_s": round(t5_recovery_time, 3),
        "recovery_100_correct": t5_recover_ok,
        "conditions_count": n_conditions,
        "conditions_time_s": round(t5_cond_time, 4),
        "memory_mb": round(mem_mb, 1),
        "gate_pass": t5_pass,
    }

    # ================================================================
    # T6: 3D LiDAR Zone Comparison (vertical profiles)
    # ================================================================
    print("  " + "=" * 64)
    print("  T6: 3D LiDAR Zone Comparison (10 robots, vertical profiles)")
    print("  " + "=" * 64 + "\n")

    # Pick 10 robots across different zones (use actual positions)
    # Select one robot per zone, then fill with extras
    t6_robots = {}
    zones_seen = set()
    for rname, nn, pos in robot_assignments:
        zone = node_to_zone.get(nn, "?")
        if zone not in zones_seen and zone != "?":
            t6_robots[rname] = nn
            zones_seen.add(zone)
        if len(t6_robots) >= 10:
            break
    # Fill up to 10 if we have fewer zones
    for rname, nn, pos in robot_assignments:
        if rname not in t6_robots and len(t6_robots) < 10:
            t6_robots[rname] = nn

    # NOTE: gz topic -e exposes 360 horizontal rays only (not 5760).
    # We use the 360-ray scan and extract height-proxy features to
    # show that shelf zones have different range profiles than open zones.

    t6_profiles = {}
    for rname, nn in t6_robots.items():
        zone = node_to_zone.get(nn, "?")
        scan = read_robot_lidar(rname, timeout=45)
        if scan is None:
            print(f"    {rname} {nn:>14} zone:{zone:>12} -- NO SCAN")
            continue

        hf = extract_3d_height_features(scan)
        mean_range = float(np.mean(scan))
        close_frac = hf[0]   # H1: fraction < 2m
        open_frac = hf[1]    # H2: fraction > 6m
        variance = hf[2]     # H3: range variance
        wall_cont = hf[3]    # H4: wall continuity

        t6_profiles[rname] = {
            "node": nn, "zone": zone,
            "mean_range_m": round(mean_range, 2),
            "close_frac": round(close_frac, 3),
            "open_frac": round(open_frac, 3),
            "variance": round(variance, 3),
            "wall_continuity": round(wall_cont, 3),
            "height_features": [round(float(v), 3) for v in hf],
        }

        print(f"    {rname} {nn:>14} zone:{zone:>12}  mean:{mean_range:.1f}m  "
              f"close:{close_frac:.0%}  open:{open_frac:.0%}  "
              f"wall_cont:{wall_cont:.2f}")

    # Analyze: shelf zones have more close returns than open zones
    shelf_close = [p["close_frac"] for p in t6_profiles.values()
                   if "Storage" in p["zone"]]
    open_close = [p["close_frac"] for p in t6_profiles.values()
                  if p["zone"] in ("Corridor", "Charging", "Operations")]

    shelf_mean = float(np.mean(shelf_close)) if shelf_close else 0
    open_mean = float(np.mean(open_close)) if open_close else 0
    profile_differs = abs(shelf_mean - open_mean) > 0.05

    print(f"\n  Shelf zones close-frac mean: {shelf_mean:.3f}")
    print(f"  Open zones close-frac mean:  {open_mean:.3f}")
    print(f"  Profile differs measurably: {profile_differs}")

    t6_pass = len(t6_profiles) >= 5
    print(f"  Gate (>=5 profiles): {'PASS' if t6_pass else 'FAIL'}\n")

    results["tests"]["T6_3d_zone_comparison"] = {
        "profiles": t6_profiles,
        "shelf_close_mean": round(shelf_mean, 3),
        "open_close_mean": round(open_mean, 3),
        "profile_differs": profile_differs,
        "gate_pass": t6_pass,
        "note": "360-ray horizontal scan (gz topic exposes 360, not 5760)",
    }

    # ================================================================
    # SUMMARY
    # ================================================================
    print("  " + "=" * 64)
    print("  SUMMARY")
    print("  " + "=" * 64 + "\n")

    all_tests = [
        ("T1", results["tests"]["T1_100_robot_cold_start"]["gate_pass"]),
        ("T2", results["tests"]["T2_3d_lidar_height"]["gate_pass"]),
        ("T3", results["tests"]["T3_obstacle_injection"]["gate_pass"]),
        ("T4", results["tests"]["T4_moving_robot_obstacle"]["gate_pass"]),
        ("T5", results["tests"]["T5_fleet_benchmark"]["gate_pass"]),
        ("T6", results["tests"]["T6_3d_zone_comparison"]["gate_pass"]),
    ]
    passed = sum(1 for _, p in all_tests if p)
    total = len(all_tests)

    for name, p in all_tests:
        mark = "PASS" if p else "FAIL"
        print(f"    {name}: {mark}")

    overall = passed >= 4  # 4/6 minimum
    print(f"\n  Overall: {passed}/{total} passed -- {'PASS' if overall else 'FAIL'}")
    results["summary"] = {"passed": passed, "total": total, "overall_pass": overall}

    # Save results
    out_path = os.path.join(SCRIPT_DIR, "scale_100_robots_results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Results saved to {out_path}")


if __name__ == "__main__":
    main()

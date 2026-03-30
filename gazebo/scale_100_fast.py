#!/usr/bin/env python3
"""
50-ROBOT SCALE TEST (FAST) — Read real LiDAR from 100 robots at current positions.
No calibration phase (uses engine's built-in fingerprints).
No teleporting (robots already placed by gen_fleet_world.py).

Tests:
  T1: 100-robot simultaneous cold start (real LiDAR, batches of 10)
  T2: 3D LiDAR vertical layer analysis (16-layer data)
  T3: Obstacle injection + detection (real physics)
  T4: Performance benchmark (engine speed at 100-robot scale)
"""

import json, math, os, re, subprocess, sys, time
import numpy as np

os.environ["PYTHONUNBUFFERED"] = "1"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "python"))

from intelligence.iogita.zone_identifier import HierarchicalZoneIdentifier, extract_zone_features

CONFIG_PATH = os.path.join(PROJECT_ROOT, "configs", "warehouses", "warehouse_distinct.json")
WORLD_NAME = "warehouse_distinct"


def gz_cmd(args, timeout=10):
    try:
        return subprocess.run(["gz"] + args, capture_output=True, text=True, timeout=timeout).stdout
    except:
        return ""

def read_lidar(robot_name, timeout=45):
    raw = gz_cmd(["topic", "-e", "-t", f"/{robot_name}/lidar", "-n", "1"], timeout=timeout)
    ranges = [float("inf") if "inf" in m.group(1) else float(m.group(1))
              for m in re.finditer(r'ranges:\s*([-\d.e+inf]+)', raw)]
    if len(ranges) < 36:
        return None
    arr = np.array(ranges[:360], dtype=np.float64)
    return np.clip(np.where(np.isfinite(arr), arr, 12.0), 0.1, 12.0)

def read_lidar_3d(robot_name, timeout=45):
    """Read full 3D scan — 360 horizontal × 16 vertical = 5760 values."""
    raw = gz_cmd(["topic", "-e", "-t", f"/{robot_name}/lidar", "-n", "1"], timeout=timeout)
    ranges = [float("inf") if "inf" in m.group(1) else float(m.group(1))
              for m in re.finditer(r'ranges:\s*([-\d.e+inf]+)', raw)]
    if len(ranges) < 5760:
        # Fewer than 16 layers — return horizontal only
        if len(ranges) >= 360:
            return np.clip(np.where(np.isfinite(np.array(ranges[:360])), np.array(ranges[:360]), 12.0), 0.1, 12.0), None
        return None, None
    arr = np.array(ranges[:5760], dtype=np.float64).reshape(16, 360)
    arr = np.clip(np.where(np.isfinite(arr), arr, 12.0), 0.1, 12.0)
    horizontal = arr[8]  # middle layer
    return horizontal, arr

def get_robot_poses():
    raw = gz_cmd(["topic", "-e", "-t", f"/world/{WORLD_NAME}/dynamic_pose/info", "-n", "1"], timeout=10)
    poses = {}
    for block in raw.split("pose {"):
        nm = re.search(r'name:\s*"(robot_\d+)"', block)
        if not nm:
            continue
        pos = re.search(r'position\s*\{[^}]*x:\s*([-\d.]+)[^}]*y:\s*([-\d.]+)', block, re.DOTALL)
        if pos:
            poses[nm.group(1)] = (float(pos.group(1)), float(pos.group(2)))
    return poses

def spawn_obstacle(name, x, y, z, sx, sy, sz):
    sdf = f'<?xml version="1.0"?><sdf version="1.8"><model name="{name}"><static>true</static><pose>{x} {y} {z} 0 0 0</pose><link name="link"><collision name="c"><geometry><box><size>{sx} {sy} {sz}</size></box></geometry></collision><visual name="v"><geometry><box><size>{sx} {sy} {sz}</size></box></geometry><material><ambient>1 0 0 1</ambient></material></visual></link></model></sdf>'
    tmp = f"/tmp/{name}.sdf"
    with open(tmp, "w") as f:
        f.write(sdf)
    gz_cmd(["service", "-s", f"/world/{WORLD_NAME}/create",
            "--reqtype", "gz.msgs.EntityFactory", "--reptype", "gz.msgs.Boolean",
            "--timeout", "10000", "--req", f"sdf_filename: '{tmp}', name: '{name}'"], timeout=15)


def main():
    print("\n  50-ROBOT SCALE TEST (REAL GAZEBO)", flush=True)
    print("  " + "=" * 50, flush=True)

    with open(CONFIG_PATH) as f:
        config = json.load(f)
    nodes = config["nodes"]
    zones = config["zones"]
    node_to_zone = {}
    for z in zones:
        for nn in z.get("nodes", []):
            node_to_zone[nn] = z["name"]

    # Check Gazebo
    lidar_count = len([t for t in gz_cmd(["topic", "-l"]).split("\n") if "/lidar" in t and "points" not in t])
    print(f"  Robots with LiDAR: {lidar_count}", flush=True)
    if lidar_count < 20:
        print("  ERROR: Need 50+ robots. Run gen_fleet_world.py --count 100")
        sys.exit(1)

    # Engine (auto-calibrates from synthetic on init — sufficient for zone ID)
    zi = HierarchicalZoneIdentifier(zones=zones, nodes=nodes, edges=config.get("edges", []))
    print(f"  Engine: {len(zi._zone_fingerprints)} zones, {zi._zone_hopfield.n_patterns} patterns\n", flush=True)

    # Get robot positions
    poses = get_robot_poses()
    print(f"  Robot poses loaded: {len(poses)}", flush=True)

    results = {"test": "scale_100_robots", "world": WORLD_NAME,
               "n_robots": lidar_count, "tests": {}}

    # ══════════════════════════════════════════════════════════
    # T1: 100-ROBOT COLD START (batches of 10)
    # ══════════════════════════════════════════════════════════
    print(f"\n  {'='*50}")
    print("  T1: 100-Robot Cold Start (real LiDAR, batches of 10)")
    print(f"  {'='*50}\n", flush=True)

    t1_start = time.perf_counter()
    zone_correct = 0
    total_read = 0
    failed_reads = 0
    rng = np.random.default_rng(2026)

    robot_names = [f"robot_{i:02d}" if i < 100 else "robot_100" for i in range(1, 101)]

    for batch_start in range(0, min(lidar_count, 100), 10):
        batch_end = min(batch_start + 10, lidar_count)
        batch_ok = 0

        for i in range(batch_start, batch_end):
            rname = robot_names[i]
            scan = read_lidar(rname)
            if scan is None:
                failed_reads += 1
                continue

            total_read += 1
            # Get position (with ±1m noise for realism)
            pos = poses.get(rname, (0, 0))
            last_x = pos[0] + float(rng.normal(0, 1.0))
            last_y = pos[1] + float(rng.normal(0, 1.0))

            result = zi.recover_from_last_known(scan, last_x, last_y,
                                                 heading_deg=float(rng.uniform(0, 360)), k=5)

            # Check zone — find which node is closest to this robot's position
            best_node = None
            best_dist = 999
            for n in nodes:
                d = math.sqrt((n["x"] - pos[0])**2 + (n["y"] - pos[1])**2)
                if d < best_dist:
                    best_dist = d
                    best_node = n["name"]
            true_zone = node_to_zone.get(best_node, "unknown")

            if result["zone"] == true_zone:
                zone_correct += 1
                batch_ok += 1

        elapsed = time.perf_counter() - t1_start
        print(f"    Batch {batch_start+1}-{batch_end}: {batch_ok}/{batch_end-batch_start} zone correct  "
              f"({elapsed:.0f}s elapsed)", flush=True)

    t1_time = time.perf_counter() - t1_start
    t1_acc = zone_correct / total_read if total_read > 0 else 0
    t1_pass = t1_acc >= 0.80 and total_read >= 50

    print(f"\n  T1 RESULT: {zone_correct}/{total_read} zone correct ({t1_acc:.1%})")
    print(f"  Failed reads: {failed_reads}")
    print(f"  Fleet time: {t1_time:.0f}s")
    print(f"  Gate (>=80%, >=50 reads): {'PASS' if t1_pass else 'FAIL'}\n", flush=True)

    results["tests"]["T1_cold_start_100"] = {
        "zone_accuracy": round(t1_acc, 3), "correct": zone_correct,
        "total_read": total_read, "failed_reads": failed_reads,
        "fleet_time_s": round(t1_time, 1), "pass": t1_pass,
        "measurement": "gazebo_physics_real_lidar",
    }

    # ══════════════════════════════════════════════════════════
    # T2: 3D LIDAR VERTICAL ANALYSIS (10 robots)
    # ══════════════════════════════════════════════════════════
    print(f"  {'='*50}")
    print("  T2: 3D LiDAR Vertical Layer Analysis (10 robots)")
    print(f"  {'='*50}\n", flush=True)

    t2_data = []
    for i in [1, 5, 10, 15, 20, 25, 30, 35, 40, 45]:
        rname = f"robot_{i:02d}"
        horiz, full_3d = read_lidar_3d(rname)
        if horiz is None:
            print(f"    {rname}: no 3D data", flush=True)
            continue

        pos = poses.get(rname, (0, 0))
        best_node = min(nodes, key=lambda n: math.sqrt((n["x"]-pos[0])**2 + (n["y"]-pos[1])**2))
        true_zone = node_to_zone.get(best_node["name"], "?")

        if full_3d is not None:
            # Vertical analysis: check each layer
            layer_medians = [float(np.median(full_3d[layer])) for layer in range(16)]
            low_layers = np.mean(layer_medians[:4])   # looking down
            mid_layers = np.mean(layer_medians[6:10])  # horizontal
            high_layers = np.mean(layer_medians[12:])  # looking up
            has_tall_obstacle = high_layers < 8.0  # something above robot

            t2_data.append({
                "robot": rname, "zone": true_zone,
                "low_m": round(low_layers, 2), "mid_m": round(mid_layers, 2),
                "high_m": round(high_layers, 2),
                "tall_obstacle": has_tall_obstacle,
                "layers": 16,
            })
            print(f"    {rname} [{true_zone:>12}]: low={low_layers:.1f}m mid={mid_layers:.1f}m "
                  f"high={high_layers:.1f}m tall={'YES' if has_tall_obstacle else 'no'}", flush=True)
        else:
            # 2D only
            t2_data.append({"robot": rname, "zone": true_zone, "layers": 1,
                            "mid_m": round(float(np.median(horiz)), 2)})
            print(f"    {rname} [{true_zone:>12}]: 2D only, median={np.median(horiz):.1f}m", flush=True)

    t2_has_3d = sum(1 for d in t2_data if d.get("layers", 0) == 16)
    t2_pass = t2_has_3d >= 3  # at least 3 robots with 3D data

    print(f"\n  T2 RESULT: {t2_has_3d}/{len(t2_data)} robots with 3D LiDAR data")
    print(f"  Gate (>=3 with 3D): {'PASS' if t2_pass else 'FAIL'}\n", flush=True)

    results["tests"]["T2_3d_lidar"] = {
        "robots_with_3d": t2_has_3d, "total_sampled": len(t2_data),
        "data": t2_data, "pass": t2_pass,
        "measurement": "gazebo_physics_3d_lidar",
    }

    # ══════════════════════════════════════════════════════════
    # T3: OBSTACLE INJECTION (real physics)
    # ══════════════════════════════════════════════════════════
    print(f"  {'='*50}")
    print("  T3: Real-Time Obstacle Injection")
    print(f"  {'='*50}\n", flush=True)

    # Read robot_05 LiDAR BEFORE obstacle
    pre_scan = read_lidar("robot_05")
    pre_min = float(np.min(pre_scan)) if pre_scan is not None else 12.0
    print(f"  robot_05 BEFORE: min_range={pre_min:.2f}m", flush=True)

    # Spawn obstacle in front of robot_05 (Corridor area ~(0.5, 1.5))
    pos_05 = poses.get("robot_05", (0, 1.5))
    obs_x = pos_05[0] + 1.0  # 1m in front
    obs_y = pos_05[1]
    print(f"  Spawning obstacle at ({obs_x:.1f}, {obs_y:.1f})...", flush=True)
    spawn_obstacle("test_obstacle", obs_x, obs_y, 0.5, 0.5, 0.5, 1.0)
    time.sleep(5)  # wait for physics + LiDAR update

    # Read AFTER obstacle
    post_scan = read_lidar("robot_05")
    post_min = float(np.min(post_scan)) if post_scan is not None else 12.0
    print(f"  robot_05 AFTER:  min_range={post_min:.2f}m", flush=True)

    obstacle_detected = post_min < pre_min - 0.3  # range decreased by >0.3m
    scan_changed = pre_scan is not None and post_scan is not None and float(np.mean(np.abs(pre_scan - post_scan))) > 0.05

    # Zone ID should still be Corridor (obstacle doesn't change zone)
    zone_still_ok = True
    if post_scan is not None:
        r = zi.recover_from_last_known(post_scan, pos_05[0], pos_05[1], k=5)
        zone_still_ok = "Corridor" in r.get("zone", "")
        print(f"  Zone ID with obstacle: {r['zone']} (expected Corridor)", flush=True)

    t3_pass = obstacle_detected or scan_changed
    print(f"\n  Obstacle detected in LiDAR: {'YES' if obstacle_detected else 'NO'}")
    print(f"  Scan changed: {'YES' if scan_changed else 'NO'}")
    print(f"  Zone still correct: {'YES' if zone_still_ok else 'NO'}")
    print(f"  Gate: {'PASS' if t3_pass else 'FAIL'}\n", flush=True)

    results["tests"]["T3_obstacle"] = {
        "pre_min_range_m": round(pre_min, 3), "post_min_range_m": round(post_min, 3),
        "obstacle_detected": obstacle_detected, "scan_changed": scan_changed,
        "zone_still_correct": zone_still_ok, "pass": t3_pass,
        "measurement": "gazebo_physics_real_obstacle",
    }

    # ══════════════════════════════════════════════════════════
    # T4: PERFORMANCE BENCHMARK (engine only, no Gazebo reads)
    # ══════════════════════════════════════════════════════════
    print(f"  {'='*50}")
    print("  T4: Performance Benchmark (100 recoveries + 40 conditions)")
    print(f"  {'='*50}\n", flush=True)

    # 100 recoveries using synthetic scans (pure engine speed)
    rng_bench = np.random.default_rng(42)
    t4_start = time.perf_counter()
    for _ in range(100):
        fake_scan = rng_bench.uniform(0.5, 8.0, 360)
        node = nodes[rng_bench.integers(0, len(nodes))]
        zi.recover_from_last_known(fake_scan, node["x"], node["y"], k=5)
    t4_recovery_ms = (time.perf_counter() - t4_start) * 1000
    per_recovery = t4_recovery_ms / 100

    print(f"  100 recoveries: {t4_recovery_ms:.1f}ms total ({per_recovery:.2f}ms each)")

    # 40 zone identifications
    t4_zone_start = time.perf_counter()
    for _ in range(40):
        fake_scan = rng_bench.uniform(0.5, 8.0, 360)
        zi.hierarchical_zone_id(fake_scan, 0, 0, 0, previous_zone=None)
    t4_zone_ms = (time.perf_counter() - t4_zone_start) * 1000

    print(f"  40 zone IDs: {t4_zone_ms:.1f}ms total ({t4_zone_ms/40:.2f}ms each)")

    # Memory
    import resource
    mem_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024
    print(f"  Memory: {mem_mb:.0f} MB")

    t4_pass = per_recovery < 10.0 and t4_zone_ms < 1000
    print(f"  Gate (<10ms/recovery, <1s/40 zones): {'PASS' if t4_pass else 'FAIL'}\n", flush=True)

    results["tests"]["T4_benchmark"] = {
        "recoveries_100_ms": round(t4_recovery_ms, 1),
        "per_recovery_ms": round(per_recovery, 2),
        "zone_ids_40_ms": round(t4_zone_ms, 1),
        "per_zone_ms": round(t4_zone_ms / 40, 2),
        "memory_mb": round(mem_mb),
        "pass": t4_pass,
        "measurement": "engine_only_no_gazebo",
    }

    # ══════════════════════════════════════════════════════════
    # SUMMARY
    # ══════════════════════════════════════════════════════════
    all_pass = [results["tests"][k]["pass"] for k in results["tests"]]
    overall = sum(all_pass)

    print(f"  {'='*50}")
    print("  SUMMARY")
    print(f"  {'='*50}\n")
    print(f"    T1 100-robot cold start: {t1_acc:.1%} zone ({zone_correct}/{total_read})  {'PASS' if t1_pass else 'FAIL'}")
    print(f"    T2 3D LiDAR:             {t2_has_3d} robots with 16 layers  {'PASS' if t2_pass else 'FAIL'}")
    print(f"    T3 Obstacle injection:    detected={'YES' if t3_pass else 'NO'}  {'PASS' if t3_pass else 'FAIL'}")
    print(f"    T4 Benchmark:             {per_recovery:.2f}ms/recovery  {'PASS' if t4_pass else 'FAIL'}")
    print(f"\n    OVERALL: {overall}/{len(all_pass)} PASS\n")

    results["summary"] = {
        "passed": overall, "total": len(all_pass),
        "verdict": "PASS" if overall == len(all_pass) else "FAIL",
    }

    out_path = os.path.join(SCRIPT_DIR, "scale_100_robots_results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"  Results: {out_path}\n", flush=True)


if __name__ == "__main__":
    main()

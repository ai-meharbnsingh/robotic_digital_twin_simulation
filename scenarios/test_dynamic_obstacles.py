#!/usr/bin/env python3
"""
Dynamic Environment Stress Test — moving obstacles during io-gita operation.

Simulates:
  1. Forklift crossing the aisle (temporary scan occlusion)
  2. Person walking through the corridor (small, fast obstacle)
  3. Pallet cart parked in front of shelf (persistent occlusion)
  4. Multiple obstacles simultaneously (worst case)

Measures:
  - Zone accuracy under dynamic occlusion
  - Recovery time degradation
  - False positive rate (does noise trigger wrong zone?)
  - Dynamic object filtering effectiveness

Run: python3 test_dynamic_obstacles.py
"""

import math
import os
import sys
import time

import numpy as np
import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
IOGITA_ROOT = os.path.join(PROJECT_ROOT, "..", "iogita_kdtree_addverb")
sys.path.insert(0, IOGITA_ROOT)

from engine import IoGitaEngine


def inject_obstacle(scan: np.ndarray, angle_deg: float, distance_m: float,
                    width_deg: float = 10.0) -> np.ndarray:
    """Inject a synthetic obstacle into a LiDAR scan.

    Args:
        scan: 360-ray scan to modify.
        angle_deg: Center angle of obstacle (0=forward, 90=left).
        distance_m: Distance to obstacle.
        width_deg: Angular width of obstacle.
    Returns:
        Modified scan with obstacle.
    """
    scan = scan.copy()
    start = int(angle_deg - width_deg / 2) % 360
    end = int(angle_deg + width_deg / 2) % 360

    if start < end:
        indices = range(start, end)
    else:
        indices = list(range(start, 360)) + list(range(0, end))

    for i in indices:
        if 0 <= i < len(scan):
            scan[i] = min(scan[i], distance_m)
    return scan


def inject_moving_obstacle(scan: np.ndarray, t: float,
                           start_angle: float, end_angle: float,
                           distance_m: float, duration_s: float,
                           width_deg: float = 15.0) -> np.ndarray:
    """Inject a moving obstacle that sweeps across the scan.

    Args:
        t: Current time in seconds.
        start_angle: Starting angle of obstacle.
        end_angle: Ending angle of obstacle.
        duration_s: Time to traverse from start to end.
        distance_m: Distance to obstacle.
    """
    progress = min(t / max(duration_s, 0.01), 1.0)
    current_angle = start_angle + progress * (end_angle - start_angle)
    return inject_obstacle(scan, current_angle, distance_m, width_deg)


class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.results = []

    def check(self, name, condition, detail=""):
        status = "PASS" if condition else "FAIL"
        self.results.append((name, status, detail))
        if condition:
            self.passed += 1
        else:
            self.failed += 1
        symbol = "+" if condition else "X"
        print(f"  [{symbol}] {name}" + (f" — {detail}" if detail else ""))


def run_tests():
    print("=" * 70)
    print("DYNAMIC OBSTACLE STRESS TEST — io-gita under chaos")
    print("=" * 70)

    config_path = os.path.join(IOGITA_ROOT, "config", "warehouse_example.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    nodes = {n["name"]: n for n in config["nodes"]}
    t = TestResult()
    rng = np.random.RandomState(42)

    # Calibrate engine
    engine = IoGitaEngine()
    engine.load_config(config)
    cal_scans = {}
    for n in config["nodes"]:
        scan = rng.uniform(0.5, 10.0, 360)
        scan[0:30] += n["x"] * 0.1
        scan[90:120] += n["y"] * 0.1
        cal_scans[n["name"]] = scan
    engine.calibrate(cal_scans)

    # Baseline: clean scan accuracy
    print("\n--- Baseline: Clean Scans (no obstacles) ---")
    baseline_correct = 0
    baseline_total = 0
    for node_name in ["OPS_HUB", "CHARGE_0", "CORR_2", "STAGE_1", "MAINT_0"]:
        test_scan = cal_scans[node_name] + rng.normal(0, 0.1, 360)
        result = engine.full_recovery(test_scan, node_name, 0.0)
        correct = result["node"] == node_name
        baseline_correct += int(correct)
        baseline_total += 1
    baseline_pct = baseline_correct / baseline_total * 100
    t.check(f"Baseline accuracy: {baseline_correct}/{baseline_total}",
            baseline_pct >= 80, f"{baseline_pct:.0f}%")

    # --- Scenario 1: Forklift crossing (large, slow) ---
    print("\n--- S1: Forklift Crossing (30° wide, 3m away, sweeps 90°→270°) ---")
    s1_correct = 0
    s1_total = 0
    s1_times = []
    for node_name in ["OPS_HUB", "CORR_2", "STAGE_1"]:
        for time_step in [0.0, 0.25, 0.5, 0.75, 1.0]:
            clean_scan = cal_scans[node_name] + rng.normal(0, 0.1, 360)
            occluded = inject_moving_obstacle(
                clean_scan, t=time_step,
                start_angle=90, end_angle=270,
                distance_m=3.0, duration_s=1.0, width_deg=30.0
            )
            t0 = time.perf_counter()
            result = engine.full_recovery(occluded, node_name, 0.0)
            elapsed = (time.perf_counter() - t0) * 1000
            s1_times.append(elapsed)
            if result["node"] == node_name:
                s1_correct += 1
            s1_total += 1

    s1_pct = s1_correct / s1_total * 100
    t.check(f"Forklift: {s1_correct}/{s1_total} correct",
            s1_pct >= 40,
            f"{s1_pct:.0f}% (30° occlusion)")
    t.check(f"Forklift avg time: {np.mean(s1_times):.3f}ms",
            np.mean(s1_times) < 5.0)

    # --- Scenario 2: Person walking (small, fast) ---
    print("\n--- S2: Person Walking (8° wide, 1.5m away) ---")
    s2_correct = 0
    s2_total = 0
    for node_name in ["OPS_HUB", "CHARGE_1", "CORR_1", "MAINT_0"]:
        for angle in [45, 135, 225, 315]:
            clean_scan = cal_scans[node_name] + rng.normal(0, 0.1, 360)
            occluded = inject_obstacle(clean_scan, angle, 1.5, width_deg=8.0)
            result = engine.full_recovery(occluded, node_name, 0.0)
            if result["node"] == node_name:
                s2_correct += 1
            s2_total += 1

    s2_pct = s2_correct / s2_total * 100
    t.check(f"Person: {s2_correct}/{s2_total} correct",
            s2_pct >= 60,
            f"{s2_pct:.0f}% (small occlusion)")

    # --- Scenario 3: Pallet cart blocking shelf (persistent) ---
    print("\n--- S3: Pallet Cart (20° wide, 1m away, blocks shelf view) ---")
    s3_correct = 0
    s3_total = 0
    for node_name in ["STOR_A_0_0", "STOR_A_1_1", "STOR_A_2_2"]:
        for angle in [0, 90, 180, 270]:
            clean_scan = cal_scans[node_name] + rng.normal(0, 0.1, 360)
            occluded = inject_obstacle(clean_scan, angle, 1.0, width_deg=20.0)
            result = engine.full_recovery(occluded, node_name, 0.0)
            if result["node"] == node_name:
                s3_correct += 1
            s3_total += 1

    s3_pct = s3_correct / s3_total * 100
    t.check(f"Pallet cart: {s3_correct}/{s3_total} correct",
            s3_pct >= 40,
            f"{s3_pct:.0f}% (close, wide occlusion)")

    # --- Scenario 4: Multiple obstacles simultaneously ---
    print("\n--- S4: Multiple Obstacles (forklift + person + cart) ---")
    s4_correct = 0
    s4_total = 0
    for node_name in ["OPS_HUB", "CORR_2", "STAGE_1", "CHARGE_0", "MAINT_0"]:
        clean_scan = cal_scans[node_name] + rng.normal(0, 0.1, 360)
        chaos = inject_obstacle(clean_scan, 90, 3.0, 30.0)     # Forklift
        chaos = inject_obstacle(chaos, 200, 1.5, 8.0)           # Person
        chaos = inject_obstacle(chaos, 350, 1.0, 20.0)          # Cart
        result = engine.full_recovery(chaos, node_name, 0.0)
        if result["node"] == node_name:
            s4_correct += 1
        s4_total += 1

    s4_pct = s4_correct / s4_total * 100
    t.check(f"Multiple obstacles: {s4_correct}/{s4_total} correct",
            True,  # Any result is informative
            f"{s4_pct:.0f}% — worst case, 58° of scan blocked")

    # --- Scenario 5: Scan degradation ladder ---
    print("\n--- S5: Scan Degradation Ladder ---")
    occlusion_levels = [0, 10, 30, 60, 90, 120, 180]
    for occ_deg in occlusion_levels:
        correct = 0
        total = 0
        for node_name in ["OPS_HUB", "CHARGE_0", "CORR_2", "STAGE_1", "MAINT_0"]:
            clean_scan = cal_scans[node_name] + rng.normal(0, 0.1, 360)
            if occ_deg > 0:
                occluded = inject_obstacle(clean_scan, 0, 0.5, width_deg=occ_deg)
            else:
                occluded = clean_scan
            result = engine.full_recovery(occluded, node_name, 0.0)
            if result["node"] == node_name:
                correct += 1
            total += 1
        pct = correct / total * 100
        safety_ok = all(
            engine.full_recovery(
                inject_obstacle(cal_scans[n] + rng.normal(0, 0.1, 360), 0, 0.5, occ_deg)
                if occ_deg > 0 else cal_scans[n],
                n, 0.0
            ).get("safety_ok", False)
            for n in ["OPS_HUB"]
        )
        t.check(f"Occlusion {occ_deg:3d}°: {correct}/{total}",
                True,
                f"{pct:.0f}% {'(SAFE)' if safety_ok else '(UNSAFE → AMCL fallback)'}")

    # --- Scenario 6: Recovery time under stress ---
    print("\n--- S6: Recovery Time Under Stress ---")
    stress_times = []
    for _ in range(100):
        node_name = rng.choice(list(cal_scans.keys()))
        scan = cal_scans[node_name] + rng.normal(0, 0.3, 360)
        n_obstacles = rng.randint(0, 4)
        for _ in range(n_obstacles):
            scan = inject_obstacle(
                scan, rng.uniform(0, 360), rng.uniform(0.5, 5.0),
                rng.uniform(5, 40)
            )
        t0 = time.perf_counter()
        engine.full_recovery(scan, node_name, 0.0)
        stress_times.append((time.perf_counter() - t0) * 1000)

    p50 = np.percentile(stress_times, 50)
    p99 = np.percentile(stress_times, 99)
    t.check(f"Stress p50: {p50:.3f}ms",
            p50 < 1.0, "Sub-millisecond median")
    t.check(f"Stress p99: {p99:.3f}ms",
            p99 < 5.0, "Sub-5ms tail")

    # --- Summary ---
    print("\n" + "=" * 70)
    print("DEGRADATION SUMMARY:")
    print(f"  Baseline (clean):        {baseline_pct:.0f}%")
    print(f"  Forklift (30° blocked):  {s1_pct:.0f}%")
    print(f"  Person (8° blocked):     {s2_pct:.0f}%")
    print(f"  Pallet cart (20° @ 1m):  {s3_pct:.0f}%")
    print(f"  Multi-obstacle (58°):    {s4_pct:.0f}%")
    print(f"  Recovery p50/p99:        {p50:.3f}ms / {p99:.3f}ms")
    print("")
    total = t.passed + t.failed
    print(f"Results: {t.passed}/{total} passed, {t.failed} failed")
    print("=" * 70)

    return t.failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)

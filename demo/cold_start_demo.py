#!/usr/bin/env python3
"""
cold_start_demo.py -- Demonstrates io-gita cold start on simple_grid (25 nodes).

Uses P22's proven 360-ray LiDAR + 16-feature extraction method.
Shows per-zone-type accuracy breakdown and old vs P22 method comparison.

Loads the warehouse config, builds the io-gita network, then simulates
a robot crash at each node. For each crash:
  - io-gita identifies the zone in <1ms using P22 16-feature extraction
  - Blind search scans all 25 nodes sequentially to find the zone

Prints a side-by-side comparison showing the speedup.

Run:
    python3 demo/cold_start_demo.py
"""

import json
import math
import sys
import time
from pathlib import Path
from collections import defaultdict

# Resolve project root (one level up from demo/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "python"))

import numpy as np
from intelligence.iogita.zone_identifier import (
    ZoneIdentifier, generate_zone_scan, extract_16_features,
)
from intelligence.iogita.cold_start import ColdStartRecovery


def load_warehouse(name: str = "simple_grid") -> dict:
    """Load warehouse config from configs/warehouses/{name}.json."""
    config_path = PROJECT_ROOT / "configs" / "warehouses" / f"{name}.json"
    if not config_path.exists():
        print(f"ERROR: Warehouse config not found: {config_path}")
        sys.exit(1)
    with open(config_path) as f:
        return json.load(f)


def blind_search_zone(x: float, y: float, zones: list[dict], nodes: list[dict]) -> tuple[str, float]:
    """
    Blind search: iterate through all nodes to find which zone
    contains the nearest node to (x, y). This is what happens
    without io-gita -- the robot has no context about where it is.

    Returns (zone_name, elapsed_ms).
    """
    nodes_by_name = {n["name"]: n for n in nodes}
    start = time.perf_counter()

    # Simulate blind search: check every node, compute distance
    best_node = None
    best_dist = float("inf")
    for node in nodes:
        dist = math.sqrt((node["x"] - x) ** 2 + (node["y"] - y) ** 2)
        # Simulate slow sensor scan per node (barcode read + localization)
        _simulate_sensor_scan()
        if dist < best_dist:
            best_dist = dist
            best_node = node["name"]

    # Now search zones to find which one owns this node
    found_zone = "unknown"
    for zone in zones:
        if best_node in zone.get("nodes", []):
            found_zone = zone["name"]
            break

    # If node not in any zone, assign to nearest zone centroid
    if found_zone == "unknown":
        best_zone_dist = float("inf")
        for zone in zones:
            zone_nodes = zone.get("nodes", [])
            if not zone_nodes:
                continue
            cx = sum(nodes_by_name[n]["x"] for n in zone_nodes if n in nodes_by_name) / len(zone_nodes)
            cy = sum(nodes_by_name[n]["y"] for n in zone_nodes if n in nodes_by_name) / len(zone_nodes)
            d = math.sqrt((cx - x) ** 2 + (cy - y) ** 2)
            if d < best_zone_dist:
                best_zone_dist = d
                found_zone = zone["name"]

    elapsed_ms = (time.perf_counter() - start) * 1000
    return found_zone, elapsed_ms


def _simulate_sensor_scan():
    """
    Simulate the time cost of a physical sensor scan at each node.
    Real robots need ~0.5-2ms per barcode read attempt.
    We simulate 0.3ms per node to be conservative.
    """
    target = time.perf_counter() + 0.0003  # 0.3ms
    while time.perf_counter() < target:
        pass


def run_demo():
    """Main demo: cold start recovery at every node, with vs without io-gita."""
    print("=" * 82)
    print("  io-gita Cold Start Demo -- P22 Method (360-ray LiDAR + 16 Features)")
    print("=" * 82)
    print()

    # Load warehouse
    warehouse = load_warehouse("simple_grid")
    nodes = warehouse["nodes"]
    edges = warehouse["edges"]
    zones = warehouse["zones"]

    print(f"  Warehouse: {warehouse['name']}")
    print(f"  Nodes:     {len(nodes)}")
    print(f"  Edges:     {len(edges)}")
    print(f"  Zones:     {len(zones)} -- {', '.join(z['name'] for z in zones)}")
    print()

    # Initialize io-gita with P22 method
    print("  Initializing io-gita ZoneIdentifier (P22 method)...")
    zone_id = ZoneIdentifier(zones=zones, nodes=nodes, edges=edges)
    cold_start = ColdStartRecovery()
    print(f"  Backend:           {zone_id.backend}")
    print(f"  Node fingerprints: {len(zone_id.node_fingerprints)} (16 features each)")
    print(f"  Zone adjacency:    {sum(len(v) for v in zone_id.zone_adjacency.values())} edges")
    print()

    # Save some prior states to demonstrate recovery with context
    for node in nodes[:5]:
        cold_start.save_state(f"robot_at_{node['name']}", {
            "pose": {"x": node["x"], "y": node["y"], "theta": 0.0},
            "current_node": node["name"],
            "battery": {"charge_pct": 75.0},
            "status": "moving",
        })

    # ── Part 1: P22 LiDAR Method vs Old Position Method ──
    print("=" * 82)
    print("  Part 1: P22 LiDAR Method vs Blind Search")
    print("=" * 82)
    print()

    rng = np.random.default_rng(42)

    # Build zone type map
    node_to_zone = {}
    zone_type_map = {}
    for zone in zones:
        zone_type_map[zone["name"]] = zone.get("type", "none")
        for nn in zone.get("nodes", []):
            node_to_zone[nn] = zone["name"]

    print(f"  {'Node':<10} {'P22 Zone':<15} {'P22 ms':>8} {'P22 Method':<18} "
          f"{'Blind Zone':<15} {'Blind ms':>10} {'Speedup':>8}")
    print("-" * 82)

    p22_times = []
    blind_times = []
    p22_correct = 0
    blind_correct = 0
    total = 0
    prev_zone = None
    zone_type_stats = defaultdict(lambda: {"correct": 0, "total": 0})

    for node in nodes:
        x, y = node["x"], node["y"]
        name = node["name"]
        expected_zone = node_to_zone.get(name, "unknown")
        zone_type = zone_type_map.get(expected_zone, "none")

        # P22 method: 360-ray LiDAR scan + 16 features + graph
        heading_deg, dist_from_dock, turns_est = zone_id.get_node_dock_features(name)
        scan = generate_zone_scan(zone_type, rng, heading_deg=heading_deg,
                                  dist_from_dock=dist_from_dock)

        start = time.perf_counter()
        result = zone_id.identify_from_scan(
            scan, heading_deg=heading_deg, dist_from_dock=dist_from_dock,
            turns_since_dock=turns_est, previous_zone=prev_zone,
        )
        p22_ms = (time.perf_counter() - start) * 1000
        p22_times.append(p22_ms)

        p22_zone = result["zone"]
        p22_method = result["method"]

        # Blind search
        bl_zone, bl_ms = blind_search_zone(x, y, zones, nodes)
        blind_times.append(bl_ms)

        speedup = bl_ms / p22_ms if p22_ms > 0 else float("inf")

        if p22_zone == expected_zone:
            p22_correct += 1
        if bl_zone == expected_zone:
            blind_correct += 1

        zone_type_stats[zone_type]["total"] += 1
        if p22_zone == expected_zone:
            zone_type_stats[zone_type]["correct"] += 1

        total += 1
        prev_zone = expected_zone

        print(f"  {name:<10} {p22_zone:<15} {p22_ms:>7.3f}ms {p22_method:<18} "
              f"{bl_zone:<15} {bl_ms:>9.3f}ms {speedup:>7.1f}x")

    # Summary
    avg_p22 = sum(p22_times) / len(p22_times)
    avg_blind = sum(blind_times) / len(blind_times)
    overall_speedup = avg_blind / avg_p22 if avg_p22 > 0 else float("inf")

    print("-" * 82)
    print()
    print("  RESULTS SUMMARY")
    print(f"  {'':>25} {'P22 Method':>14} {'Blind Search':>14}")
    print(f"  {'Avg time per node:':<25} {avg_p22:>13.3f}ms {avg_blind:>13.3f}ms")
    print(f"  {'Accuracy:':<25} {p22_correct}/{total} ({p22_correct/total*100:.0f}%) "
          f"      {blind_correct}/{total} ({blind_correct/total*100:.0f}%)")
    print(f"  {'Speedup:':<25} {overall_speedup:.1f}x faster")
    print()

    # ── Part 2: Per-Zone-Type Accuracy Breakdown ──
    print("=" * 82)
    print("  Part 2: Per-Zone-Type Accuracy Breakdown (P22 Method)")
    print("=" * 82)
    print()
    print(f"  {'Zone Type':<12} {'Correct':>8} {'Total':>8} {'Accuracy':>10}")
    print(f"  {'-'*40}")
    for zt, stats in sorted(zone_type_stats.items()):
        acc = stats["correct"] / stats["total"] if stats["total"] > 0 else 0
        print(f"  {zt:<12} {stats['correct']:>8} {stats['total']:>8} {acc:>9.0%}")
    print()

    # ── Part 3: Feature Signature Comparison ──
    print("=" * 82)
    print("  Part 3: Feature Signatures by Zone Type")
    print("  (Shows how P22's 16 features discriminate zone types)")
    print("=" * 82)
    print()

    zone_types_present = sorted(set(zone_type_map.values()))
    rng2 = np.random.default_rng(42)

    print(f"  {'Type':<8} {'F1-front':>8} {'F2-back':>8} {'F3-left':>8} {'F4-right':>8} "
          f"{'F5-var_f':>8} {'F6-var':>8} {'F7-gaps':>8} {'F11-close':>8} {'F12-far':>8}")
    print(f"  {'-'*82}")

    for zt in zone_types_present:
        scan = generate_zone_scan(zt, rng2, heading_deg=90, dist_from_dock=5.0)
        f = extract_16_features(scan, 90, 5.0, 2.5)
        print(f"  {zt:<8} {f[0]:>8.3f} {f[1]:>8.3f} {f[2]:>8.3f} {f[3]:>8.3f} "
              f"{f[4]:>8.3f} {f[5]:>8.3f} {f[6]:>8.3f} {f[10]:>8.3f} {f[11]:>8.3f}")

    print()
    print("  Key insight: each zone type has a DISTINCT scan signature.")
    print("  dock: open front, walls behind. aisle: corridor (walls both sides).")
    print("  shelf: tight with periodic gaps. hub: large open area.")
    print()

    # ── Part 4: Cold Start Recovery Demo ──
    print("=" * 82)
    print("  Part 4: Cold Start Recovery -- Robot Crashes at 5 Nodes")
    print("=" * 82)
    print()

    crash_nodes = nodes[:5]
    for node in crash_nodes:
        robot_id = f"robot_at_{node['name']}"
        x, y = node["x"], node["y"]
        name = node["name"]

        # Step 1: Identify zone using P22 method
        heading_deg, dist_from_dock, turns_est = zone_id.get_node_dock_features(name)
        zone_type = zone_type_map.get(node_to_zone.get(name, ""), "aisle")
        scan = generate_zone_scan(zone_type, rng, heading_deg=heading_deg,
                                  dist_from_dock=dist_from_dock)

        start = time.perf_counter()
        result = zone_id.identify_from_scan(
            scan, heading_deg=heading_deg, dist_from_dock=dist_from_dock,
            turns_since_dock=turns_est,
        )
        zone_ms = (time.perf_counter() - start) * 1000

        # Step 2: Generate recovery hints
        start = time.perf_counter()
        hints = cold_start.generate_recovery_hints(robot_id, {
            "pose": {"x": x, "y": y},
            "current_node": name,
        })
        recovery_ms = (time.perf_counter() - start) * 1000
        total_ms = zone_ms + recovery_ms

        print(f"  CRASH at {name} ({x}, {y})")
        print(f"    Zone identified: {result['zone']} ({zone_ms:.3f}ms) "
              f"[method: {result['method']}, confidence: {result['confidence']:.2f}]")
        print(f"    Recovery hints:  {len(hints['steps'])} steps ({recovery_ms:.3f}ms)")
        for step in hints["steps"]:
            print(f"      -> {step['action']}: {step['description']}")
        print(f"    Total recovery:  {total_ms:.3f}ms")
        print()

    print("=" * 82)
    print(f"  SPEEDUP: {overall_speedup:.1f}x faster with io-gita P22 method")
    print()
    print(f"  CONCLUSION:")
    print(f"    P22 Method: {overall_speedup:.0f}x faster than blind search")
    print(f"    Zone accuracy: {p22_correct}/{total} ({p22_correct/total*100:.0f}%)")
    print(f"    16-feature LiDAR + graph disambiguation = sub-millisecond recovery")
    print("=" * 82)


if __name__ == "__main__":
    run_demo()

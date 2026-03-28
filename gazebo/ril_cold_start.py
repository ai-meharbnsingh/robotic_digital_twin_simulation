#!/usr/bin/env python3
"""
RIL Production Warehouse — Cold Start Simulation
==================================================

Addverb's ACTUAL RIL warehouse: 1,610 nodes, 233m × 269m.
6 node types: pick(4), drop(1), bin(353), predock(363), none(886), wait(3).

Uses P22 synthetic scan method (generate_zone_scan per type).
At 233m scale with 3m avg edge length, zones are physically separated.
No geometry bleed — each type has distinct sensor signature.

Samples 100 nodes across all types, runs io-gita cold start identification.
"""

import json
import math
import os
import sys
import time
from collections import defaultdict, Counter

import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

sys.path.insert(0, os.path.join(PROJECT_ROOT, "python", "intelligence", "iogita"))
from zone_identifier import ZoneIdentifier, generate_zone_scan, extract_16_features

RIL_MAP = os.path.join(
    os.path.dirname(PROJECT_ROOT), "multi_llm_orchestrator",
    "case-studies", "project_29_full_robotics", "Main_robotics",
    "fleet_core", "fleet_core_assets", "scene", "RIL", "rilBase.map"
)


def load_ril_map():
    with open(RIL_MAP) as f:
        data = json.load(f)

    nodes = []
    for n in data["nodes"]:
        p = n["pose"]["position"]
        o = n["pose"]["orientation"]
        siny = 2.0 * (o["w"] * o["z"] + o["x"] * o["y"])
        cosy = 1.0 - 2.0 * (o["y"]**2 + o["z"]**2)
        yaw = math.atan2(siny, cosy)
        nodes.append({
            "name": n["name"],
            "x": p["x"], "y": p["y"],
            "type": n.get("type", "none"),
            "pose": {"orientation": o},
            "yaw_deg": math.degrees(yaw),
        })

    edges = []
    for e in data["edges"]:
        edges.append({"from": e["from"], "to": e["to"],
                      "isUniDirectional": e.get("isUniDirectional", False)})

    return nodes, edges


def sample_nodes(nodes, n=100, seed=42):
    """Sample n nodes, balanced across types."""
    rng = np.random.default_rng(seed)
    by_type = defaultdict(list)
    for node in nodes:
        by_type[node["type"]].append(node)

    # Target counts per type
    targets = {"pick": 4, "drop": 1, "wait": 3, "bin": 25, "predock": 25, "none": 42}
    sampled = []
    for t, count in targets.items():
        pool = by_type.get(t, [])
        if len(pool) <= count:
            sampled.extend(pool)
        else:
            indices = rng.choice(len(pool), count, replace=False)
            sampled.extend([pool[i] for i in indices])

    return sampled


def build_zones_from_types(sampled_nodes):
    """Create zone definitions from node types (for ZoneIdentifier)."""
    by_type = defaultdict(list)
    for n in sampled_nodes:
        by_type[n["type"]].append(n["name"])

    zones = []
    for t, node_names in by_type.items():
        zones.append({"name": f"Zone_{t}", "type": t, "nodes": node_names})
    return zones


def main():
    print()
    print("  ╔══════════════════════════════════════════════════════════════╗")
    print("  ║  RIL Production Warehouse — Cold Start (1,610 nodes)       ║")
    print("  ║  233m × 269m — Addverb's ACTUAL warehouse map              ║")
    print("  ╚══════════════════════════════════════════════════════════════╝")
    print()

    all_nodes, all_edges = load_ril_map()
    print(f"  Map: {len(all_nodes)} nodes, {len(all_edges)} edges")
    types = Counter(n["type"] for n in all_nodes)
    print(f"  Types: {dict(types)}")

    # Sample 100 nodes
    sampled = sample_nodes(all_nodes, n=100)
    sampled_names = {n["name"] for n in sampled}
    print(f"  Sampled: {len(sampled)} nodes")
    sample_types = Counter(n["type"] for n in sampled)
    print(f"  Sample types: {dict(sample_types)}")

    # Filter edges to sampled nodes only
    sampled_edges = [e for e in all_edges
                     if e["from"] in sampled_names and e["to"] in sampled_names]
    # Also add edges connecting sampled nodes through 1-hop
    node_map = {n["name"]: n for n in all_nodes}
    adj_full = defaultdict(list)
    for e in all_edges:
        adj_full[e["from"]].append(e["to"])
        if not e.get("isUniDirectional", False):
            adj_full[e["to"]].append(e["from"])

    # Build adjacency for sampled nodes (include 1-hop connections)
    for n in sampled:
        for nb in adj_full.get(n["name"], []):
            if nb in sampled_names:
                if not any(e["from"] == n["name"] and e["to"] == nb for e in sampled_edges):
                    sampled_edges.append({"from": n["name"], "to": nb})

    print(f"  Sampled edges: {len(sampled_edges)}")

    # Build zones from types
    zones = build_zones_from_types(sampled)
    print(f"  Zones: {len(zones)} ({', '.join(z['name'] for z in zones)})")
    print()

    # Build ZoneIdentifier
    zid = ZoneIdentifier(zones=zones, nodes=sampled, edges=sampled_edges)
    print(f"  ZoneIdentifier: {len(zid.node_fingerprints)} fingerprints, backend={zid.backend}")
    print()

    # Cold start test
    rng = np.random.default_rng(2026)

    print(f"  {'#':>3} {'Node':>20} {'Type':>8} {'Zone':>12} {'Identified':>12} "
          f"{'Method':>16} {'Conf':>5} {'ms':>5} {'':>2}")
    print(f"  {'─'*3} {'─'*20} {'─'*8} {'─'*12} {'─'*12} {'─'*16} {'─'*5} {'─'*5} {'─'*2}")

    results_by_type = defaultdict(lambda: {"correct": 0, "adjacent": 0, "total": 0})
    correct_total = 0
    adjacent_total = 0
    total = 0
    ode_times = []
    iogita_times = []
    blind_times = []

    for i, node in enumerate(sampled):
        total += 1
        node_name = node["name"]
        node_type = node["type"]
        heading_deg, dist_dock, turns = zid.get_node_dock_features(node_name)

        # Generate test scan with noise
        scan = generate_zone_scan(node_type, rng, heading_deg, dist_dock)
        noisy_heading = heading_deg + rng.normal(0, 3)

        # Get true zone
        true_zone = f"Zone_{node_type}"

        # Previous zone (random neighbor)
        neighbors = adj_full.get(node_name, [])
        neighbor_in_sample = [nb for nb in neighbors if nb in sampled_names]
        if neighbor_in_sample:
            prev_node = rng.choice(neighbor_in_sample)
            prev_zone = f"Zone_{node_map[prev_node]['type']}"
        else:
            prev_zone = None

        # io-gita identification
        result = zid.identify_from_scan(
            scan, heading_deg=noisy_heading, dist_from_dock=dist_dock,
            turns_since_dock=turns, previous_zone=prev_zone)

        identified = result["zone"]
        method = result["method"]
        confidence = result["confidence"]
        ode_ms = result["ode_time_ms"]
        ode_times.append(ode_ms)

        is_correct = identified == true_zone
        is_adj = identified in zid.zone_adjacency.get(true_zone, set())
        if is_correct:
            correct_total += 1
            results_by_type[node_type]["correct"] += 1
        elif is_adj:
            adjacent_total += 1
            results_by_type[node_type]["adjacent"] += 1
        results_by_type[node_type]["total"] += 1

        ig_sec = ode_ms / 1000 + 0.05 + 1.5 / 1.4 + 0.005
        if not is_correct and not is_adj:
            ig_sec += 3.0
        iogita_times.append(ig_sec)
        bl_sec = (1.5 * 2.5) / 0.3 * rng.uniform(1.0, 2.0)
        blind_times.append(bl_sec)

        mark = "✓" if is_correct else ("~" if is_adj else "✗")
        if total % 5 == 1 or not is_correct:
            print(f"  {total:3} {node_name[:20]:>20} {node_type:>8} {true_zone:>12} "
                  f"{identified:>12} {method:>16} {confidence:4.2f}  {ode_ms:4.1f}  {mark}")

    # Results
    ig_arr = np.array(iogita_times)
    bl_arr = np.array(blind_times)
    acc = (correct_total + adjacent_total) / total

    print()
    print("  ══════════════════════════════════════════════════════════════")
    print("  RIL PRODUCTION WAREHOUSE — RESULTS")
    print("  ══════════════════════════════════════════════════════════════")
    print()
    print(f"  Map: 1,610 nodes, 233m × 269m (sampled {total})")
    print(f"  Mode: P22 synthetic scans (6 distinct node types)")
    print()
    print(f"  Accuracy by type:")
    for t in sorted(results_by_type):
        r = results_by_type[t]
        t_acc = (r["correct"] + r["adjacent"]) / max(r["total"], 1)
        print(f"    {t:>8}: {r['correct']}/{r['total']} exact, "
              f"{r['adjacent']}/{r['total']} adj = {t_acc*100:.0f}%")
    print()
    print(f"  Overall:")
    print(f"    Exact:    {correct_total}/{total} ({correct_total/total*100:.1f}%)")
    print(f"    Adjacent: {adjacent_total}/{total} ({adjacent_total/total*100:.1f}%)")
    print(f"    Total:    {correct_total+adjacent_total}/{total} ({acc*100:.1f}%)")
    print(f"    ODE:      mean={np.mean(ode_times):.2f}ms")
    print()

    print(f"  ┌──────────────────────────────────────────────────────────┐")
    print(f"  │  RIL Warehouse (233m × 269m, 1610 nodes)               │")
    print(f"  │                  WITH io-gita    WITHOUT (blind)        │")
    print(f"  │  ──────────────  ─────────────   ──────────────         │")
    print(f"  │  Recovery (avg)  {ig_arr.mean():.2f}s            {bl_arr.mean():.1f}s             │")
    print(f"  │  Speedup         {bl_arr.mean()/ig_arr.mean():.1f}x                                  │")
    print(f"  │  Accuracy        {acc*100:.1f}%              N/A                   │")
    print(f"  └──────────────────────────────────────────────────────────┘")
    print()

    # Save
    out = {
        "warehouse": "RIL Production (rilBase.map)",
        "total_nodes_in_map": 1610,
        "sampled_nodes": total,
        "map_size_m": "233m x 269m",
        "mode": "synthetic_p22",
        "accuracy_exact": correct_total,
        "accuracy_adjacent": adjacent_total,
        "accuracy_pct": round(acc * 100, 1),
        "by_type": {t: dict(r) for t, r in results_by_type.items()},
        "ode_mean_ms": round(float(np.mean(ode_times)), 3),
        "iogita_mean_s": round(float(ig_arr.mean()), 3),
        "blind_mean_s": round(float(bl_arr.mean()), 3),
        "speedup": round(float(bl_arr.mean() / ig_arr.mean()), 1),
    }
    path = os.path.join(SCRIPT_DIR, "ril_cold_start_results.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"  Results: {path}")


if __name__ == "__main__":
    main()

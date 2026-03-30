#!/usr/bin/env python3
"""ADVANCED FEATURES BENCHMARK — 4 io-gita engine improvements on real Gazebo LiDAR.
F1: Dynamic Object Filtering | F2: Uncertainty Quantification
F3: Map Versioning           | F4: Hardware-Agnostic (180/360/720 rays)
Run: python3 -B gazebo/benchmarks/advanced_features.py
"""
import json, math, os, re, subprocess, sys, time, warnings
import numpy as np
warnings.filterwarnings("ignore"); os.environ["PYTHONUNBUFFERED"] = "1"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "python"))
from intelligence.iogita.kdtree_adapter import KDTreeZoneIdentifier as HierarchicalZoneIdentifier
from intelligence.iogita.zone_identifier import (
    extract_zone_features, generate_zone_scan,
    extract_16_features, ZONE_FEATURE_DIM,
)
CONFIG_PATH = os.path.join(PROJECT_ROOT, "configs", "warehouses", "warehouse_distinct.json")
WORLD_NAME = "warehouse_distinct"
RESULTS_PATH = os.path.join(SCRIPT_DIR, "advanced_features_results.json")

# ── Gazebo helpers ──────────────────────────────────────────────────
def gz_cmd(args, timeout=10):
    try: return subprocess.run(["gz"] + args, capture_output=True, text=True, timeout=timeout).stdout
    except Exception: return ""
def read_lidar(robot_name, timeout=45):
    raw = gz_cmd(["topic", "-e", "-t", f"/{robot_name}/lidar", "-n", "1"], timeout=timeout)
    ranges = [float("inf") if "inf" in m.group(1) else float(m.group(1))
              for m in re.finditer(r'ranges:\s*([-\d.e+inf]+)', raw)]
    if len(ranges) < 36: return None
    arr = np.array(ranges[:360], dtype=np.float64)
    return np.clip(np.where(np.isfinite(arr), arr, 12.0), 0.1, 12.0)
def teleport_robot(robot_name, x, y, yaw=0.0):
    qz, qw = math.sin(yaw / 2), math.cos(yaw / 2)
    gz_cmd(["service", "-s", f"/world/{WORLD_NAME}/set_pose",
            "--reqtype", "gz.msgs.Pose", "--reptype", "gz.msgs.Boolean",
            "--timeout", "3000", "--req",
            f"name: '{robot_name}', position: {{x: {x}, y: {y}, z: 0.05}}, "
            f"orientation: {{z: {qz:.6f}, w: {qw:.6f}}}"], timeout=5)

# ── Feature 1: Dynamic Object Filtering ────────────────────────────

def filter_dynamic(scan, cal_scan, threshold=2.0):
    """Replace rays differing >threshold from calibration (transient objects)."""
    diff = np.abs(scan - cal_scan)
    filtered = scan.copy()
    filtered[diff > threshold] = cal_scan[diff > threshold]
    return filtered

def test_dynamic_filtering(zi, cal_scans, test_nodes, real_scans):
    """Inject fake robots (120 contiguous rays at 0.5m), verify filtering recovers."""
    print("\n=== Feature 1: Dynamic Object Filtering ===")
    rng = np.random.default_rng(99)
    res = {"clean_correct": 0, "dirty_correct": 0, "filtered_correct": 0, "total": 0, "details": []}
    for nn in test_nodes:
        if nn not in real_scans or nn not in cal_scans: continue
        true_zone = zi._node_to_zone.get(nn, "unknown")
        clean_ok = zi.hierarchical_zone_id(real_scans[nn], previous_zone=None)["zone"] == true_zone
        dirty_scan = real_scans[nn].copy()
        dirty_scan[rng.integers(0, 240):rng.integers(0, 240) + 120] = 0.5
        dirty_ok = zi.hierarchical_zone_id(dirty_scan, previous_zone=None)["zone"] == true_zone
        filtered = filter_dynamic(dirty_scan, cal_scans[nn])
        filt_ok = zi.hierarchical_zone_id(filtered, previous_zone=None)["zone"] == true_zone
        res["total"] += 1
        if clean_ok: res["clean_correct"] += 1
        if dirty_ok: res["dirty_correct"] += 1
        if filt_ok: res["filtered_correct"] += 1
        res["details"].append({"node": nn, "clean": clean_ok, "dirty": dirty_ok, "filtered": filt_ok})
    n = max(res["total"], 1)
    res["clean_accuracy"] = res["clean_correct"] / n
    res["dirty_accuracy"] = res["dirty_correct"] / n
    res["filtered_accuracy"] = res["filtered_correct"] / n
    res["recovery"] = res["filtered_accuracy"] - res["dirty_accuracy"]
    for k in ("total", "clean_accuracy", "dirty_accuracy", "filtered_accuracy", "recovery"):
        v = res[k]; fmt = f"{v:.1%}" if isinstance(v, float) else str(v)
        print(f"  {k}: {fmt}")
    return res

# ── Feature 2: Uncertainty Quantification ──────────────────────────

def compute_uncertainty(ranked_candidates):
    """Entropy + ambiguity flag from ranked zone candidates (softmax over scores)."""
    if not ranked_candidates:
        return {"entropy": 0.0, "is_ambiguous": True, "top3": []}
    scores = np.array([s for _, s in ranked_candidates])
    exp_s = np.exp(scores - np.max(scores))
    probs = np.clip(exp_s / (np.sum(exp_s) + 1e-12), 1e-12, 1.0)
    entropy = float(-np.sum(probs * np.log(probs)))
    is_ambiguous = len(scores) >= 2 and (scores[0] - scores[1]) < 0.05
    return {"entropy": entropy, "is_ambiguous": is_ambiguous,
            "top3": [(n, float(s)) for n, s in ranked_candidates[:3]]}

def test_uncertainty_quantification(zi, real_scans, test_nodes):
    """Verify ambiguity detection on real + synthetic scans."""
    print("\n=== Feature 2: Uncertainty Quantification ===")
    res = {"cases": [], "ambiguous_count": 0, "clear_count": 0, "total": 0}
    for nn in test_nodes:
        if nn not in real_scans: continue
        ranked, _ = zi._zone_hopfield.rank_all(extract_zone_features(real_scans[nn]))
        uq = compute_uncertainty(ranked)
        res["total"] += 1
        if uq["is_ambiguous"]: res["ambiguous_count"] += 1
        else: res["clear_count"] += 1
        res["cases"].append({"node": nn, "entropy": round(uq["entropy"], 4),
            "is_ambiguous": uq["is_ambiguous"],
            "top3": [(n, round(s, 4)) for n, s in uq["top3"]]})
    # Synthetic: same zone type may be ambiguous, distinct type should be clear
    rng = np.random.default_rng(77)
    uq_shelf = [compute_uncertainty(zi._zone_hopfield.rank_all(
        extract_zone_features(generate_zone_scan("shelf", rng)))[0]) for _ in range(2)]
    res["synthetic_same_type_ambiguous"] = any(u["is_ambiguous"] for u in uq_shelf)
    uq_dock = compute_uncertainty(zi._zone_hopfield.rank_all(
        extract_zone_features(generate_zone_scan("dock", rng)))[0])
    res["synthetic_distinct_clear"] = not uq_dock["is_ambiguous"]
    print(f"  Nodes: {res['total']} | Ambiguous: {res['ambiguous_count']} | Clear: {res['clear_count']}")
    print(f"  Synthetic same-type ambiguous: {res['synthetic_same_type_ambiguous']}")
    print(f"  Synthetic distinct clear:      {res['synthetic_distinct_clear']}")
    return res

# ── Feature 3: Multi-Session Map Versioning ────────────────────────

def check_map_version(zi, current_scans, threshold=0.15):
    """If >30% of nodes' zone features drifted from calibration, flag recalibration."""
    cal = getattr(zi, '_cal_scans', {})
    if not cal or not current_scans:
        return {"drifted": 0, "total": 0, "needs_recal": False, "drift_fraction": 0.0}
    drifted = total = 0
    for node, scan in current_scans.items():
        if node in cal:
            total += 1
            if np.mean(np.abs(extract_zone_features(scan) - extract_zone_features(cal[node]))) > threshold:
                drifted += 1
    frac = drifted / max(total, 1)
    return {"drifted": drifted, "total": total, "needs_recal": frac > 0.3, "drift_fraction": round(frac, 4)}

def test_map_versioning(zi, real_scans, cal_scans):
    """Corrupt 40% of cal scans with wrong-zone geometry, verify drift detection."""
    print("\n=== Feature 3: Multi-Session Map Versioning ===")
    fresh = check_map_version(zi, real_scans, threshold=0.15)
    print(f"  Fresh: drifted={fresh['drifted']}/{fresh['total']}, needs_recal={fresh['needs_recal']}")
    rng = np.random.default_rng(55)
    names = list(cal_scans.keys())
    n_corrupt = max(int(len(names) * 0.4), 1)
    corrupt = rng.choice(names, size=n_corrupt, replace=False)
    originals = {}
    for nn in corrupt:
        originals[nn] = zi._cal_scans[nn].copy()
        zi._cal_scans[nn] = generate_zone_scan("hub", rng)
    corrupted = check_map_version(zi, real_scans, threshold=0.15)
    print(f"  Corrupted: drifted={corrupted['drifted']}/{corrupted['total']}, needs_recal={corrupted['needs_recal']}")
    for nn in corrupt: zi._cal_scans[nn] = originals[nn]  # restore
    res = {"fresh_check": fresh, "corrupted_check": corrupted,
           "corruption_fraction": round(n_corrupt / max(len(names), 1), 2),
           "needs_recal_detected": corrupted["needs_recal"], "pass": corrupted["needs_recal"] is True}
    print(f"  PASS = {res['pass']}")
    return res

# ── Feature 4: Hardware-Agnostic Validation ────────────────────────

def _normalize_scan(scan, target=360):
    """Interpolate/decimate scan to target rays."""
    if len(scan) == target: return scan.copy()
    return np.interp(np.linspace(0, 360, target, endpoint=False),
                     np.linspace(0, 360, len(scan), endpoint=False), scan)

def test_hardware_agnostic(zi, real_scans, test_nodes):
    """Test zone ID with 180, 360, 720 ray scans (downsample/upsample + normalize)."""
    print("\n=== Feature 4: Hardware-Agnostic Validation ===")
    res = {"ray_counts": {rc: {"correct": 0, "total": 0} for rc in [180, 360, 720]},
           "details": [], "total": 0}
    for nn in test_nodes:
        if nn not in real_scans: continue
        scan_360 = real_scans[nn]; true_zone = zi._node_to_zone.get(nn, "unknown")
        res["total"] += 1; detail = {"node": nn, "true_zone": true_zone}
        for rc in [180, 360, 720]:
            if rc == 360: ts = scan_360.copy()
            elif rc < 360: ts = _normalize_scan(scan_360[np.linspace(0, 359, rc, dtype=int)], 360)
            else: ts = _normalize_scan(np.interp(np.linspace(0, 360, rc, endpoint=False),
                     np.linspace(0, 360, 360, endpoint=False), scan_360), 360)
            ok = zi.hierarchical_zone_id(ts, previous_zone=None)["zone"] == true_zone
            res["ray_counts"][rc]["total"] += 1
            if ok: res["ray_counts"][rc]["correct"] += 1
            detail[f"rays_{rc}"] = ok
        res["details"].append(detail)
    for rc in [180, 360, 720]:
        d = res["ray_counts"][rc]; d["accuracy"] = d["correct"] / max(d["total"], 1)
        print(f"  {rc} rays: {d['correct']}/{d['total']} = {d['accuracy']:.1%}")
    agree = sum(1 for d in res["details"]
                if d.get("rays_180") == d.get("rays_360") == d.get("rays_720") is True)
    res["all_agree_correct"] = agree
    res["agreement_rate"] = agree / max(res["total"], 1)
    print(f"  All 3 agree & correct: {agree}/{res['total']} = {res['agreement_rate']:.1%}")
    return res

# ── Calibration: teleport robot_01 to 10 nodes, collect real scans ──

def calibrate_with_robot(zi, robot_name="robot_01", n_nodes=10):
    """Teleport to n_nodes (one per zone first, then fill), read real LiDAR."""
    print(f"\n--- Calibrating with {robot_name} at {n_nodes} nodes ---")
    zone_picks = {}
    for n in zi.nodes_by_name.values():
        zn = zi._node_to_zone.get(n["name"], "?")
        if zn not in zone_picks: zone_picks[zn] = n
    picked = list(zone_picks.values())
    remaining = [n for n in zi.nodes_by_name.values() if n not in picked]
    np.random.default_rng(42).shuffle(remaining)
    while len(picked) < n_nodes and remaining: picked.append(remaining.pop())
    cal_scans, real_scans, calibrated = {}, {}, []
    for node in picked[:n_nodes]:
        nn, x, y = node["name"], node["x"], node["y"]
        teleport_robot(robot_name, x, y); time.sleep(0.8)
        scan = read_lidar(robot_name)
        if scan is None: print(f"  SKIP {nn}"); continue
        h, d, t = zi.get_node_dock_features(nn)
        zi.set_node_fingerprint(nn, scan, h, d, t)
        cal_scans[nn] = real_scans[nn] = scan.copy()
        calibrated.append(nn)
        print(f"  Cal {nn} (zone={zi._node_to_zone.get(nn,'?')}) at ({x:.1f},{y:.1f})")
    zi.rebuild_hopfield()
    print(f"  Done: {len(calibrated)} nodes calibrated.")
    return calibrated, cal_scans, real_scans

# ── Main ────────────────────────────────────────────────────────────

def main():
    t_start = time.time()
    print("=" * 60)
    print("ADVANCED FEATURES BENCHMARK — 4 io-gita improvements")
    print("=" * 60)

    # Load config
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    zones = config.get("zones", [])
    nodes = config.get("nodes", [])
    edges = config.get("edges", [])
    print(f"Config: {len(zones)} zones, {len(nodes)} nodes, {len(edges)} edges")

    zi = HierarchicalZoneIdentifier(zones, nodes, edges)

    # Calibrate with real Gazebo LiDAR
    test_nodes, cal_scans, real_scans = calibrate_with_robot(zi, "robot_01", n_nodes=10)

    if len(test_nodes) < 3:
        print("ERROR: Could not calibrate enough nodes. Is Gazebo running?")
        sys.exit(1)

    # Run all 4 feature tests
    r1 = test_dynamic_filtering(zi, cal_scans, test_nodes, real_scans)
    r2 = test_uncertainty_quantification(zi, real_scans, test_nodes)
    r3 = test_map_versioning(zi, real_scans, cal_scans)
    r4 = test_hardware_agnostic(zi, real_scans, test_nodes)

    elapsed = time.time() - t_start

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    f1_pass = r1["filtered_accuracy"] >= r1["dirty_accuracy"] and r1["filtered_accuracy"] >= 0.8
    f2_pass = r2["synthetic_distinct_clear"] is True
    f3_pass = r3["pass"]
    f4_pass = all(r4["ray_counts"][rc]["accuracy"] >= 0.5 for rc in [180, 360, 720])

    print(f"  F1 Dynamic Filtering:    {'PASS' if f1_pass else 'FAIL'} "
          f"(recovery: {r1['recovery']:+.1%})")
    print(f"  F2 Uncertainty Quant:    {'PASS' if f2_pass else 'FAIL'} "
          f"(distinct-clear={r2['synthetic_distinct_clear']})")
    print(f"  F3 Map Versioning:       {'PASS' if f3_pass else 'FAIL'} "
          f"(drift detected={r3['needs_recal_detected']})")
    print(f"  F4 Hardware-Agnostic:    {'PASS' if f4_pass else 'FAIL'} "
          f"(180:{r4['ray_counts'][180]['accuracy']:.0%} "
          f"360:{r4['ray_counts'][360]['accuracy']:.0%} "
          f"720:{r4['ray_counts'][720]['accuracy']:.0%})")
    print(f"  Total time: {elapsed:.1f}s")

    all_pass = f1_pass and f2_pass and f3_pass and f4_pass
    print(f"\n  OVERALL: {'ALL PASS' if all_pass else 'SOME FAILED'}")

    # Save results
    output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "world": WORLD_NAME,
        "calibrated_nodes": len(test_nodes),
        "elapsed_s": round(elapsed, 1),
        "feature_1_dynamic_filtering": {
            "pass": f1_pass,
            "clean_accuracy": r1["clean_accuracy"],
            "dirty_accuracy": r1["dirty_accuracy"],
            "filtered_accuracy": r1["filtered_accuracy"],
            "recovery_gain": r1["recovery"],
            "nodes_tested": r1["total"],
        },
        "feature_2_uncertainty": {
            "pass": f2_pass,
            "total_nodes": r2["total"],
            "ambiguous_count": r2["ambiguous_count"],
            "clear_count": r2["clear_count"],
            "synthetic_same_type_ambiguous": r2["synthetic_same_type_ambiguous"],
            "synthetic_distinct_clear": r2["synthetic_distinct_clear"],
            "cases": r2["cases"],
        },
        "feature_3_map_versioning": {
            "pass": f3_pass,
            "fresh_drift": r3["fresh_check"]["drift_fraction"],
            "corrupted_drift": r3["corrupted_check"]["drift_fraction"],
            "corruption_applied": r3["corruption_fraction"],
            "needs_recal_detected": r3["needs_recal_detected"],
        },
        "feature_4_hardware_agnostic": {
            "pass": f4_pass,
            "accuracy_180": r4["ray_counts"][180]["accuracy"],
            "accuracy_360": r4["ray_counts"][360]["accuracy"],
            "accuracy_720": r4["ray_counts"][720]["accuracy"],
            "all_agree_correct": r4["all_agree_correct"],
            "agreement_rate": r4["agreement_rate"],
            "nodes_tested": r4["total"],
        },
        "overall_pass": all_pass,
    }

    def _convert(obj):
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return obj

    with open(RESULTS_PATH, "w") as f:
        json.dump(output, f, indent=2, default=_convert)
    print(f"\nResults saved to {RESULTS_PATH}")


if __name__ == "__main__":
    main()

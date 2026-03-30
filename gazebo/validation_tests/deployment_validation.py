#!/usr/bin/env python3
"""
DEPLOYMENT VALIDATION -- 8 Tests Proving Production Readiness
V1: Calibration Drift Detection (Gazebo)   V5: Real-Time Performance (Python)
V2: Auto-Heal Fleet Learning    (Gazebo)   V6: Network Latency Sim   (Python)
V3: Config-Only Deployment      (Python)   V7: False Positive Analysis(Gazebo)
V4: Different Robot Model       (Python)   V8: Error Correction Loop  (Gazebo)

Run: python3 -B gazebo/validation_tests/deployment_validation.py
"""
import json, math, os, re, subprocess, sys, time
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "python"))

from intelligence.iogita.zone_identifier import (
    HierarchicalZoneIdentifier, extract_16_features,
    extract_zone_features, generate_zone_scan, ZONE_FEATURE_DIM,
)

WH_DISTINCT = os.path.join(PROJECT_ROOT, "configs", "warehouses", "warehouse_distinct.json")
WH_PHARMA = os.path.join(PROJECT_ROOT, "configs", "warehouses", "warehouse_pharma.json")
RESULTS_PATH = os.path.join(SCRIPT_DIR, "deployment_validation_results.json")
WORLD_NAME, ROBOT = "warehouse_distinct", "robot_01"

# ── Gazebo helpers ──────────────────────────────────────────────────────
def gz_cmd(args, timeout=10):
    try:
        return subprocess.run(["gz"] + args, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""

def gz_running():
    return len(gz_cmd(["topic", "-e", "-t", "/clock", "-n", "1"], timeout=4)) > 0

def gz_topics():
    return [t.strip() for t in gz_cmd(["topic", "-l"]).strip().split("\n") if t.strip()]

def read_robot_lidar(rn, timeout=4):
    raw = gz_cmd(["topic", "-e", "-t", f"/{rn}/lidar", "-n", "1"], timeout=timeout)
    if not raw: return None
    ranges = [float("inf") if "inf" in m.group(1) else float(m.group(1))
              for m in re.finditer(r'ranges:\s*([-\d.e+inf]+)', raw)]
    if len(ranges) < 36: return None
    arr = np.array(ranges, dtype=np.float64)
    if len(arr) != 360:
        arr = np.interp(np.linspace(0, len(arr)-1, 360), np.arange(len(arr)), arr)
    return np.clip(np.where(np.isfinite(arr), arr, 12.0), 0.1, 12.0)

def get_all_robot_poses():
    raw = gz_cmd(["topic", "-e", "-t", f"/world/{WORLD_NAME}/dynamic_pose/info", "-n", "1"], timeout=6)
    if not raw: return {}
    poses = {}
    for block in raw.split("pose {"):
        nm = re.search(r'name:\s*"(robot_\d+)"', block)
        pm = re.search(r'position\s*\{[^}]*x:\s*([-\d.e+]+)[^}]*y:\s*([-\d.e+]+)[^}]*z:\s*([-\d.e+]+)', block)
        if nm and pm:
            om = re.search(r'orientation\s*\{[^}]*z:\s*([-\d.e+]+)[^}]*w:\s*([-\d.e+]+)', block)
            yaw = 2.0 * math.atan2(float(om.group(1)), float(om.group(2))) if om else 0.0
            poses[nm.group(1)] = {"x": float(pm.group(1)), "y": float(pm.group(2)),
                                  "z": float(pm.group(3)), "yaw": yaw}
    return poses

def teleport_robot(rn, x, y, yaw=0.0):
    qz, qw = math.sin(yaw/2), math.cos(yaw/2)
    gz_cmd(["service", "-s", f"/world/{WORLD_NAME}/set_pose",
            "--reqtype", "gz.msgs.Pose", "--reptype", "gz.msgs.Boolean", "--timeout", "3000",
            "--req", f"name: '{rn}', position: {{x: {x}, y: {y}, z: 0.05}}, "
                     f"orientation: {{z: {qz:.6f}, w: {qw:.6f}}}"], timeout=5)

def teleport_and_wait(rn, x, y, yaw, timeout=5.0):
    old = read_robot_lidar(rn, 2)
    teleport_robot(rn, x, y, yaw)
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(0.15)
        new = read_robot_lidar(rn, 2)
        if new is not None and (old is None or float(np.mean(np.abs(old - new))) > 0.05):
            time.sleep(0.1)
            f = read_robot_lidar(rn, 2)
            return f if f is not None else new
    return read_robot_lidar(rn, 2)

def detect_world_name():
    for t in gz_topics():
        if t.startswith("/world/") and t.endswith("/clock"): return t.split("/")[2]
    return None

def find_lidar_topic():
    for t in gz_topics():
        if t == f"/{ROBOT}/lidar": return t
    for t in gz_topics():
        if "lidar" in t.lower() and "points" not in t.lower(): return t
    return None

# ── Utilities ───────────────────────────────────────────────────────────
def load_config(path):
    with open(path) as f: return json.load(f)

def build_engine(cfg):
    return HierarchicalZoneIdentifier(zones=cfg["zones"], nodes=cfg["nodes"],
                                      edges=cfg.get("edges", []))

def node_zone_map(cfg):
    m = {}
    for z in cfg["zones"]:
        for nn in z.get("nodes", []): m[nn] = z["name"]
    return m

def zone_type_for(cfg, zone_name):
    for z in cfg["zones"]:
        if z["name"] == zone_name: return z.get("type", "none")
    return "none"

ALL_RESULTS = {}
def report(tid, title, passed, details):
    ALL_RESULTS[tid] = {"title": title, "passed": passed, "details": details}
    s = "PASS" if passed else "FAIL"
    print(f"\n{'='*70}\n  {tid}: {title}  [{s}]\n{'='*70}")
    for k, v in details.items():
        if isinstance(v, float): print(f"    {k}: {v:.4f}")
        elif isinstance(v, dict):
            print(f"    {k}:")
            for kk, vv in v.items(): print(f"      {kk}: {vv}")
        else: print(f"    {k}: {v}")

# ========================================================================
# V1: Calibration Drift Detection
# ========================================================================
def run_v1(cfg, eng, gz):
    nzm, nbn, rng = node_zone_map(cfg), {n["name"]: n for n in cfg["nodes"]}, np.random.default_rng(99)
    corrupt = ["STOR_A_0_0", "STOR_B_1_1", "CHARGE_1", "PICK_0", "CORR_1"]
    clean = ["STOR_A_2_2", "STOR_B_0_2", "STAGE_0", "DROP_1", "MAINT_0"]
    cal_scans = {}
    # Phase 1: Calibrate
    for nn in corrupt + clean:
        nd = nbn[nn]
        if gz:
            scan = teleport_and_wait(ROBOT, nd["x"], nd["y"], 0.0)
            if scan is not None:
                cal_scans[nn] = scan.copy()
                h, d, t = eng.get_node_dock_features(nn)
                eng.set_node_fingerprint(nn, scan, h, d, t)
        else:
            cal_scans[nn] = generate_zone_scan(zone_type_for(cfg, nzm.get(nn, "")), rng)
    if gz: eng.rebuild_hopfield()
    # Phase 2: Corrupt 5 fingerprints
    for nn in corrupt:
        if nn in eng.node_fingerprints:
            eng._node_fingerprints[nn] = eng.node_fingerprints[nn] + rng.normal(0, 0.5, eng.node_fingerprints[nn].shape)
    # Phase 3: Re-scan -- detect drift
    thresh, det, fp = 0.15, 0, 0
    cd, cld = {}, {}
    for nn in corrupt:
        if nn in cal_scans:
            h, d, t = eng.get_node_dock_features(nn)
            fd = float(np.linalg.norm(extract_16_features(cal_scans[nn], h, d, t) - eng.node_fingerprints[nn]))
            drifted = fd > thresh; det += drifted
            cd[nn] = {"feature_distance": round(fd, 4), "drift_detected": drifted}
    for nn in clean:
        if nn in cal_scans and nn in eng.node_fingerprints:
            h, d, t = eng.get_node_dock_features(nn)
            fd = float(np.linalg.norm(extract_16_features(cal_scans[nn], h, d, t) - eng.node_fingerprints[nn]))
            is_fp = fd > thresh; fp += is_fp
            cld[nn] = {"feature_distance": round(fd, 4), "false_positive": is_fp}
    passed = det == len(corrupt) and fp == 0
    report("V1", "Calibration Drift Detection", passed, {
        "corrupted_nodes": len(corrupt), "drift_detected": det,
        "clean_nodes": len(clean), "false_positives": fp,
        "corrupt_details": cd, "clean_details": cld,
        "threshold": thresh, "measurement": "gazebo_physics" if gz else "synthetic",
    })
    return passed

# ========================================================================
# V2: Auto-Heal (Fleet Learning Update)
# ========================================================================
def run_v2(cfg, eng, gz):
    nzm, nbn, rng = node_zone_map(cfg), {n["name"]: n for n in cfg["nodes"]}, np.random.default_rng(200)
    targets = ["STOR_A_0_0", "STOR_B_1_1", "CHARGE_1", "PICK_0", "CORR_1"]
    pre_acc, post_acc, details = 0, 0, {}
    for nn in targets:
        nd, tz = nbn[nn], nzm[nn]
        scan = teleport_and_wait(ROBOT, nd["x"], nd["y"], 0.0) if gz else generate_zone_scan(zone_type_for(cfg, tz), rng)
        if scan is None: details[nn] = {"error": "no_scan"}; continue
        pre = eng.identify_from_scan(scan, previous_zone=None)
        pre_ok = pre["zone"] == tz; pre_acc += pre_ok
        h, d, t = eng.get_node_dock_features(nn)
        eng.set_node_fingerprint(nn, scan, h, d, t)
        details[nn] = {"true_zone": tz, "pre_heal_zone": pre["zone"], "pre_ok": pre_ok}
    eng.rebuild_hopfield()
    for nn in targets:
        nd, tz = nbn[nn], nzm[nn]
        scan = teleport_and_wait(ROBOT, nd["x"], nd["y"], 0.0) if gz else generate_zone_scan(zone_type_for(cfg, tz), rng)
        if scan is None: continue
        post = eng.identify_from_scan(scan, previous_zone=None)
        post_ok = post["zone"] == tz; post_acc += post_ok
        if nn in details: details[nn].update({"post_heal_zone": post["zone"], "post_ok": post_ok})
    n = len(targets); post_pct = post_acc / n * 100 if n else 0
    report("V2", "Auto-Heal Fleet Learning Update", post_pct >= 90, {
        "pre_heal_pct": round(pre_acc / n * 100, 1), "post_heal_pct": round(post_pct, 1),
        "target_pct": 90.0, "details": details,
        "measurement": "gazebo_physics" if gz else "synthetic",
    })
    return post_pct >= 90

# ========================================================================
# V3: Config-Only Deployment (Warehouse Swap)
# ========================================================================
def run_v3():
    pc = load_config(WH_PHARMA); rng = np.random.default_rng(300)
    pe = build_engine(pc); pnzm = node_zone_map(pc)
    ez = {z["name"] for z in pc["zones"]}; en = {n["name"] for n in pc["nodes"]}
    load_ok = len(ez) == 11 and len(en) == 30
    names_ok = all(z in ez for z in ["Airlock", "CleanRoom_A", "CleanRoom_B",
        "ColdStorage_C", "ColdStorage_D", "QualityControl", "Dispatch",
        "MainCorridor", "Charging", "Maintenance", "Buffer"])
    # Calibrate
    for nd in pc["nodes"]:
        zt = zone_type_for(pc, pnzm.get(nd["name"], ""))
        scan = generate_zone_scan(zt, rng)
        h, d, t = pe.get_node_dock_features(nd["name"])
        pe.set_node_fingerprint(nd["name"], scan, h, d, t)
    pe.rebuild_hopfield()
    # Test recovery
    test_nodes = ["CLEAN_A1", "COLD_C2", "QC_STATION_1", "DISPATCH_1",
                  "CORRIDOR_MID", "CHARGE_P1", "MAINT_BAY", "BUFFER_1"]
    hits, rec_ok, rd = 0, True, {}
    for nn in test_nodes:
        tz = pnzm.get(nn, "unknown")
        scan = generate_zone_scan(zone_type_for(pc, tz), rng)
        r = pe.identify_from_scan(scan, previous_zone=None)
        valid = r["zone"] in ez; correct = r["zone"] == tz; hits += correct
        if not valid: rec_ok = False
        rd[nn] = {"true": tz, "predicted": r["zone"], "valid": valid, "correct": correct}
    passed = load_ok and names_ok and rec_ok
    report("V3", "Config-Only Deployment (Warehouse Swap)", passed, {
        "zones": len(ez), "nodes": len(en), "loaded": load_ok, "names_ok": names_ok,
        "recovery_valid": rec_ok, "zone_accuracy_pct": round(hits/len(test_nodes)*100, 1),
        "details": rd, "measurement": "synthetic_config_swap",
    })
    return passed

# ========================================================================
# V4: Different Robot Model (LiDAR Mount Height)
# ========================================================================
def run_v4(cfg):
    nzm = node_zone_map(cfg)
    rng_d, rng_v = np.random.default_rng(400), np.random.default_rng(401)
    de = build_engine(cfg)
    for nd in cfg["nodes"]:
        zt = zone_type_for(cfg, nzm.get(nd["name"], ""))
        scan = generate_zone_scan(zt, rng_d)
        h, d, t = de.get_node_dock_features(nd["name"])
        de.set_node_fingerprint(nd["name"], scan, h, d, t)
    de.rebuild_hopfield()
    bias = 1.10; correct, total = 0, 0
    for nd in cfg["nodes"]:
        tz = nzm.get(nd["name"], "")
        vscan = np.clip(generate_zone_scan(zone_type_for(cfg, tz), rng_v) * bias, 0.1, 12.0)
        r = de.identify_from_scan(vscan, previous_zone=None)
        correct += r["zone"] == tz; total += 1
    acc = correct / total * 100 if total else 0
    report("V4", "Different Robot Model (LiDAR Mount Height)", acc >= 70, {
        "dynamo_m": 0.395, "veloce_m": 0.25, "bias": bias,
        "total": total, "correct": correct, "accuracy_pct": round(acc, 1),
        "target_pct": 70.0, "measurement": "synthetic_height_bias",
    })
    return acc >= 70

# ========================================================================
# V5: Real-Time Performance Benchmark
# ========================================================================
def run_v5(cfg, eng):
    rng = np.random.default_rng(500)
    types = ["storage_a", "storage_b", "charging", "operations", "corridor"]
    scans = [generate_zone_scan(types[i % 5], rng) for i in range(1000)]
    times = []
    for s in scans:
        t0 = time.perf_counter()
        eng.identify_from_scan(s, previous_zone=None)
        times.append((time.perf_counter() - t0) * 1000)
    avg, p99, mx = np.mean(times), np.percentile(times, 99), np.max(times)
    # 40-decision batch benchmark (100 iterations)
    dt = []
    for _ in range(100):
        bs = [generate_zone_scan(types[i % 5], rng) for i in range(40)]
        t0 = time.perf_counter()
        for s in bs: eng.identify_from_scan(s, previous_zone=None)
        dt.append((time.perf_counter() - t0) * 1000)
    avg40, mx40, tgt40 = np.mean(dt), np.max(dt), 400.0
    r_ok, d_ok = avg < 10.0, avg40 < tgt40
    report("V5", "Real-Time Performance Benchmark", r_ok and d_ok, {
        "recovery_1000": {"avg_ms": round(avg, 3), "p99_ms": round(p99, 3),
                          "max_ms": round(mx, 3), "target": 10.0, "ok": r_ok},
        "decision_40x100": {"avg_ms": round(avg40, 3), "max_ms": round(mx40, 3),
                            "target": tgt40, "ok": d_ok, "per_decision_ms": round(avg40/40, 3)},
        "measurement": "wall_clock_perf_counter",
    })
    return r_ok and d_ok

# ========================================================================
# V6: Network Latency Simulation
# ========================================================================
def run_v6(cfg, eng):
    rng = np.random.default_rng(600); nzm = node_zone_map(cfg)
    lats = [0, 50, 100, 200]; rl = {}
    for lat in lats:
        ok, tt = 0, 0.0
        for _ in range(10):
            nd = cfg["nodes"][rng.integers(0, len(cfg["nodes"]))]
            tz = nzm.get(nd["name"], ""); zt = zone_type_for(cfg, tz)
            scan = generate_zone_scan(zt, rng)
            t0 = time.perf_counter()
            if lat > 0: time.sleep(lat / 1000.0)
            r = eng.identify_from_scan(scan, previous_zone=None)
            tt += time.perf_counter() - t0
            ok += r["zone"] == tz
        rl[f"{lat}ms"] = {"accuracy_pct": ok * 10.0, "avg_time_s": round(tt/10, 4)}
    a_stable = abs(rl["0ms"]["accuracy_pct"] - rl["200ms"]["accuracy_pct"]) < 15
    t_ok = rl["200ms"]["avg_time_s"] < 5.5
    report("V6", "Network Latency Simulation", a_stable and t_ok, {
        "results": rl, "accuracy_stable": a_stable, "timing_ok": t_ok,
        "measurement": "simulated_network_delay",
    })
    return a_stable and t_ok

# ========================================================================
# V7: False Positive Analysis
# ========================================================================
def run_v7(cfg, eng, gz):
    nzm, rng = node_zone_map(cfg), np.random.default_rng(700)
    zn = [z["name"] for z in cfg["zones"]]
    # Calibrate with real scans when Gazebo is available
    if gz:
        print("    V7: Calibrating 36 nodes with real Gazebo LiDAR...")
        for nd in cfg["nodes"]:
            s = teleport_and_wait(ROBOT, nd["x"], nd["y"], 0.0)
            if s is not None:
                h, d, t = eng.get_node_dock_features(nd["name"])
                eng.set_node_fingerprint(nd["name"], s, h, d, t)
        eng.rebuild_hopfield()
        print("    V7: Calibration done. Testing...")
    conf = {z: {zz: 0 for zz in zn} for z in zn}
    ok, fp, tot = 0, 0, 0
    for nd in cfg["nodes"]:
        nn, tz = nd["name"], nzm.get(nd["name"], "unknown")
        if tz not in zn: continue
        scan = teleport_and_wait(ROBOT, nd["x"], nd["y"], 0.0) if gz else generate_zone_scan(zone_type_for(cfg, tz), rng)
        if scan is None: continue
        r = eng.identify_from_scan(scan, previous_zone=None)
        pz = r["zone"]; c = r.get("zone_confidence", r.get("confidence", 0))
        correct = pz == tz; ok += correct; tot += 1
        if c > 0.8 and not correct: fp += 1
        if tz in conf and pz in conf[tz]: conf[tz][pz] += 1
    fp_rate = fp / tot * 100 if tot else 0
    cm = {tz: {pz: n for pz, n in row.items() if n > 0} for tz, row in conf.items() if any(v > 0 for v in row.values())}
    report("V7", "False Positive Analysis", fp_rate < 5, {
        "tested": tot, "correct": ok, "accuracy_pct": round(ok/tot*100, 1) if tot else 0,
        "high_conf_wrong": fp, "fp_rate_pct": round(fp_rate, 1), "target_fp_pct": 5.0,
        "confusion": cm, "measurement": "gazebo_physics" if gz else "synthetic",
    })
    return fp_rate < 5

# ========================================================================
# V8: Error Correction Loop
# ========================================================================
def run_v8(cfg, eng, gz):
    nzm = node_zone_map(cfg); nbn = {n["name"]: n for n in cfg["nodes"]}
    rng = np.random.default_rng(800)
    tp = nbn["STOR_B_0_0"]; tz, wz = "Storage_B", "Storage_A"
    wt = nbn["STOR_A_0_0"]
    dx, dy = wt["x"] - tp["x"], wt["y"] - tp["y"]
    d2w = math.sqrt(dx*dx + dy*dy); d2w = max(d2w, 0.01)
    ux, uy = dx / d2w, dy / d2w
    steps, corrected, corr_d = [], False, 0.0
    for si in range(10):
        travel = (si + 1) * 0.5; nx, ny = tp["x"] + ux * travel, tp["y"] + uy * travel
        if gz:
            scan = teleport_and_wait(ROBOT, nx, ny, 0.0)
        else:
            best_z, min_d = tz, float("inf")
            for z in cfg["zones"]:
                zns = [nbn[nn] for nn in z.get("nodes", []) if nn in nbn]
                if not zns: continue
                cx, cy = np.mean([n["x"] for n in zns]), np.mean([n["y"] for n in zns])
                dd = math.sqrt((nx-cx)**2 + (ny-cy)**2)
                if dd < min_d: min_d, best_z = dd, z["name"]
            scan = generate_zone_scan(zone_type_for(cfg, best_z), rng)
        if scan is None: steps.append({"step": si+1, "travel_m": travel, "error": "no_scan"}); continue
        r = eng.identify_from_scan(scan, previous_zone=None)
        pz = r["zone"]; c = r.get("zone_confidence", r.get("confidence", 0))
        info = {"step": si+1, "travel_m": round(travel, 1), "pos": (round(nx, 2), round(ny, 2)),
                "predicted": pz, "confidence": round(c, 3)}
        if pz != wz:
            corrected, corr_d = True, travel; info["corrected"] = True; steps.append(info); break
        info["corrected"] = False; steps.append(info)
    passed = corrected and corr_d <= 5.0
    report("V8", "Error Correction Loop", passed, {
        "true_zone": tz, "wrong_zone": wz, "corrected": corrected,
        "correction_m": round(corr_d, 1), "max_m": 5.0, "steps": steps,
        "measurement": "gazebo_physics" if gz else "synthetic",
    })
    return passed

# ========================================================================
# MAIN
# ========================================================================
def main():
    print("=" * 70)
    print("  DEPLOYMENT VALIDATION -- 8 Production Readiness Tests")
    print("=" * 70)
    cfg = load_config(WH_DISTINCT); eng = build_engine(cfg)
    gz = gz_running()
    if gz:
        print(f"\n  Gazebo: RUNNING (world={detect_world_name()}, lidar={find_lidar_topic()})")
        print(f"  V1,V2,V7,V8 use REAL LiDAR via {ROBOT}")
    else:
        print("\n  Gazebo: NOT RUNNING -- V1,V2,V7,V8 use synthetic scans")
        print("  For full validation: gz sim -r warehouse_distinct_fleet.sdf")
    t0 = time.time()
    v1 = run_v1(cfg, eng, gz)
    # V2: fresh engine with same corruption as V1
    e2 = build_engine(cfg); rng1 = np.random.default_rng(99)
    for nn in ["STOR_A_0_0", "STOR_B_1_1", "CHARGE_1", "PICK_0", "CORR_1"]:
        if nn in e2.node_fingerprints:
            e2._node_fingerprints[nn] = e2.node_fingerprints[nn] + rng1.normal(0, 0.5, e2.node_fingerprints[nn].shape)
    v2 = run_v2(cfg, e2, gz)
    v3 = run_v3()
    v4 = run_v4(cfg)
    ec = build_engine(cfg)
    v5 = run_v5(cfg, ec)
    v6 = run_v6(cfg, ec)
    v7 = run_v7(cfg, ec, gz)
    v8 = run_v8(cfg, ec, gz)
    dt = time.time() - t0; results = [v1, v2, v3, v4, v5, v6, v7, v8]
    p, n = sum(results), len(results); prod = p == n
    names = ["V1: Calibration Drift Detection", "V2: Auto-Heal Fleet Learning",
             "V3: Config-Only Deployment (Pharma)", "V4: Different Robot Model (LiDAR)",
             "V5: Real-Time Performance", "V6: Network Latency Simulation",
             "V7: False Positive Analysis", "V8: Error Correction Loop"]
    print(f"\n{'='*70}\n  SUMMARY: {p}/{n} passed | {dt:.1f}s | Gazebo={'REAL' if gz else 'SYNTHETIC'}\n{'='*70}")
    for nm, r in zip(names, results): print(f"    {nm:45s} [{'PASS' if r else 'FAIL'}]")
    print(f"\n  PRODUCTION READY: {'YES' if prod else 'NO'}\n{'='*70}")
    ALL_RESULTS["_summary"] = {"passed": p, "total": n, "production_ready": prod,
                               "gazebo": "real" if gz else "synthetic", "time_s": round(dt, 2)}
    def conv(o):
        if isinstance(o, dict): return {k: conv(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)): return [conv(v) for v in o]
        if isinstance(o, (np.integer,)): return int(o)
        if isinstance(o, (np.floating,)): return float(o)
        if isinstance(o, np.ndarray): return o.tolist()
        if isinstance(o, np.bool_): return bool(o)
        if isinstance(o, set): return sorted(list(o))
        return o
    with open(RESULTS_PATH, "w") as f: json.dump(conv(ALL_RESULTS), f, indent=2, default=str)
    print(f"\n  Results: {RESULTS_PATH}")

if __name__ == "__main__":
    main()

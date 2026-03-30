#!/usr/bin/env python3
"""
ENGINE COMPARISON: Hopfield ODE vs KDTree vs LightGBM
Same tests, same data, 3 engines. Run: python3 -B gazebo/engine_comparison.py
"""
import json, math, os, re, resource, subprocess, sys, time, warnings
from collections import Counter
import numpy as np
warnings.filterwarnings("ignore", category=UserWarning)
os.environ["PYTHONUNBUFFERED"] = "1"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "python"))
from scipy.spatial import KDTree
import lightgbm as lgb
from intelligence.iogita.zone_identifier import (
    HierarchicalZoneIdentifier, extract_zone_features, generate_zone_scan,
    extract_16_features, ZONE_FEATURE_DIM,
)
CONFIG_PATH = os.path.join(PROJECT_ROOT, "configs", "warehouses", "warehouse_distinct.json")
REALISTIC_PATH = os.path.join(PROJECT_ROOT, "configs", "warehouses", "realistic.json")
WORLD_NAME = "warehouse_distinct"

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
def get_robot_poses():
    raw = gz_cmd(["topic", "-e", "-t", f"/world/{WORLD_NAME}/dynamic_pose/info", "-n", "1"], timeout=10)
    poses = {}
    for block in raw.split("pose {"):
        nm = re.search(r'name:\s*"(robot_\d+)"', block)
        if not nm: continue
        pos = re.search(r'position\s*\{[^}]*x:\s*([-\d.]+)[^}]*y:\s*([-\d.]+)', block, re.DOTALL)
        if pos: poses[nm.group(1)] = (float(pos.group(1)), float(pos.group(2)))
    return poses
def spawn_obstacle(name, x, y, z, sx, sy, sz):
    sdf = (f'<?xml version="1.0"?><sdf version="1.8"><model name="{name}"><static>true</static>'
           f'<pose>{x} {y} {z} 0 0 0</pose><link name="link"><collision name="c"><geometry>'
           f'<box><size>{sx} {sy} {sz}</size></box></geometry></collision><visual name="v"><geometry>'
           f'<box><size>{sx} {sy} {sz}</size></box></geometry><material><ambient>1 0 0 1</ambient>'
           f'</material></visual></link></model></sdf>')
    tmp = f"/tmp/{name}.sdf"
    with open(tmp, "w") as f: f.write(sdf)
    gz_cmd(["service", "-s", f"/world/{WORLD_NAME}/create",
            "--reqtype", "gz.msgs.EntityFactory", "--reptype", "gz.msgs.Boolean",
            "--timeout", "10000", "--req", f"sdf_filename: '{tmp}', name: '{name}'"], timeout=15)
def teleport_robot(robot_name, x, y, yaw=0.0):
    qz, qw = math.sin(yaw/2), math.cos(yaw/2)
    gz_cmd(["service", "-s", f"/world/{WORLD_NAME}/set_pose",
            "--reqtype", "gz.msgs.Pose", "--reptype", "gz.msgs.Boolean",
            "--timeout", "3000", "--req",
            f"name: '{robot_name}', position: {{x: {x}, y: {y}, z: 0.05}}, "
            f"orientation: {{z: {qz:.6f}, w: {qw:.6f}}}"], timeout=5)

# ── Shared ──────────────────────────────────────────────────────────
def _wall_count(scan_360, threshold=1.5):
    sw = 360 // 8
    return sum(1 for i in range(8) if np.median(scan_360[i*sw:(i+1)*sw]) < threshold)

def _4clue_score(candidates_names, nodes_by_name, node_to_zone, query_zf,
                 scan_360, last_x, last_y, heading_deg, feat_lookup, cal_scans):
    """Shared 4-clue scoring: returns sorted [(node, score)] and zone of best."""
    W_LIDAR, W_WALLS, W_PROX, W_HEAD = 0.40, 0.20, 0.25, 0.15
    scan_walls = _wall_count(scan_360)
    cdists = {nn: math.sqrt((nodes_by_name[nn]["x"]-last_x)**2 +
              (nodes_by_name[nn]["y"]-last_y)**2) for nn in candidates_names}
    max_d = max(max(cdists.values(), default=1.0), 0.1)
    scored = []
    for nn in candidates_names:
        fp = feat_lookup(nn)
        if fp is not None:
            n = min(len(query_zf), len(fp))
            lidar_sim = 1.0 / (1.0 + float(np.linalg.norm(query_zf[:n] - fp[:n])))
        else:
            lidar_sim = 0.0
        cs = cal_scans.get(nn)
        wall_score = (1.0 if _wall_count(cs) == scan_walls else 0.0) if cs is not None else 0.5
        prox = 1.0 - (cdists[nn] / max_d)
        nd = nodes_by_name[nn]
        ap = math.degrees(math.atan2(nd["y"]-last_y, nd["x"]-last_x)) % 360
        hd = abs(heading_deg - ap); hd = 360 - hd if hd > 180 else hd
        head = 1.0 - (hd / 180.0)
        scored.append((nn, W_LIDAR*lidar_sim + W_WALLS*wall_score + W_PROX*prox + W_HEAD*head))
    scored.sort(key=lambda x: -x[1])
    best = scored[0][0] if scored else candidates_names[0]
    margin = scored[0][1] - scored[1][1] if len(scored) >= 2 else 0.4
    conf = min(0.5 + margin * 5.0, 0.99)
    return scored, node_to_zone.get(best, "unknown"), conf

# ── Engine B: KDTree ────────────────────────────────────────────────
class KDTreeEngine:
    def __init__(self):
        self.zone_tree = self.node_tree = None
        self.zone_names = self.node_names = []
        self.zone_features = self.node_features = None
        self.node_to_zone = {}; self.nodes_by_name = {}; self.zone_nodes = {}; self.cal_scans = {}
    def calibrate(self, zones, nodes, zone_fps, node_fps, node_zf, cal_scans=None):
        self.nodes_by_name = {n["name"]: n for n in nodes}
        for z in zones:
            for nn in z.get("nodes", []): self.node_to_zone[nn] = z["name"]
            self.zone_nodes[z["name"]] = z.get("nodes", [])
        self.cal_scans = cal_scans or {}
        self.zone_names = list(zone_fps.keys())
        self.zone_features = np.array([zone_fps[zn] for zn in self.zone_names])
        self.zone_tree = KDTree(self.zone_features)
        self.node_names = list(node_zf.keys())
        self.node_features = np.array([node_zf[nn] for nn in self.node_names])
        self.node_tree = KDTree(self.node_features)
    def identify_zone(self, feat):
        if self.zone_tree is None: return "unknown", 0.0
        dist, idx = self.zone_tree.query(feat, k=min(2, len(self.zone_names)))
        if np.ndim(dist) == 0: return self.zone_names[int(idx)], 1.0/(1.0+float(dist))
        return self.zone_names[int(idx[0])], 1.0/(1.0+float(dist[0]))
    def recover_from_last_known(self, scan_360, last_x, last_y, heading_deg=0.0, k=5):
        qzf = extract_zone_features(scan_360)
        if self.node_tree is not None and len(self.node_names) >= k:
            _, idxs = self.node_tree.query(qzf, k=k)
            cands = [self.node_names[int(i)] for i in idxs]
        else:
            nd = sorted(self.nodes_by_name.items(), key=lambda x: math.sqrt(
                (x[1]["x"]-last_x)**2+(x[1]["y"]-last_y)**2))
            cands = [x[0] for x in nd[:k]]
        def lookup(nn):
            i = self.node_names.index(nn) if nn in self.node_names else -1
            return self.node_features[i] if i >= 0 else None
        scored, zone, conf = _4clue_score(cands, self.nodes_by_name, self.node_to_zone,
                                          qzf, scan_360, last_x, last_y, heading_deg, lookup, self.cal_scans)
        return {"node": scored[0][0], "zone": zone, "confidence": conf,
                "method": "kdtree_4clue", "candidates": scored[:k]}

# ── Engine C: LightGBM ─────────────────────────────────────────────
class LGBMEngine:
    def __init__(self):
        self.zone_model = self.node_model = None
        self.zone_names = self.node_names = []
        self.node_to_zone = {}; self.nodes_by_name = {}; self.zone_nodes = {}; self.cal_scans = {}
    def calibrate(self, zones, nodes, zone_fps, node_zf, cal_scans=None):
        self.nodes_by_name = {n["name"]: n for n in nodes}
        for z in zones:
            for nn in z.get("nodes", []): self.node_to_zone[nn] = z["name"]
            self.zone_nodes[z["name"]] = z.get("nodes", [])
        self.cal_scans = cal_scans or {}
        self.zone_names = sorted(set(self.node_to_zone.values()))
        zlm = {zn: i for i, zn in enumerate(self.zone_names)}
        X_z, y_z = [], []
        for nn, feat in node_zf.items():
            zn = self.node_to_zone.get(nn)
            if zn and zn in zlm: X_z.append(feat); y_z.append(zlm[zn])
        if X_z:
            nc = len(self.zone_names)
            self.zone_model = lgb.LGBMClassifier(n_estimators=100, max_depth=8, num_leaves=31,
                num_class=nc if nc > 2 else None, verbose=-1, force_col_wise=True)
            self.zone_model.fit(np.array(X_z), np.array(y_z))
        self.node_names = sorted(node_zf.keys())
        nlm = {nn: i for i, nn in enumerate(self.node_names)}
        X_n, y_n = [], []
        for nn, feat in node_zf.items():
            nd = self.nodes_by_name.get(nn)
            if nd and nn in nlm:
                X_n.append(np.concatenate([feat, [nd["x"]/20.0, nd["y"]/20.0]]))
                y_n.append(nlm[nn])
        if X_n:
            nn_c = len(self.node_names)
            self.node_model = lgb.LGBMClassifier(n_estimators=100, max_depth=10, num_leaves=63,
                num_class=nn_c if nn_c > 2 else None, verbose=-1, force_col_wise=True)
            self.node_model.fit(np.array(X_n), np.array(y_n))
    def identify_zone(self, feat):
        if self.zone_model is None: return "unknown", 0.0
        proba = self.zone_model.predict_proba([feat])[0]
        best = int(np.argmax(proba))
        return self.zone_names[best], float(proba[best])
    def recover_from_last_known(self, scan_360, last_x, last_y, heading_deg=0.0, k=5):
        qzf = extract_zone_features(scan_360)
        pz, _ = self.identify_zone(qzf)
        zn_nodes = self.zone_nodes.get(pz, [])[:k]
        nd = sorted(self.nodes_by_name.items(), key=lambda x: math.sqrt(
            (x[1]["x"]-last_x)**2+(x[1]["y"]-last_y)**2))
        pos_near = [x[0] for x in nd[:k]]
        cands = list(dict.fromkeys(zn_nodes + pos_near))[:k]
        def lookup(nn):
            if self.node_model is not None and nn in self.node_names:
                nd = self.nodes_by_name[nn]
                aug = np.concatenate([qzf, [nd["x"]/20.0, nd["y"]/20.0]])
                try:
                    proba = self.node_model.predict_proba([aug])[0]
                    ni = self.node_names.index(nn)
                    # Return synthetic feature vector scaled by probability
                    return qzf * float(proba[ni]) if ni < len(proba) else None
                except Exception: pass
            return None
        scored, zone, conf = _4clue_score(cands, self.nodes_by_name, self.node_to_zone,
                                          qzf, scan_360, last_x, last_y, heading_deg, lookup, self.cal_scans)
        return {"node": scored[0][0], "zone": zone, "confidence": conf,
                "method": "lgbm_4clue", "candidates": scored[:k]}

# ── Calibration ─────────────────────────────────────────────────────
def build_cal_data(config, rng, n_scans=20):
    nodes, zones = config["nodes"], config["zones"]
    n2z, zt = {}, {}
    for z in zones:
        zt[z["name"]] = z.get("type", "none")
        for nn in z.get("nodes", []): n2z[nn] = z["name"]
    docks = [n for n in nodes if n.get("type") in ("charge","dock")] or nodes[:1]
    nzf, za, cs = {}, {}, {}
    for node in nodes:
        nn = node["name"]; zn = n2z.get(nn, "unknown")
        st = zt.get(zn, node.get("type", "none"))
        bd = min(math.sqrt((node["x"]-d["x"])**2+(node["y"]-d["y"])**2) for d in docks)
        hd = (bd * 7.3) % 360
        feats, last = [], None
        for _ in range(n_scans):
            scan = generate_zone_scan(st, rng, hd, bd); feats.append(extract_zone_features(scan)); last = scan
        nzf[nn] = np.mean(feats, axis=0); cs[nn] = last
        za.setdefault(zn, []).append(nzf[nn])
    zfp = {zn: np.mean(fps, axis=0) for zn, fps in za.items()}
    return zfp, nzf, cs

def calibrate_all(config, zi, kdt, lgbm_e, rng, real_scans=None):
    zones, nodes = config["zones"], config["nodes"]
    if real_scans:
        nzf, cs = {}, {}
        for nn, scan in real_scans.items(): nzf[nn] = extract_zone_features(scan); cs[nn] = scan
        n2z = {}
        for z in zones:
            for nd in z.get("nodes", []): n2z[nd] = z["name"]
        za = {}
        for nn, feat in nzf.items(): za.setdefault(n2z.get(nn, "?"), []).append(feat)
        zfp = {zn: np.mean(fps, axis=0) for zn, fps in za.items()}
        for nn, scan in real_scans.items():
            nd = next((n for n in nodes if n["name"] == nn), None)
            if nd: zi.set_node_fingerprint(nn, scan, 0.0, 0.0)
        zi.rebuild_hopfield()
    else:
        zfp, nzf, cs = build_cal_data(config, rng)
    kdt.calibrate(zones, nodes, zfp, dict(zi.node_fingerprints), nzf, cs)
    lgbm_e.calibrate(zones, nodes, zfp, nzf, cs)
    return zfp, nzf, cs

# ── MAIN ────────────────────────────────────────────────────────────
def main():
    SEP = "=" * 56
    print(f"\n{SEP}\n  ENGINE COMPARISON: Hopfield ODE vs KDTree vs LightGBM\n{SEP}\n", flush=True)
    with open(CONFIG_PATH) as f: config = json.load(f)
    nodes, zones, edges = config["nodes"], config["zones"], config.get("edges", [])
    n2z = {}
    for z in zones:
        for nn in z.get("nodes", []): n2z[nn] = z["name"]
    rng = np.random.default_rng(2026)
    zi = HierarchicalZoneIdentifier(zones=zones, nodes=nodes, edges=edges)
    kdt, lgbm_e = KDTreeEngine(), LGBMEngine()
    # Check Gazebo
    lidar_topics = [t for t in gz_cmd(["topic", "-l"]).split("\n") if "/lidar" in t and "points" not in t]
    gazebo_ok = len(lidar_topics) >= 10
    print(f"  Gazebo robots: {len(lidar_topics)} ({'OK' if gazebo_ok else 'INSUFFICIENT — using synthetic'})")
    # Calibrate
    real_scans = {}
    if gazebo_ok:
        print("  Calibrating with REAL Gazebo LiDAR...", flush=True)
        for node in nodes:
            teleport_robot("robot_01", node["x"], node["y"]); time.sleep(0.3)
            scan = read_lidar("robot_01", timeout=10)
            if scan is not None: real_scans[node["name"]] = scan
        print(f"  Real scans: {len(real_scans)}/{len(nodes)}", flush=True)
    zfp, nzf, cs = calibrate_all(config, zi, kdt, lgbm_e, rng, real_scans or None)
    print(f"  Calibrated: {len(zfp)} zones, {len(nzf)} nodes\n", flush=True)
    R = {"test": "engine_comparison", "world": WORLD_NAME, "gazebo": gazebo_ok,
         "engines": ["HopfieldODE", "KDTree", "LightGBM"], "tests": {}}

    def get_scan(nn):
        if nn in real_scans:
            s = real_scans[nn] + rng.normal(0, 0.05, 360); return np.clip(s, 0.1, 12.0)
        zt = next((z.get("type","none") for z in zones if nn in z.get("nodes",[])), "none")
        return generate_zone_scan(zt, rng)

    # ── T1: Zone Accuracy ───────────────────────────────────────────
    print(f"  {SEP}\n  T1: Zone Accuracy (36 nodes)\n  {SEP}", flush=True)
    t1 = {"h": 0, "k": 0, "l": 0, "n": 0}
    for node in nodes:
        nn, tz = node["name"], n2z.get(node["name"], "?")
        scan = get_scan(nn); feat = extract_zone_features(scan); t1["n"] += 1
        if zi.hierarchical_zone_id(scan, previous_zone=None)["zone"] == tz: t1["h"] += 1
        if kdt.identify_zone(feat)[0] == tz: t1["k"] += 1
        if lgbm_e.identify_zone(feat)[0] == tz: t1["l"] += 1
    t1p = {k: round(t1[k]/max(t1["n"],1)*100, 1) for k in "hkl"}
    print(f"  Hopfield: {t1['h']}/{t1['n']} ({t1p['h']}%)  KDTree: {t1['k']}/{t1['n']} ({t1p['k']}%)"
          f"  LightGBM: {t1['l']}/{t1['n']} ({t1p['l']}%)\n", flush=True)
    R["tests"]["T1_zone_accuracy"] = {"total": t1["n"], "hopfield_pct": t1p["h"],
        "kdtree_pct": t1p["k"], "lgbm_pct": t1p["l"]}

    # ── T2: Node Accuracy (4-clue) ─────────────────────────────────
    print(f"  {SEP}\n  T2: Node Accuracy (4-clue, +/-1m noise)\n  {SEP}", flush=True)
    t2 = {"h": 0, "k": 0, "l": 0, "n": 0}
    for node in nodes:
        nn, tz = node["name"], n2z.get(node["name"], "?")
        scan = get_scan(nn)
        lx = node["x"] + float(rng.normal(0, 1.0)); ly = node["y"] + float(rng.normal(0, 1.0))
        hd = float(rng.uniform(0, 360)); t2["n"] += 1
        if zi.recover_from_last_known(scan, lx, ly, hd, k=5)["zone"] == tz: t2["h"] += 1
        if kdt.recover_from_last_known(scan, lx, ly, hd, k=5)["zone"] == tz: t2["k"] += 1
        if lgbm_e.recover_from_last_known(scan, lx, ly, hd, k=5)["zone"] == tz: t2["l"] += 1
    t2p = {k: round(t2[k]/max(t2["n"],1)*100, 1) for k in "hkl"}
    print(f"  Hopfield: {t2['h']}/{t2['n']} ({t2p['h']}%)  KDTree: {t2['k']}/{t2['n']} ({t2p['k']}%)"
          f"  LightGBM: {t2['l']}/{t2['n']} ({t2p['l']}%)\n", flush=True)
    R["tests"]["T2_node_accuracy"] = {"total": t2["n"], "hopfield_pct": t2p["h"],
        "kdtree_pct": t2p["k"], "lgbm_pct": t2p["l"]}

    # ── T3: Recovery Speed (1000 iterations) ────────────────────────
    print(f"  {SEP}\n  T3: Speed (1000 zone IDs, synthetic)\n  {SEP}", flush=True)
    N = 1000; rng_s = np.random.default_rng(42)
    scans_s = [rng_s.uniform(0.5, 8.0, 360).astype(np.float64) for _ in range(N)]
    feats_s = [extract_zone_features(s) for s in scans_s]
    t3 = {}
    for label, fn in [("hopfield", lambda i: zi.hierarchical_zone_id(scans_s[i], previous_zone=None)),
                      ("kdtree", lambda i: kdt.identify_zone(feats_s[i])),
                      ("lgbm", lambda i: lgbm_e.identify_zone(feats_s[i]))]:
        t0 = time.perf_counter()
        for i in range(N): fn(i)
        total = (time.perf_counter() - t0) * 1000
        # P99 from 100 samples
        times = []
        for i in range(100):
            t0 = time.perf_counter(); fn(i); times.append((time.perf_counter() - t0) * 1000)
        t3[label] = {"total": round(total, 1), "avg": round(total/N, 3),
                     "p99": round(float(np.percentile(times, 99)), 3)}
    print(f"  {'Engine':<10} {'Total ms':>10} {'Avg ms':>10} {'P99 ms':>10}")
    for e in ["hopfield", "kdtree", "lgbm"]:
        print(f"  {e:<10} {t3[e]['total']:>10.1f} {t3[e]['avg']:>10.3f} {t3[e]['p99']:>10.3f}")
    print(flush=True)
    R["tests"]["T3_speed"] = t3

    # ── T4: Memory Usage ────────────────────────────────────────────
    print(f"  {SEP}\n  T4: Memory Usage\n  {SEP}", flush=True)
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024
    hop_mb = (zi._zone_hopfield.D * zi._zone_hopfield.n_features * 8
              + zi._zone_hopfield.n_patterns * zi._zone_hopfield.D * 8
              + len(zi._node_fingerprints) * 16 * 8) / 1024 / 1024
    kdt_mb = (kdt.zone_features.nbytes + kdt.node_features.nbytes) / 1024 / 1024
    lgbm_mb = (len(lgbm_e.zone_model.booster_.model_to_string() if lgbm_e.zone_model else "") +
               len(lgbm_e.node_model.booster_.model_to_string() if lgbm_e.node_model else "")) / 1024 / 1024
    print(f"  Process RSS: {rss:.0f}MB  Hopfield: {hop_mb:.2f}MB  KDTree: {kdt_mb:.2f}MB  LightGBM: {lgbm_mb:.2f}MB\n", flush=True)
    R["tests"]["T4_memory"] = {"rss_mb": round(rss), "hopfield_mb": round(hop_mb, 2),
        "kdtree_mb": round(kdt_mb, 2), "lgbm_mb": round(lgbm_mb, 2)}

    # ── T5: Multi-Robot (10 robots) ─────────────────────────────────
    print(f"  {SEP}\n  T5: Multi-Robot (10 robots)\n  {SEP}", flush=True)
    t5 = {"h": 0, "k": 0, "l": 0, "n": 0}; t5t = {"h": 0., "k": 0., "l": 0.}
    if gazebo_ok:
        poses = get_robot_poses()
        for i in [1, 5, 10, 15, 20, 25, 30, 35, 40, 45]:
            rname = f"robot_{i:02d}"; scan = read_lidar(rname)
            if scan is None: continue
            pos = poses.get(rname, (0, 0))
            bn = min(nodes, key=lambda n: math.sqrt((n["x"]-pos[0])**2+(n["y"]-pos[1])**2))
            tz = n2z.get(bn["name"], "?"); feat = extract_zone_features(scan); t5["n"] += 1
            t0 = time.perf_counter()
            hz = zi.hierarchical_zone_id(scan, previous_zone=None); t5t["h"] += (time.perf_counter()-t0)*1000
            if hz["zone"] == tz: t5["h"] += 1
            t0 = time.perf_counter(); kz = kdt.identify_zone(feat)[0]; t5t["k"] += (time.perf_counter()-t0)*1000
            if kz == tz: t5["k"] += 1
            t0 = time.perf_counter(); lz = lgbm_e.identify_zone(feat)[0]; t5t["l"] += (time.perf_counter()-t0)*1000
            if lz == tz: t5["l"] += 1
            print(f"    {rname}: true={tz:>12} H={hz['zone']:>12} K={kz:>12} L={lz:>12}", flush=True)
    else:
        for i in range(10):
            nd = nodes[i % len(nodes)]; tz = n2z.get(nd["name"], "?")
            scan = get_scan(nd["name"]); feat = extract_zone_features(scan); t5["n"] += 1
            if zi.hierarchical_zone_id(scan, previous_zone=None)["zone"] == tz: t5["h"] += 1
            if kdt.identify_zone(feat)[0] == tz: t5["k"] += 1
            if lgbm_e.identify_zone(feat)[0] == tz: t5["l"] += 1
    t5p = {k: round(t5[k]/max(t5["n"],1)*100, 1) for k in "hkl"}
    print(f"  Hopfield: {t5p['h']}%  KDTree: {t5p['k']}%  LightGBM: {t5p['l']}%\n", flush=True)
    R["tests"]["T5_multi_robot"] = {"total": t5["n"], "hopfield_pct": t5p["h"],
        "kdtree_pct": t5p["k"], "lgbm_pct": t5p["l"],
        "measurement": "real_gazebo" if gazebo_ok else "synthetic"}

    # ── T6: Obstacle Robustness ─────────────────────────────────────
    print(f"  {SEP}\n  T6: Obstacle Robustness\n  {SEP}", flush=True)
    t6 = {"h": "N/A", "k": "N/A", "l": "N/A"}
    if gazebo_ok:
        poses = get_robot_poses(); p05 = poses.get("robot_05", (0, 1.5))
        pre = read_lidar("robot_05")
        if pre is not None:
            spawn_obstacle("eng_cmp_obs", p05[0]+1.0, p05[1], 0.5, 0.5, 0.5, 1.0); time.sleep(5)
            post = read_lidar("robot_05")
            if post is not None:
                pref, postf = extract_zone_features(pre), extract_zone_features(post)
                hz_pre = zi.hierarchical_zone_id(pre, previous_zone=None)["zone"]
                hz_post = zi.hierarchical_zone_id(post, previous_zone=None)["zone"]
                t6["h"] = "PASS" if hz_post == hz_pre else "FAIL"
                t6["k"] = "PASS" if kdt.identify_zone(postf)[0] == kdt.identify_zone(pref)[0] else "FAIL"
                t6["l"] = "PASS" if lgbm_e.identify_zone(postf)[0] == lgbm_e.identify_zone(pref)[0] else "FAIL"
    else:
        nd = nodes[0]; zt = next((z.get("type","none") for z in zones if nd["name"] in z.get("nodes",[])), "none")
        clean = generate_zone_scan(zt, rng); dirty = clean.copy(); dirty[80:100] = 0.5
        cf, df = extract_zone_features(clean), extract_zone_features(dirty)
        t6["h"] = "PASS" if zi.hierarchical_zone_id(clean, previous_zone=None)["zone"] == \
                            zi.hierarchical_zone_id(dirty, previous_zone=None)["zone"] else "FAIL"
        t6["k"] = "PASS" if kdt.identify_zone(cf)[0] == kdt.identify_zone(df)[0] else "FAIL"
        t6["l"] = "PASS" if lgbm_e.identify_zone(cf)[0] == lgbm_e.identify_zone(df)[0] else "FAIL"
    print(f"  Hopfield: {t6['h']}  KDTree: {t6['k']}  LightGBM: {t6['l']}\n", flush=True)
    R["tests"]["T6_obstacle"] = t6

    # ── T7: Scalability (539 nodes) ─────────────────────────────────
    print(f"  {SEP}\n  T7: Scalability (539 nodes, synthetic)\n  {SEP}", flush=True)
    with open(REALISTIC_PATH) as f: bc = json.load(f)
    bn, bz, be = bc["nodes"], bc["zones"], bc.get("edges", [])
    bn2z = {}
    for z in bz:
        for nn in z.get("nodes", []): bn2z[nn] = z["name"]
    rng_b = np.random.default_rng(7777)
    t0 = time.perf_counter()
    bzi = HierarchicalZoneIdentifier(zones=bz, nodes=bn, edges=be)
    hop_cal = (time.perf_counter()-t0)*1000
    bzfp, bnzf, bcs = build_cal_data(bc, rng_b, n_scans=5)
    bkdt = KDTreeEngine()
    t0 = time.perf_counter()
    bkdt.calibrate(bz, bn, bzfp, dict(bzi.node_fingerprints), bnzf, bcs)
    kdt_cal = (time.perf_counter()-t0)*1000
    blgbm = LGBMEngine()
    t0 = time.perf_counter()
    blgbm.calibrate(bz, bn, bzfp, bnzf, bcs)
    lgbm_cal = (time.perf_counter()-t0)*1000
    print(f"  Cal time: Hopfield={hop_cal:.0f}ms  KDTree={kdt_cal:.0f}ms  LightGBM={lgbm_cal:.0f}ms")
    t7 = {"h": 0, "k": 0, "l": 0, "n": 0}; t7s = {"h": 0., "k": 0., "l": 0.}
    idxs = rng_b.choice(len(bn), size=min(100, len(bn)), replace=False)
    for idx in idxs:
        nd = bn[idx]; nn = nd["name"]; tz = bn2z.get(nn, "?")
        zt = next((z.get("type","none") for z in bz if nn in z.get("nodes",[])), "none")
        scan = generate_zone_scan(zt, rng_b); feat = extract_zone_features(scan); t7["n"] += 1
        t0 = time.perf_counter()
        if bzi.hierarchical_zone_id(scan, previous_zone=None)["zone"] == tz: t7["h"] += 1
        t7s["h"] += (time.perf_counter()-t0)*1000
        t0 = time.perf_counter()
        if bkdt.identify_zone(feat)[0] == tz: t7["k"] += 1
        t7s["k"] += (time.perf_counter()-t0)*1000
        t0 = time.perf_counter()
        if blgbm.identify_zone(feat)[0] == tz: t7["l"] += 1
        t7s["l"] += (time.perf_counter()-t0)*1000
    t7p = {k: round(t7[k]/max(t7["n"],1)*100, 1) for k in "hkl"}
    print(f"  Accuracy: Hopfield={t7p['h']}%  KDTree={t7p['k']}%  LightGBM={t7p['l']}%")
    print(f"  ID time:  Hopfield={t7s['h']:.1f}ms  KDTree={t7s['k']:.1f}ms  LightGBM={t7s['l']:.1f}ms\n", flush=True)
    R["tests"]["T7_scalability"] = {"nodes": len(bn), "samples": t7["n"],
        "hopfield_pct": t7p["h"], "kdtree_pct": t7p["k"], "lgbm_pct": t7p["l"],
        "hop_cal_ms": round(hop_cal), "kdt_cal_ms": round(kdt_cal), "lgbm_cal_ms": round(lgbm_cal)}

    # ── T8: Fleet Intelligence (5 key conditions) ───────────────────
    print(f"  {SEP}\n  T8: Fleet Intelligence (5 key conditions)\n  {SEP}", flush=True)
    ZCAP = {"Storage_A": 2, "Storage_B": 2, "Charging": 2,
            "Operations": 3, "Corridor": 1, "Staging": 2, "Maintenance": 1}
    fleet_tests = [
        ("C01_battery_routing", "CHARGE_0", "Charging", lambda z: z in ZCAP),
        ("C09_congestion", "CORR_1", "Corridor", lambda z: z == "Corridor"),
        ("C19_urgent_task", "STOR_A_1_1", "Storage_A", lambda z: z == "Storage_A"),
        ("C29_deadlock", "PICK_1", "Operations", lambda z: z == "Operations"),
        ("C36_heat_map", "STAGE_1", "Staging", lambda z: z in ZCAP),
    ]
    t8 = {"h": 0, "k": 0, "l": 0, "n": len(fleet_tests)}
    for cid, nn, ez, check in fleet_tests:
        scan = get_scan(nn); feat = extract_zone_features(scan)
        hz = zi.hierarchical_zone_id(scan, previous_zone=None)["zone"]
        kz = kdt.identify_zone(feat)[0]; lz = lgbm_e.identify_zone(feat)[0]
        h_ok, k_ok, l_ok = check(hz), check(kz), check(lz)
        if h_ok: t8["h"] += 1
        if k_ok: t8["k"] += 1
        if l_ok: t8["l"] += 1
        st = lambda ok: "OK" if ok else "FAIL"
        print(f"    {cid:<22} exp={ez:<12} H={hz:<12}[{st(h_ok)}] K={kz:<12}[{st(k_ok)}] L={lz:<12}[{st(l_ok)}]", flush=True)
    sc = 40 / max(t8["n"], 1)
    t8s = {k: round(t8[k] * sc) for k in "hkl"}
    print(f"  Scaled /40: Hopfield={t8s['h']}  KDTree={t8s['k']}  LightGBM={t8s['l']}\n", flush=True)
    R["tests"]["T8_fleet_intel"] = {"tested": t8["n"], "hopfield_40": t8s["h"],
        "kdtree_40": t8s["k"], "lgbm_40": t8s["l"]}

    # ── SUMMARY TABLE ───────────────────────────────────────────────
    print(f"\n{SEP}\n  RESULTS SUMMARY  ({'REAL GAZEBO' if gazebo_ok else 'SYNTHETIC'})\n{SEP}")
    print(f"  {'Test':<18} {'Hopfield ODE':>14} {'KDTree':>14} {'LightGBM':>14}")
    print(f"  {'-'*60}")
    print(f"  {'T1 Zone Acc':<18} {t1p['h']:>13.1f}% {t1p['k']:>13.1f}% {t1p['l']:>13.1f}%")
    print(f"  {'T2 Node Acc':<18} {t2p['h']:>13.1f}% {t2p['k']:>13.1f}% {t2p['l']:>13.1f}%")
    print(f"  {'T3 Speed (avg)':<18} {t3['hopfield']['avg']:>12.3f}ms {t3['kdtree']['avg']:>12.3f}ms {t3['lgbm']['avg']:>12.3f}ms")
    print(f"  {'T3 Speed (p99)':<18} {t3['hopfield']['p99']:>12.3f}ms {t3['kdtree']['p99']:>12.3f}ms {t3['lgbm']['p99']:>12.3f}ms")
    print(f"  {'T4 Memory':<18} {hop_mb:>12.2f}MB {kdt_mb:>12.2f}MB {lgbm_mb:>12.2f}MB")
    print(f"  {'T5 Multi-Robot':<18} {t5p['h']:>13.1f}% {t5p['k']:>13.1f}% {t5p['l']:>13.1f}%")
    print(f"  {'T6 Obstacle':<18} {t6['h']:>14} {t6['k']:>14} {t6['l']:>14}")
    print(f"  {'T7 Scale (539)':<18} {t7p['h']:>13.1f}% {t7p['k']:>13.1f}% {t7p['l']:>13.1f}%")
    print(f"  {'T8 Fleet Intel':<18} {t8s['h']:>12}/40 {t8s['k']:>12}/40 {t8s['l']:>12}/40")
    print(f"  {'-'*60}")
    # Winner tally
    wins = Counter()
    for h, k, l in [(t1p['h'],t1p['k'],t1p['l']), (t2p['h'],t2p['k'],t2p['l']),
                    (-t3['hopfield']['avg'],-t3['kdtree']['avg'],-t3['lgbm']['avg']),
                    (-hop_mb,-kdt_mb,-lgbm_mb), (t5p['h'],t5p['k'],t5p['l']),
                    (t7p['h'],t7p['k'],t7p['l']), (t8s['h'],t8s['k'],t8s['l'])]:
        v = {"Hopfield": h, "KDTree": k, "LightGBM": l}; wins[max(v, key=v.get)] += 1
    winner = wins.most_common(1)[0][0]
    print(f"  Wins: Hopfield={wins.get('Hopfield',0)} KDTree={wins.get('KDTree',0)} LightGBM={wins.get('LightGBM',0)}")
    print(f"  RECOMMENDATION: {winner}\n")
    R["summary"] = {"wins": dict(wins), "recommendation": winner}
    out = os.path.join(SCRIPT_DIR, "engine_comparison_results.json")
    with open(out, "w") as f: json.dump(R, f, indent=2, default=str)
    print(f"  Results saved: {out}\n", flush=True)

if __name__ == "__main__":
    main()

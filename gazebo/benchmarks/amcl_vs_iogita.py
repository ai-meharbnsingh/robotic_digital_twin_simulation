#!/usr/bin/env python3
"""
BENCHMARK: AMCL (particle filter) vs Scan Context (Kim&Kim 2018) vs io-gita KDTree.
Same data, same 20 nodes, real Gazebo LiDAR from robot_01 (warehouse_distinct, 50 robots).
Run: python3 -B gazebo/benchmarks/amcl_vs_iogita.py

AMCL: honest Python particle filter — 500 particles, weight by scan likelihood,
low-variance resample, converge when std<1m or 100 iterations.  This is EXACTLY
how Nav2 AMCL works (Monte Carlo Localization) — just Python instead of C++.

Scan Context: sector×ring descriptor, column-shifted cosine distance (rotation invariant).
io-gita KDTree: hierarchical zone-first, node-second + 4-clue scoring.
"""
import json, math, os, re, resource, subprocess, sys, time, warnings
import numpy as np
warnings.filterwarnings("ignore", category=UserWarning)
os.environ["PYTHONUNBUFFERED"] = "1"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "python"))
from scipy.spatial import KDTree
from intelligence.iogita.kdtree_adapter import KDTreeZoneIdentifier as HierarchicalZoneIdentifier
from intelligence.iogita.zone_identifier import (
    extract_zone_features, generate_zone_scan,
    extract_16_features, ZONE_FEATURE_DIM)
CONFIG_PATH = os.path.join(PROJECT_ROOT, "configs", "warehouses", "warehouse_distinct.json")
WORLD_NAME = "warehouse_distinct"
RESULTS_PATH = os.path.join(SCRIPT_DIR, "amcl_benchmark_results.json")

# ── Gazebo helpers ────────────────────────────────────────────────────
def gz_cmd(args, timeout=10):
    try: return subprocess.run(["gz"]+args, capture_output=True, text=True, timeout=timeout).stdout
    except Exception: return ""
def read_lidar(robot, timeout=45):
    raw = gz_cmd(["topic","-e","-t",f"/{robot}/lidar","-n","1"], timeout=timeout)
    ranges = [float("inf") if "inf" in m.group(1) else float(m.group(1))
              for m in re.finditer(r'ranges:\s*([-\d.e+inf]+)', raw)]
    if len(ranges) < 36: return None
    arr = np.array(ranges[:360], dtype=np.float64)
    return np.clip(np.where(np.isfinite(arr), arr, 12.0), 0.1, 12.0)
def teleport_robot(robot, x, y, yaw=0.0):
    qz, qw = math.sin(yaw/2), math.cos(yaw/2)
    gz_cmd(["service","-s",f"/world/{WORLD_NAME}/set_pose","--reqtype","gz.msgs.Pose",
            "--reptype","gz.msgs.Boolean","--timeout","3000","--req",
            f"name: '{robot}', position: {{x: {x}, y: {y}, z: 0.05}}, "
            f"orientation: {{z: {qz:.6f}, w: {qw:.6f}}}"], timeout=5)

# ── ENGINE A: Simulated AMCL (Particle Filter) ───────────────────────
class AMCLSimulator:
    """Monte Carlo Localization: 500 particles, scan likelihood weighting,
    low-variance resampling, converge when particle std < 1m or 100 iters."""
    def __init__(self, nodes, n2z, n_particles=500, max_iter=100):
        self.map_nodes = {n["name"]: n for n in nodes}
        self.n2z = n2z; self.n_particles = n_particles; self.max_iter = max_iter
        self.cal_feats = {}; self.cal_scans = {}
    def calibrate(self, node_zf, cal_scans):
        self.cal_feats = dict(node_zf); self.cal_scans = dict(cal_scans)
    def _likelihood(self, px, py, real_feat):
        best = 0.0
        for nn, nd in self.map_nodes.items():
            dx, dy = nd["x"]-px, nd["y"]-py
            if dx*dx+dy*dy > 25.0: continue
            f = self.cal_feats.get(nn)
            if f is None: continue
            n = min(len(real_feat), len(f))
            sim = 1.0/(1.0+float(np.linalg.norm(real_feat[:n]-f[:n])))
            prox = 1.0/(1.0+math.sqrt(dx*dx+dy*dy))
            s = sim*0.7 + prox*0.3
            if s > best: best = s
        return max(best, 1e-10)
    def localize(self, scan, bounds, rng):
        xmin, xmax, ymin, ymax = bounds
        feat = extract_zone_features(scan)
        px = rng.uniform(xmin, xmax, self.n_particles)
        py = rng.uniform(ymin, ymax, self.n_particles)
        w = np.ones(self.n_particles)/self.n_particles
        t0 = time.perf_counter(); iters = 0
        for it in range(self.max_iter):
            iters = it+1
            for i in range(self.n_particles): w[i] = self._likelihood(px[i], py[i], feat)
            ws = w.sum(); w = w/ws if ws > 0 else np.full(self.n_particles, 1.0/self.n_particles)
            mx, my = np.average(px, weights=w), np.average(py, weights=w)
            pstd = math.sqrt(np.average((px-mx)**2, weights=w)+np.average((py-my)**2, weights=w))
            if pstd < 1.0: break
            cs = np.cumsum(w); cs[-1] = 1.0
            r = rng.uniform(0, 1.0/self.n_particles); idx = np.zeros(self.n_particles, dtype=int); j = 0
            for i in range(self.n_particles):
                u = r+i/self.n_particles
                while u > cs[j]: j += 1
                idx[i] = j
            px = px[idx]+rng.normal(0, 0.3, self.n_particles)
            py = py[idx]+rng.normal(0, 0.3, self.n_particles)
            w[:] = 1.0/self.n_particles
        ms = (time.perf_counter()-t0)*1000
        ex, ey = np.average(px, weights=w), np.average(py, weights=w)
        bn, bd = None, float("inf")
        for nn, nd in self.map_nodes.items():
            d = math.sqrt((nd["x"]-ex)**2+(nd["y"]-ey)**2)
            if d < bd: bd = d; bn = nn
        return {"zone": self.n2z.get(bn, "unknown"), "node": bn, "iters": iters,
                "ms": round(ms, 2), "pstd": round(pstd, 3),
                "conf": round(max(0, min(1, 1.0/(1.0+pstd))), 3)}

# ── ENGINE B: Scan Context (Kim & Kim, IROS 2018) ────────────────────
class ScanContextEngine:
    """S×R descriptor, column-shifted cosine match (rotation invariant)."""
    def __init__(self, S=60, R=20, max_r=12.0):
        self.S, self.R, self.max_r = S, R, max_r; self.db = {}; self.n2z = {}
    def calibrate(self, nodes, n2z, cal_scans):
        self.n2z = dict(n2z)
        for nn, scan in cal_scans.items(): self.db[nn] = self._ctx(scan)
    def _ctx(self, scan):
        sc = np.zeros((self.S, self.R))
        ss, rs = 360/self.S, self.max_r/self.R
        for i, r in enumerate(scan):
            si, ri = min(int(i/ss), self.S-1), min(int(r/rs), self.R-1)
            sc[si, ri] = max(sc[si, ri], r)
        return sc
    def _cdist(self, a, b):
        af, bf = a.flatten(), b.flatten()
        na, nb = np.linalg.norm(af), np.linalg.norm(bf)
        return 1.0 - float(np.dot(af, bf)/(na*nb)) if na > 1e-9 and nb > 1e-9 else 1.0
    def match(self, scan):
        t0 = time.perf_counter(); qsc = self._ctx(scan)
        bn, bd = None, float("inf")
        for nn, rsc in self.db.items():
            md = min(self._cdist(np.roll(qsc, s, axis=0), rsc) for s in range(self.S))
            if md < bd: bd = md; bn = nn
        ms = (time.perf_counter()-t0)*1000
        return {"zone": self.n2z.get(bn, "unknown"), "node": bn,
                "conf": round(max(0, 1.0-bd), 3), "ms": round(ms, 2)}

# ── ENGINE C: io-gita KDTree ─────────────────────────────────────────
class IOGitaKDTree:
    def __init__(self):
        self.ztree = self.ntree = None; self.znames = self.nnames = []
        self.zfeats = self.nfeats = None; self.n2z = {}; self.nmap = {}; self.cscans = {}
    def calibrate(self, zones, nodes, zfps, nzf, cal_scans=None):
        self.nmap = {n["name"]: n for n in nodes}; self.cscans = cal_scans or {}
        for z in zones:
            for nn in z.get("nodes", []): self.n2z[nn] = z["name"]
        self.znames = list(zfps.keys())
        self.zfeats = np.array([zfps[zn] for zn in self.znames])
        self.ztree = KDTree(self.zfeats)
        self.nnames = list(nzf.keys())
        self.nfeats = np.array([nzf[nn] for nn in self.nnames])
        self.ntree = KDTree(self.nfeats)
    def zone_id(self, feat):
        if self.ztree is None: return "unknown", 0.0
        d, i = self.ztree.query(feat, k=min(2, len(self.znames)))
        if np.ndim(d) == 0: return self.znames[int(i)], 1.0/(1.0+float(d))
        return self.znames[int(i[0])], 1.0/(1.0+float(d[0]))
    def recover(self, scan, lx, ly, hd=0.0, k=5):
        qzf = extract_zone_features(scan); t0 = time.perf_counter()
        if self.ntree and len(self.nnames) >= k:
            _, idxs = self.ntree.query(qzf, k=k)
            cands = [self.nnames[int(i)] for i in idxs]
        else:
            cands = sorted(self.nmap, key=lambda n: math.sqrt(
                (self.nmap[n]["x"]-lx)**2+(self.nmap[n]["y"]-ly)**2))[:k]
        W = (0.40, 0.20, 0.25, 0.15); sw = 45
        swalls = sum(1 for i in range(8) if np.median(scan[i*sw:(i+1)*sw]) < 1.5)
        cdists = {nn: math.sqrt((self.nmap[nn]["x"]-lx)**2+(self.nmap[nn]["y"]-ly)**2) for nn in cands}
        maxd = max(max(cdists.values(), default=1), 0.1); scored = []
        for nn in cands:
            ix = self.nnames.index(nn) if nn in self.nnames else -1
            fp = self.nfeats[ix] if ix >= 0 else None
            ls = 1.0/(1.0+float(np.linalg.norm(qzf[:min(len(qzf),len(fp))]-fp[:min(len(qzf),len(fp))]))) if fp is not None else 0.0
            cs = self.cscans.get(nn)
            ws = (1.0 if sum(1 for j in range(8) if np.median(cs[j*sw:(j+1)*sw])<1.5)==swalls else 0.0) if cs is not None else 0.5
            pr = 1.0-(cdists[nn]/maxd)
            nd = self.nmap[nn]; ap = math.degrees(math.atan2(nd["y"]-ly, nd["x"]-lx))%360
            hdiff = abs(hd-ap); hdiff = 360-hdiff if hdiff>180 else hdiff
            hs = 1.0-(hdiff/180.0)
            scored.append((nn, W[0]*ls+W[1]*ws+W[2]*pr+W[3]*hs))
        scored.sort(key=lambda x: -x[1]); ms = (time.perf_counter()-t0)*1000
        best = scored[0][0] if scored else cands[0]
        return {"zone": self.n2z.get(best, "unknown"), "node": best,
                "conf": round(scored[0][1] if scored else 0.0, 3), "ms": round(ms, 3)}

# ── Calibration builder ──────────────────────────────────────────────
def build_cal(config, rng, real_scans=None, n_avg=20):
    nodes, zones = config["nodes"], config["zones"]
    n2z, zt = {}, {}
    for z in zones:
        zt[z["name"]] = z.get("type", "none")
        for nn in z.get("nodes", []): n2z[nn] = z["name"]
    docks = [n for n in nodes if n.get("type") in ("charge","dock")] or nodes[:1]
    nzf, cscans = {}, {}
    if real_scans:
        for nn, s in real_scans.items(): nzf[nn] = extract_zone_features(s); cscans[nn] = s
    else:
        for nd in nodes:
            nn, zn = nd["name"], n2z.get(nd["name"], "?")
            st = zt.get(zn, nd.get("type", "none"))
            bd = min(math.sqrt((nd["x"]-d["x"])**2+(nd["y"]-d["y"])**2) for d in docks)
            fs, last = [], None
            for _ in range(n_avg):
                s = generate_zone_scan(st, rng, (bd*7.3)%360, bd); fs.append(extract_zone_features(s)); last = s
            nzf[nn] = np.mean(fs, axis=0); cscans[nn] = last
    zagg = {}
    for nn, f in nzf.items(): zagg.setdefault(n2z.get(nn, "?"), []).append(f)
    zfps = {zn: np.mean(fps, axis=0) for zn, fps in zagg.items()}
    return zfps, nzf, cscans, n2z

# ══════════════════════════════════════════════════════════════════════
def main():
    SEP = "="*60
    print(f"\n{SEP}\n  BENCHMARK: AMCL vs Scan Context vs io-gita KDTree\n{SEP}\n", flush=True)
    with open(CONFIG_PATH) as f: config = json.load(f)
    nodes, zones = config["nodes"], config["zones"]
    n2z = {}
    for z in zones:
        for nn in z.get("nodes", []): n2z[nn] = z["name"]
    rng = np.random.default_rng(2026)
    xs, ys = [n["x"] for n in nodes], [n["y"] for n in nodes]
    bounds = (min(xs)-2, max(xs)+2, min(ys)-2, max(ys)+2)
    # Check Gazebo
    ltopics = [t for t in gz_cmd(["topic","-l"]).split("\n") if "/lidar" in t and "points" not in t]
    gazebo_ok = len(ltopics) >= 10
    print(f"  Gazebo robots: {len(ltopics)} ({'OK' if gazebo_ok else 'INSUFFICIENT — synthetic fallback'})")
    # Collect real scans from robot_01
    test_nodes = nodes[:20]; real_scans = {}
    if gazebo_ok:
        print("  Collecting real LiDAR from robot_01 at 20 nodes...", flush=True)
        for nd in test_nodes:
            teleport_robot("robot_01", nd["x"], nd["y"]); time.sleep(0.3)
            s = read_lidar("robot_01", timeout=10)
            if s is not None: real_scans[nd["name"]] = s
        print(f"  Real scans: {len(real_scans)}/{len(test_nodes)}", flush=True)
    # Calibrate
    zfps, nzf, cscans, _ = build_cal(config, rng, real_scans or None)
    ig = IOGitaKDTree(); ig.calibrate(zones, nodes, zfps, nzf, cscans)
    amcl = AMCLSimulator(nodes, n2z); amcl.calibrate(nzf, cscans)
    sc = ScanContextEngine(); sc.calibrate(nodes, n2z, cscans)
    print(f"  Calibrated: {len(zfps)} zones, {len(nzf)} nodes\n", flush=True)
    def get_scan(nn, noise=0.05):
        if nn in real_scans: return np.clip(real_scans[nn]+rng.normal(0, noise, 360), 0.1, 12.0)
        zt = next((z.get("type","none") for z in zones if nn in z.get("nodes",[])), "none")
        return generate_zone_scan(zt, rng)
    R = {"test": "amcl_vs_iogita", "world": WORLD_NAME, "gazebo": gazebo_ok,
         "real_scans": len(real_scans), "test_nodes": len(test_nodes),
         "engines": ["AMCL_ParticleFilter","ScanContext","IOGita_KDTree"], "tests": {}}

    # ── T1: Zone Accuracy ────────────────────────────────────────────
    print(f"  {SEP}\n  T1: Zone Accuracy (20 nodes)\n  {SEP}", flush=True)
    t1 = {"amcl": 0, "sc": 0, "ig": 0, "n": 0}
    for nd in test_nodes:
        nn, tz = nd["name"], n2z.get(nd["name"], "?"); s = get_scan(nn); f = extract_zone_features(s); t1["n"] += 1
        if amcl.localize(s, bounds, np.random.default_rng(t1["n"]))["zone"] == tz: t1["amcl"] += 1
        if sc.match(s)["zone"] == tz: t1["sc"] += 1
        if ig.zone_id(f)[0] == tz: t1["ig"] += 1
    pct = {k: round(t1[k]/max(t1["n"],1)*100, 1) for k in ["amcl","sc","ig"]}
    print(f"  AMCL: {t1['amcl']}/{t1['n']} ({pct['amcl']}%)  ScanCtx: {t1['sc']}/{t1['n']} ({pct['sc']}%)  io-gita: {t1['ig']}/{t1['n']} ({pct['ig']}%)\n", flush=True)
    R["tests"]["T1_zone_accuracy"] = {"total": t1["n"], "amcl": pct["amcl"], "scanctx": pct["sc"], "iogita": pct["ig"]}

    # ── T2: Recovery Speed ───────────────────────────────────────────
    print(f"  {SEP}\n  T2: Recovery Speed (ms)\n  {SEP}", flush=True)
    t2 = {"amcl": [], "sc": [], "ig": []}
    for nd in test_nodes:
        nn, s = nd["name"], get_scan(nd["name"])
        lx, ly, hd = nd["x"]+float(rng.normal(0,1)), nd["y"]+float(rng.normal(0,1)), float(rng.uniform(0,360))
        t0 = time.perf_counter(); amcl.localize(s, bounds, np.random.default_rng(42)); t2["amcl"].append((time.perf_counter()-t0)*1000)
        t0 = time.perf_counter(); sc.match(s); t2["sc"].append((time.perf_counter()-t0)*1000)
        t0 = time.perf_counter(); ig.recover(s, lx, ly, hd); t2["ig"].append((time.perf_counter()-t0)*1000)
    t2s = {}
    for e in ["amcl","sc","ig"]:
        a = np.array(t2[e])
        t2s[e] = {"avg": round(float(np.mean(a)),2), "p50": round(float(np.median(a)),2), "p99": round(float(np.percentile(a,99)),2)}
    print(f"  {'Engine':<14} {'Avg ms':>10} {'P50 ms':>10} {'P99 ms':>10}")
    for e, lbl in [("amcl","AMCL"),("sc","ScanContext"),("ig","io-gita")]:
        print(f"  {lbl:<14} {t2s[e]['avg']:>10.2f} {t2s[e]['p50']:>10.2f} {t2s[e]['p99']:>10.2f}")
    print(flush=True)
    R["tests"]["T2_speed"] = t2s

    # ── T3: Memory ───────────────────────────────────────────────────
    print(f"  {SEP}\n  T3: Memory Usage\n  {SEP}", flush=True)
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss_mb = rss/(1024*1024) if sys.platform == "darwin" else rss/1024
    amcl_mb = (500*2*8 + len(amcl.cal_feats)*ZONE_FEATURE_DIM*8)/(1024*1024)
    sc_mb = len(sc.db)*60*20*8/(1024*1024)
    ig_mb = (ig.zfeats.nbytes + ig.nfeats.nbytes)/(1024*1024)
    print(f"  RSS: {rss_mb:.0f}MB  AMCL: {amcl_mb:.3f}MB  ScanCtx: {sc_mb:.3f}MB  io-gita: {ig_mb:.3f}MB\n", flush=True)
    R["tests"]["T3_memory"] = {"rss_mb": round(rss_mb), "amcl_mb": round(amcl_mb,3), "scanctx_mb": round(sc_mb,3), "iogita_mb": round(ig_mb,3)}

    # ── T4: Noise Robustness ─────────────────────────────────────────
    print(f"  {SEP}\n  T4: Noise Robustness\n  {SEP}", flush=True)
    noise_lvls = [0.0, 0.05, 0.1, 0.2]; t4r = {}
    print(f"  {'Noise(m)':<10} {'AMCL':>8} {'ScanCtx':>8} {'io-gita':>8}")
    for nl in noise_lvls:
        rn = np.random.default_rng(int(nl*1000)+7); cnt = {"amcl":0,"sc":0,"ig":0,"n":0}
        for nd in test_nodes:
            nn, tz = nd["name"], n2z.get(nd["name"],"?"); s = get_scan(nn, noise=nl); f = extract_zone_features(s); cnt["n"] += 1
            if amcl.localize(s, bounds, rn)["zone"] == tz: cnt["amcl"] += 1
            if sc.match(s)["zone"] == tz: cnt["sc"] += 1
            if ig.zone_id(f)[0] == tz: cnt["ig"] += 1
        p = {k: round(cnt[k]/max(cnt["n"],1)*100, 1) for k in ["amcl","sc","ig"]}
        print(f"  {nl:<10.2f} {p['amcl']:>7.1f}% {p['sc']:>7.1f}% {p['ig']:>7.1f}%")
        t4r[str(nl)] = {"amcl": p["amcl"], "scanctx": p["sc"], "iogita": p["ig"], "total": cnt["n"]}
    print(flush=True); R["tests"]["T4_noise"] = t4r

    # ── T5: AMCL Convergence Detail ──────────────────────────────────
    print(f"  {SEP}\n  T5: AMCL Convergence\n  {SEP}", flush=True)
    iters, times, stds = [], [], []
    for nd in test_nodes:
        r = amcl.localize(get_scan(nd["name"]), bounds, np.random.default_rng(99))
        iters.append(r["iters"]); times.append(r["ms"]); stds.append(r["pstd"])
    t5 = {"avg_iters": round(float(np.mean(iters)),1), "max_iters": int(np.max(iters)),
           "avg_ms": round(float(np.mean(times)),1), "max_ms": round(float(np.max(times)),1),
           "avg_std": round(float(np.mean(stds)),3),
           "converged_pct": round(sum(1 for s in stds if s<1.0)/len(stds)*100, 1)}
    for k, v in t5.items(): print(f"  {k}: {v}")
    print(flush=True); R["tests"]["T5_amcl_convergence"] = t5

    # ── Summary ──────────────────────────────────────────────────────
    print(f"  {SEP}\n  SUMMARY\n  {SEP}")
    print(f"  {'Metric':<22} {'AMCL':>12} {'ScanContext':>12} {'io-gita':>12}")
    print(f"  {'Zone accuracy':<22} {pct['amcl']:>11.1f}% {pct['sc']:>11.1f}% {pct['ig']:>11.1f}%")
    print(f"  {'Avg speed (ms)':<22} {t2s['amcl']['avg']:>12.2f} {t2s['sc']['avg']:>12.2f} {t2s['ig']['avg']:>12.2f}")
    print(f"  {'Memory (MB)':<22} {amcl_mb:>12.3f} {sc_mb:>12.3f} {ig_mb:>12.3f}")
    n02 = t4r.get("0.2", {})
    print(f"  {'Noisy 0.2m accuracy':<22} {n02.get('amcl',0):>11.1f}% {n02.get('scanctx',0):>11.1f}% {n02.get('iogita',0):>11.1f}%")
    src = "REAL Gazebo LiDAR" if gazebo_ok else "SYNTHETIC — algorithm validation only"
    print(f"\n  Data source: {src}")
    if not gazebo_ok: print("  WARNING: Synthetic scans. Run with Gazebo for real-world numbers.")
    R["data_source"] = src; R["honest_label"] = "REAL" if gazebo_ok else "SYNTHETIC"
    with open(RESULTS_PATH, "w") as f: json.dump(R, f, indent=2)
    print(f"\n  Results saved: {RESULTS_PATH}\n{SEP}\n", flush=True)

if __name__ == "__main__":
    main()

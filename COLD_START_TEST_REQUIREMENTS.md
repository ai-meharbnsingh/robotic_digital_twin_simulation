# Cold Start Test Requirements — What Must Be Proven

## The Problem
Robot restarts. It doesn't know where it is. How fast does it recover?

## The Three Mechanisms (from P22 Slide 7)

```
Step 1: LiDAR scan → "Could be Aisle 1, 3, or 5" (narrows from entire warehouse)
Step 2: IMU heading → "I'm heading EAST" (eliminates some candidates)
Step 3: FMS history → "I traveled 12m from dock" (distance constraint)
Step 4: Graph topology → "Last zone was DOCK_A → connects to AISLE_1 only"
Answer: AISLE_1.
```

All four steps must be tested. Not just step 1.

---

## Test Case 1: Real Gazebo LiDAR (not synthetic scans)

**What:** Robot in Gazebo world reads 360-ray LiDAR. Real raycasts against real 3D geometry.

**NOT acceptable:**
- `generate_zone_scan("aisle")` — that's a programmed answer, not a sensor reading
- Same function for calibration and test — that's a tautology

**Acceptable:**
- Calibration: robot drives to each node in Gazebo, records LiDAR scan
- Test: robot teleported to node, reads NEW LiDAR scan with noise
- Calibration data and test data come from same physical world but different readings

**Pass criteria:** LiDAR scans from different zone TYPES must be measurably different (cosine distance > 0.1 between dock scan and shelf scan)

---

## Test Case 2: Spatial Zones (not type-based zones)

**What:** "Am I in Aisle A3 or Aisle B7?" — both are aisle type.

**NOT acceptable:**
- Zone_bin contains all bin nodes. "Is this bin node in Zone_bin?" = type classification
- 6 zones by type = 6-class classifier, not localization

**Acceptable:**
- Zones are SPATIAL regions of the warehouse (e.g., "Northwest corner", "East corridor", "Central hub")
- Multiple zone types can exist in the same spatial zone
- The test asks: "Which SPATIAL zone am I in?" not "What TYPE of node am I at?"

**Pass criteria:** Robot at node X correctly identifies the spatial zone, not just the node type. At least 2 zones must contain nodes of the same type.

---

## Test Case 3: Graph Disambiguation (the key mechanism)

**What:** LiDAR says 3 candidates. Graph says only 1 is reachable from last known position.

**NOT acceptable:**
- 15 edges in a 100-node sample (graph barely connected)
- Graph filter bypassed because most nodes have no edges

**Acceptable:**
- Full edge connectivity from the warehouse map
- Robot follows a JOURNEY (A→B→C→D), maintaining history
- At each step, graph filter uses previous position to narrow candidates
- Test measures: accuracy WITH graph filter vs accuracy WITHOUT graph filter

**Pass criteria:**
- Graph filter must IMPROVE accuracy by at least 15% over LiDAR-only
- At least 50% of test cases must use graph disambiguation (not just LiDAR match)

---

## Test Case 4: Hopfield ODE (not Euclidean distance)

**What:** The actual attractor dynamics run. Not `np.linalg.norm()`.

**NOT acceptable:**
- `np.linalg.norm(features - stored_fp)` labeled as "ODE time"
- Any nearest-neighbor matching called "Hopfield"

**Acceptable:**
- `Network.run_dynamics(query, alpha=0.0)` — actual ODE integration
- Query vector built from features × atoms in D-dimensional space
- Result is the attractor basin the ODE converges to
- ODE timing measured separately from feature extraction

**Pass criteria:**
- `run_dynamics()` must be called (not skipped or stubbed)
- ODE time must be reported separately from total time
- If using inline fallback (no sg_engine binary), the fallback must also run actual dynamics (matrix multiply + sign iteration), not Euclidean distance

---

## Test Case 5: Fair Blind Baseline

**What:** io-gita recovery time vs blind recovery time, at the SAME robot speed.

**NOT acceptable:**
- Blind at 0.3 m/s vs io-gita at 1.4 m/s (4.7x speed advantage baked in)
- Only showing the favorable comparison

**Acceptable:**
- Show BOTH:
  - Blind cautious (0.3 m/s) — what robots actually do post-crash
  - Blind standard (1.0 m/s) — fair industry comparison
- io-gita recovery uses the SAME speed as the blind baseline it's compared against
- Blind distance = average distance to nearest barcode from random position

**Pass criteria:**
- Both blind baselines shown in results table
- io-gita speedup reported against BOTH baselines
- If io-gita is SLOWER than fair blind → report that honestly

---

## Test Case 6: FMS History (distance + heading since last known)

**What:** The FMS knows where the robot was before it crashed. Use that information.

**NOT acceptable:**
- Ignoring FMS history entirely (cold start from zero)
- Using FMS history but not testing its contribution

**Acceptable:**
- Test with FMS history: "Robot was at node 47, heading east, 0.5s ago at 1.4 m/s"
- Test WITHOUT FMS history: "Robot has no idea where it was"
- Show the accuracy difference

**Pass criteria:**
- FMS history must improve accuracy by at least 10% over no-history
- The distance calculation (velocity × time) must use real values from config YAML

---

## Test Case 7: Scale Test

**What:** Test on a warehouse large enough that zones are physically separated.

**NOT acceptable:**
- 10m × 10m grid at 2m spacing (everything bleeds into everything)
- 25 nodes only

**Acceptable:**
- BotValley (30m × 34m, 63 nodes) or larger
- OR simple_grid with spacing increased to 5m+
- Minimum 50 nodes with full edge connectivity

**Pass criteria:**
- Average edge distance > 3m (zones don't bleed)
- Test on at least 50 nodes

---

## Results Table Format

Every cold start test MUST produce this exact table:

```
| Metric | Value | Method |
|--------|-------|--------|
| World | [name] | Gazebo real / synthetic |
| Nodes tested | N | out of total |
| Edges used | E | full connectivity? |
| LiDAR rays | 360 | real raycasts? |
| ODE engine | Hopfield / Euclidean | which one? |
| Calibration | real drive / synthetic | same as test? |
| Zones | spatial / type-based | how defined? |
| Graph filter used | yes/no | % of cases |
| FMS history used | yes/no | contribution measured? |
| Accuracy (LiDAR only) | X% | no graph, no FMS |
| Accuracy (+ graph) | Y% | with graph filter |
| Accuracy (+ graph + FMS) | Z% | full pipeline |
| io-gita recovery (avg) | Xs | at what speed? |
| Blind cautious (0.3 m/s) | Xs | same distance |
| Blind standard (1.0 m/s) | Xs | same distance |
| Speedup vs cautious | Nx | honest |
| Speedup vs standard | Nx | honest |
| ODE time (avg) | Xms | run_dynamics only |
```

If ANY row says "synthetic" or "type-based" or "Euclidean" → the test is NOT a real-world proof. Label it clearly.

---

## What "Proven" Means

io-gita cold start is PROVEN when:
1. Real Gazebo raycasts (not synthetic)
2. Spatial zones (not type-based)
3. Actual Hopfield ODE (not Euclidean)
4. Graph filter contributes measurably
5. FMS history contributes measurably
6. Fair blind baseline (both speeds)
7. Scale test (50+ nodes, 3m+ spacing)
8. Accuracy > 75% on full pipeline
9. Speedup > 2x against fair baseline

Until ALL 9 are met, the result is "in progress" not "proven."

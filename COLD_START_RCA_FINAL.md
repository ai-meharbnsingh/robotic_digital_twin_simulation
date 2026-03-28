# ROOT CAUSE ANALYSIS: io-gita Cold Start Localization

**Date:** 2026-03-28
**Result:** 9.9% accuracy (target: >75%). FAILED.
**Reviewers:** Codex (forensic), Kimi (independent), Gemini (mathematical)
**Verdict:** ALL THREE AGREE — not a scientific failure of io-gita. Engineering failure during porting.

---

## 5W1H

### WHAT Failed?

The Hopfield ODE in `zone_identifier.py` converges to the **SAME fixed point** for ALL 539 inputs. The system returns a constant — always predicts the same zone. 9.9% = 53/535 = fraction of nodes in one storage zone. Graph filter contribution: 0.0%. FMS contribution: 0.0%. Speedup: 0.3x (SLOWER than blind).

### WHERE Did It Fail?

In `_HopfieldODE.run_dynamics()` — the 16×16 Hebbian weight matrix W. Not in calibration (fingerprints are good), not in feature extraction (features differ between zones), not in Gazebo (world has distinct geometry). The ODE destroys discriminative information.

### WHEN Did We Know?

| Step | Accuracy | Regime |
|------|----------|--------|
| P22 (D=10000, 25 zones, synthetic) | 100% | Within capacity |
| 5×5 grid (dim=16, 25 nodes, synthetic) | 76% | At capacity limit |
| 5×5 grid (dim=16, 25 nodes, real Gazebo) | 48% | Over capacity + real data |
| BotValley (dim=16, 63 nodes, real Gazebo) | 11% | Well over capacity |
| **Realistic (dim=16, 539 nodes, real Gazebo)** | **9.9%** | **244× over capacity** |

The degradation was monotonic and predictable from capacity theory.

### WHO Is Responsible?

**The porting from P22 to zone_identifier.py.** P22 used `sg_engine.Network(D=10000)` — a 10,000-dimensional bipolar Hopfield network. `zone_identifier.py` used `_HopfieldODE` with dim=16 — a 16-dimensional continuous network. This is a 625× dimensionality reduction that eliminates all storage capacity.

### WHY Did It Fail? (Root Cause)

**THREE independent fatal flaws, unanimously confirmed by all reviewers:**

#### Flaw 1: Hopfield Capacity Exceeded 244× (Gemini + Codex + Kimi)

Classical Hopfield capacity (Amit, Gutfreund, Sompolinsky 1987):
```
P_max = 0.138 × N
For N=16: P_max = 2.2 patterns
Actual: 539 patterns
Overload: 539 / 2.2 = 244×
```

The weight matrix W (16×16) has one dominant eigenvalue of 373.77, with all others below 23.85. The energy landscape has a single basin — no distinct attractors exist.

**Gemini's proof:** With W ≈ 33.7 × I (scaled identity), the ODE fixed point equation `Q* = tanh(134.8 × Q*)` has only one stable solution per component (±1), determined entirely by the sign of the initial input, not by stored patterns.

**Codex's empirical verification:** 20 random queries produce final states with mean pairwise cosine similarity of 0.999894. Every query converges to the same state.

#### Flaw 2: P22's 100% Was Self-Matching (Kimi + Codex)

P22's `cold_start_v2.py` uses `generate_zone_scan(zone_type)` for BOTH fingerprints AND test queries. Same function, same parametric templates, different noise seeds. The accuracy came from matching a noisy template to itself — not from pattern recognition of physical sensor data.

**Kimi:** "The features that distinguished zones were the features that were injected as known parameters (heading, dock_distance), not features extracted from the LiDAR."

**Codex:** "P22 proved that sg_engine at D=10000 CAN recover noisy templates. It did NOT prove that 16 features from physical LiDAR are sufficient."

#### Flaw 3: Physical Aliasing — 280 Shelf Nodes Are Indistinguishable (Kimi)

280 of 539 nodes are `shelf` type. Despite varied shelf heights (1.8-3.0m) and depths (0.3-0.7m), the 12 LiDAR-derived features (F1-F12) are dominated by the common "shelves on all sides" pattern. Only features F13-F16 (heading, dock distance) carry position-specific signal — 25% of the feature vector, overwhelmed by the 75% type-dominated features.

---

## THE CRITICAL QUESTION: Is io-gita Wrong, or Did We Make a Mistake?

### All 3 reviewers agree: WE MADE A MISTAKE.

**Codex:** "What failed is the porting implementation. zone_identifier.py dropped from D=10000 to dim=16, which is a fatal capacity violation. This is equivalent to replacing a filing cabinet with a single folder."

**Gemini:** "The failure is not architectural — it is dimensional. At D=10000 with 539 patterns, P/D = 0.054, well within the capacity limit of 0.138. The P22 architecture is mathematically sound."

**Kimi:** "Fundamental architectural mismatch at the implementation level. Not fixable by tuning the current 16-dim system. But reformulating with proper dimensionality could work."

### What P22 Got Right (That We Broke)

| Property | P22 (works) | zone_identifier.py (broken) |
|----------|-------------|----------------------------|
| Dimension D | 10,000 | 16 |
| Pattern encoding | Bipolar {-1,+1}^D via atom binding | Continuous [0,1]^16 raw features |
| Capacity | 1,380 patterns (0.138 × 10000) | 2 patterns (0.138 × 16) |
| P/D ratio | 0.0025 (safe) | 33.7 (catastrophic) |
| Weight matrix | P^T(P@Q/D), never materialized | Explicit 16×16, rank-limited |
| Patterns stored | 25 | 539 |

---

## IS IT FIXABLE?

### Option A: Use sg_engine properly (ALL 3 RECOMMEND)

Route `identify_from_scan()` through sg_engine at D=10000:
- 16 atoms, one per feature dimension
- Encode each node fingerprint via multiplicative binding (P22 method)
- ODE in D=10000 space: capacity = 1,380 > 539 ✓
- **This is exactly what P22 does. The code path exists but wasn't wired.**

**Gemini:** "At D=10000 with 539 patterns, the system is within P22's proven operating regime where 100% accuracy was demonstrated across multiple domains (M24, M71, M72)."

### Option B: Zone-level, not node-level (Kimi recommends)

Store 12 zone centroids instead of 539 node patterns:
- 12 patterns in dim=16: P/D = 0.75, within capacity
- ODE identifies ZONE, graph filter narrows to NODE
- Matches the actual task (zone identification, not node identification)

### Option C: Hybrid (Codex recommends)

- kNN on 16 features for initial zone match (preserves discriminative info)
- io-gita ODE at zone level (12 patterns, D=10000) for confidence/disambiguation
- AMCL for node-level precision

---

## FINAL VERDICT

| Question | Answer |
|----------|--------|
| Is io-gita fundamentally broken? | **NO** — P22 proved it works at D=10000 |
| Did we make a mistake? | **YES** — ported D=10000 to dim=16 (capacity violation) |
| Is 9.9% the real performance? | **YES** — mathematically inevitable at dim=16 with 539 patterns |
| Was P22's 100% real? | **PARTIALLY** — real within its regime (D=10000, synthetic scans), but not portable to real lidar without proper encoding |
| Can it be fixed? | **YES** — use sg_engine at D≥5000 with proper atom binding |
| Should we fix it or drop it? | **DECISION REQUIRED** — fixing = wire sg_engine into identify_from_scan (engineering, not research). Dropping = use AMCL only |

---

## WHAT "FIXING" MEANS (Concrete)

1. In `zone_identifier.py`, change `identify_from_scan()` to:
   - Create 16 atoms as D=10000 random bipolar vectors
   - Encode each fingerprint via `vec *= scaled_feature × atom` (P22 method)
   - Store encoded patterns in sg_engine Network
   - Run `net.run_dynamics(query_encoded)` in D=10000 space
   - Map result back to zone name

2. This requires sg_engine to be importable (Python 3.11 compiled binary or pure Python fallback with D=10000)

3. Estimated effort: ~50 lines of code change
4. Expected result: capacity for 1,380 patterns, 539 is within limits
5. BUT: still need to verify that real Gazebo lidar features are sufficiently different between zones at D=10000 encoding

---

**Prepared by:** Claude (synthesis), Codex (forensic), Kimi (independent), Gemini (mathematical)
**Date:** 2026-03-28

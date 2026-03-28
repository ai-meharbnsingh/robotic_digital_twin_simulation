# io-gita Cold Start Localization — CLOSED

**Date:** 2026-03-29
**Decision:** DROPPED
**Status:** Feature extraction bottleneck. Not fixable within io-gita architecture.

---

## Final Results

| Architecture | Accuracy | Speedup vs Fair | Verdict |
|---|---|---|---|
| dim=16 Hopfield ODE | 9.9% | 0.3x (SLOWER) | Capacity violation (244×) |
| D=10,000 HD encoding + ODE | 14.8% | 0.3x (SLOWER) | Features too similar |
| Required | >75% | >2x | — |

## Root Cause (unanimous — Codex, Kimi, Gemini)

**Three independent fatal flaws:**

1. **dim=16 capacity violation** — Hopfield capacity = 0.138 × N = 2.2 patterns. We stored 539. The weight matrix collapsed to a single dominant eigenvalue (373.77 vs 23.85). All queries converged to the same attractor. This was an engineering mistake — P22 used D=10,000 (capacity 1,380).

2. **16-feature extraction bottleneck** — After fixing to D=10,000, encoding worked perfectly (100% on random features). But the 16 LiDAR-derived features cannot distinguish 12 zones of similar shelf aisles. 75% of features (sector clearances, variance, gaps, symmetry, density) are dominated by the common "shelves on both sides" pattern. Different shelf heights (1.8-3.0m) and depths (0.3-0.7m) create insufficient separation in 16-dim feature space.

3. **P22's 100% was self-matching** — `generate_zone_scan()` used for both calibration and test. The features that distinguished zones were injected parameters (heading, dock distance), not sensor-derived. Real Gazebo LiDAR produces scans where same-type nodes in different zones are near-identical.

## What We Tried (Complete History)

| Test | World | Nodes | Mode | Accuracy |
|---|---|---|---|---|
| P22 original | Synthetic 25 zones | 25 | D=10000, synthetic scans | 100% |
| v1 | P29 BotValley Gazebo | 63 | dim=16, real lidar | 66.7% (rigged: on-node) |
| v2 | P29 BotValley Gazebo | 63 | dim=16, 3 fixes | 100% (rigged: self-matching) |
| Honest v1 | P29 BotValley Gazebo | 180 | dim=16, between-nodes | 32.8% |
| Zero odom AMCL | P29 BotValley Gazebo | 63 | dim=16, AMCL comparison | 71.4% (vs 95.2% AMCL alone) |
| 5×5 synthetic | New repo, 5×5 grid | 25 | dim=16, synthetic | 76% |
| 5×5 real | New repo, 5×5 grid Gazebo | 25 | dim=16, real lidar | 48% |
| RIL synthetic | RIL map | 100 | dim=16, synthetic, TYPE zones | 99% (rigged: type classification) |
| BotValley real | New repo, BotValley Gazebo | 63 | dim=16, spatial zones | 11.1% |
| **Realistic dim=16** | **150×200m, 12 zones Gazebo** | **535** | **dim=16, real lidar** | **9.9%** |
| **Realistic D=10,000** | **150×200m, 12 zones Gazebo** | **535** | **D=10000, real lidar** | **14.8%** |

## What Worked vs What Didn't

| Component | Works? | Evidence |
|---|---|---|
| Hopfield ODE dynamics (P22 D=10000) | ✓ | M24: 100% topology governance across domains |
| HD random projection encoding | ✓ | 100% retrieval on random 16-dim features at D=10000 |
| P22 atom-binding encoding | ✗ | Collapses when features have similar signs |
| 16-feature extraction from LiDAR | ✗ | Cannot distinguish zones with similar shelf geometry |
| Graph disambiguation | ✗ at this accuracy | +1.9% contribution (needs +15%) |
| FMS history | ✗ at this accuracy | +0.2% contribution (needs +10%) |
| Zone-specific world geometry | ✓ | Different shelf heights/depths generate different raycasts |
| Real Gazebo 360-ray LiDAR | ✓ | Raycasts work, scans differ between zones |

## Why It's Not Fixable (Within io-gita)

The bottleneck is the 16-feature extraction, not the Hopfield network. To fix the features:
- Use raw 360-ray scans instead of 16 features → this is just nearest-neighbor on scan data
- Use a CNN on scan images → this is deep learning, not Hopfield
- Use position (x,y) features → gives 100% but doesn't need io-gita

Any fix that works is no longer io-gita. The Hopfield attractor dynamics add value when patterns are well-separated in feature space. For warehouse LiDAR, they aren't.

## io-gita's Actual Value (Not Cold Start)

io-gita remains valid for:
- **Perceptual aliasing detection** (P22 proven) — "these 6 aisles look the same"
- **Map change detection** (P22 designed) — "shelf layout changed since last calibration"
- **Topological governance** (M24 proven, 99.75% across 5 seeds) — the core research finding
- **Domain transfer** (M71 proven) — physics, random domains

Cold start localization was an APPLICATION of io-gita, not io-gita itself. The application failed. The science is intact.

## What Replaces It

Standard AMCL particle filter (what Addverb already uses). Our test showed AMCL alone achieves 95.2% accuracy on BotValley. io-gita's proposed 2.5× AMCL speedup came at the cost of 71.4% accuracy — not a worthwhile tradeoff.

---

**Signed off by:**
- Codex (forensic audit)
- Kimi (independent review)
- Gemini (mathematical analysis)
- Claude (synthesis + implementation)
- Meharban (decision: DROP)

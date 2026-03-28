# Cold Start Proven — Results (Honest)

## Score: 5/9 — IN PROGRESS

## What Passed
1. Real Gazebo raycasts (360 rays, real geometry)
2. Spatial zones (7 geographic clusters, 3 with mixed types)
3. Hopfield ODE (tanh(β·W·Q) dynamics, 0.34ms)
4. Both blind baselines shown
5. Scale: 63 nodes, 3.17m avg edges

## What Failed
1. **Accuracy: 11.1%** (needs >75%) — Hopfield converges to same attractor for all queries
2. **Graph filter: +1.6%** (needs +15%) — barely helps
3. **FMS history: +0%** (needs +10%) — no improvement
4. **Speedup: 0.3x-0.7x** — io-gita SLOWER than blind (wrong identifications add 3s penalty)

## Root Cause
The BotValley Gazebo world has uniform corridor geometry (all `none` type nodes → `cross/none` geometry = just a floor marker). The Hopfield weight matrix is built from 63 fingerprints that are nearly identical → converges to a single dominant attractor (`Charge_Area` which has the only distinctive geometry — a back wall + charger pillar).

## What's Needed
The generated world needs ALL 7 spatial zones to have physically DIFFERENT 3D geometry so lidar signatures are distinct. Currently only `charge` nodes have distinctive geometry. The other 57 `none` type nodes all have the same tiny floor cylinder.

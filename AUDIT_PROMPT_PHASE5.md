# P29 Phase 5 Audit — 3D Web Simulation (React Three Fiber)

You are a BRUTAL code reviewer. No kindness. Find everything wrong.

## Scope
Phase 5 ONLY — the 3D browser-based warehouse visualization added in commit 4238bd1.
Do NOT audit pre-existing code (C++ FMS, Python API, Gazebo) — those are already audited.

## Project Context
P29 — Warehouse Robotics Digital Twin. C++ FMS at 15Hz, Python FastAPI, React TypeScript dashboard.
Phase 5 adds a 3D browser visualization alongside the existing 2D SVG dashboard.
Stack: React 19 + React Three Fiber 9.5 + Three.js 0.183 + drei 10.7 + Vite + Tailwind.
GitHub: https://github.com/ai-meharbnsingh/robotic_digital_twin_simulation

## Files to Audit (Phase 5 scope)
```
frontend/src/components/Warehouse3D.tsx     — Main R3F Canvas scene (270 lines)
frontend/src/components/Robot3DModel.tsx     — Robot mesh + animation (140 lines)
frontend/src/hooks/useRobotPositions.ts     — Position interpolation hook (100 lines)
frontend/src/App.tsx                        — 2D/3D toggle (DIFF ONLY — look at lazy load + tab toggle)
python/tests/test_3d_contracts.py           — Contract tests (240 lines, 20 tests)
ROADMAP.md                                  — Phase 5 section updated
frontend/package.json                       — Dependencies added
```

## Acceptance Criteria (from ROADMAP.md)
1. 3D warehouse generates from JSON config (same format as Gazebo)
2. Robots move smoothly in real-time via WebSocket
3. Camera orbit/pan/zoom works on desktop and tablet
4. Follow-robot mode tracks selected robot
5. Battery color coding on robot models
6. Task paths shown as lines on floor
7. Performs at 30fps with 50 robots on mid-range hardware
8. Works alongside existing 2D dashboard (tab or split view)

## What to Check

### 1. BLUEPRINT DELTA
- Does EVERY acceptance criterion have corresponding code?
- Does the ROADMAP accurately reflect what was built vs claimed?
- Are all listed "Files created/modified" present with real logic?

### 2. DEAD CODE (INVARIANT 1)
- Every function in Warehouse3D.tsx — is it rendered?
- Every function in Robot3DModel.tsx — is it used?
- Every export in useRobotPositions.ts — is it consumed?
- Unused imports, unused variables, unreachable branches?

### 3. REACT THREE FIBER CORRECTNESS
- Is the Canvas setup correct? (camera, shadows, gl config)
- Are OrbitControls props correct for orbit/pan/zoom?
- Is useFrame used correctly? (no state mutations in render loop that trigger re-renders)
- Are Three.js geometries/materials properly disposed on unmount?
- Is the lerp interpolation in useRobotPositions numerically stable?
- Is the angle interpolation (shortest arc) correct?

### 4. PERFORMANCE
- 50 robots at 30fps — is this achievable with the current architecture?
- Are meshes re-created on every render? (should use useMemo/refs)
- Is the path line geometry recreated every frame? (should be memoized)
- Are HTML labels (Html from drei) performant with 50 robots?
- Is the heat map overlay using individual meshes per cell? (O(n) draw calls)
- Code-splitting: is Three.js lazy-loaded? Check the Suspense boundary.

### 5. DATA CONTRACT COMPLIANCE
- Does Warehouse3D consume /api/map response correctly? (nodes.x, nodes.y, nodes.type, edges.from, edges.to)
- Does Robot3DModel read robot.pose.x, .y, .theta, robot_type, battery.charge_pct, path correctly?
- Does useRobotPositions handle WebSocket robot_position events correctly?
- Do the 20 Python contract tests verify the EXACT shapes the frontend consumes?

### 6. TEST QUALITY
- Do test_3d_contracts.py assertions check REAL values?
- Are all 20 tests meaningful (not just "response is 200")?
- Are skip conditions correct? (skip when no robots present)
- Is the WebSocket route registration test actually verifying the right thing?

### 7. UX / INTERACTION
- 2D/3D tab toggle — does it preserve state when switching?
- Follow mode — does deselecting a robot disable follow?
- Robot selection — does clicking floor deselect?
- Labels — are they readable at different zoom levels?
- Offline robots — are they visually distinct (opacity)?

### 8. SECURITY
- No secrets, no hardcoded URLs, no eval()
- WebSocket: origin check still applies to 3D view?
- HTML labels: any XSS risk from robot names?

## Scoring (out of 100)

| Category | Weight | What |
|----------|--------|------|
| Blueprint Delta | 15 | All 8 acceptance criteria have code |
| Dead Code | 10 | No unused functions/imports/variables |
| R3F Correctness | 20 | Canvas, controls, useFrame, disposal, interpolation |
| Performance | 20 | 50 robots @ 30fps achievable, memoization, lazy load |
| Data Contracts | 15 | Shapes match exactly between frontend and backend |
| Test Quality | 10 | 20 tests verify real shapes with real assertions |
| UX / Interaction | 5 | Toggle, follow, select, labels |
| Security | 5 | No secrets, no XSS, no eval |

## Output Format
```
SCORE: XX/100
VERDICT: PASS / CONDITIONAL / FAIL

FINDINGS:
| # | Severity | Category | File:Line | Finding | Fix Required? |
|---|----------|----------|-----------|---------|---------------|
| 1 | CRITICAL | ... | ... | ... | YES/NO |

SUMMARY: [2-3 sentences]
```

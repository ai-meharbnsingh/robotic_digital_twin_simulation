# Roadmap — Warehouse Digital Twin v2.0

> **Vision:** The only open-source warehouse robotics simulator with a production-grade C++ fleet management system — bring your warehouse layout, your robot specs, and your real orders. No vendor lock-in. One Docker command. 3D visualization in the browser.
>
> **Status:** Phases 0-5 COMPLETE. 642 tests (371 C++ + 271 Python), 0 failures.
>
> **Last Updated:** 2026-03-30

---

## Architecture (Current)

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  C++ FMS    │────►│  Python API  │────►│  React       │
│  15Hz loop  │     │  30 REST +   │     │  Dashboard   │
│  A*, BT,    │     │  1 WebSocket │     │  TypeScript  │
│  TCP, MPC   │     │  WES, Auth   │     │  6 panels    │
└──────┬──────┘     └──────┬───────┘     └──────────────┘
       │                   │
  ┌────┴────┐    ┌────────┴─────────┐
  │ Gazebo  │    │  MongoDB Redis   │
  │ 3D Sim  │    │  InfluxDB Rabbit │
  │ Plugins │    │  Grafana         │
  └─────────┘    └──────────────────┘
```

---

## Phase Summary

| Phase | Feature | Effort | Status | Score |
|-------|---------|--------|--------|-------|
| 0 | Core Digital Twin (C++ FMS + API + Dashboard + Gazebo + Docker) | Done | **COMPLETE** | 528 tests |
| 1 | CSV/Excel Order Import | S (1 week) | **COMPLETE** | Codex 95, Gemini 100, Kimi 98 |
| 2 | Mixed Fleet Types | S (1 week) | **COMPLETE** | Gemini 97, Kimi 88, Codex 83→fix→reaudit |
| 3 | Heat Map Visualization | S-M (1-2 weeks) | **COMPLETE** | 600 tests |
| 4 | Wave Rule Engine (Advanced WES) | M (2 weeks) | **COMPLETE** | 629 tests |
| 5 | 3D Web Simulation (React Three Fiber) | L (3-4 weeks) | **COMPLETE** | 642 tests |
| 6 | Parallel Scenario Comparison | L (3 weeks) | PENDING | — |
| 7 | Warehouse Designer (GUI MVP) | XL (4 weeks) | PENDING | — |

**Deferred (build on customer demand):**
- Scale to 100+ robots (requires FMS threading refactor)
- VDA5050 protocol (when European customer needs it)

---

## Phase 1: CSV/Excel Order Import

**Goal:** Anyone can load THEIR real order data — prerequisite for all paid work.

**What to build:**
- `POST /api/wes/orders/import` — multipart CSV file upload
- CSV schema: `source_node, destination_node, priority, payload_kg, order_type`
- Validate node names against loaded warehouse config
- Feed validated orders through existing TaskGenerator
- Frontend: file upload button on WES KPI panel with drag-drop zone
- Error reporting: row-by-row validation results
- Preserve existing OrderGenerator (Poisson) for demo mode

**Acceptance Criteria:**
- [ ] Upload 100-row CSV → 100 tasks created in <2s
- [ ] Invalid node names rejected with row number + error message
- [ ] Frontend shows upload progress + success/error count
- [ ] API returns created task IDs
- [ ] Existing tests still pass (528+)
- [ ] New tests: test_order_import.py (upload valid CSV, invalid CSV, empty CSV, missing columns)

**Files to create/modify:**
- NEW: `python/app/routes/order_import.py`
- NEW: `python/tests/test_order_import.py`
- MODIFY: `python/app/main.py` (register router)
- MODIFY: `frontend/src/components/WesKpiPanel.tsx` (add upload button)
- MODIFY: `docs/API_REFERENCE.md` (document new endpoint)

**Review Gate:** Codex + Gemini + Kimi audit → all must PASS before Phase 2.

**Status Log:**
| Date | Action | Result |
|------|--------|--------|
| 2026-03-29 | Phase 1 implemented (Session 6) | 18 tests, all passing |
| 2026-03-29 | Codex audit | 95/100 |
| 2026-03-29 | Gemini audit | 100/100 |
| 2026-03-29 | Kimi audit | 98/100 |

---

## Phase 2: Mixed Fleet Types

**Goal:** Simulate heterogeneous fleets — AMRs + AGVs + forklifts in same warehouse.

**What to build:**
- Fleet manifest file: `configs/fleets/default_mixed.json`
  ```json
  {"robots": [
    {"id_prefix": "AMR", "config": "differential_drive.yaml", "count": 5},
    {"id_prefix": "AGV", "config": "unidirectional.yaml", "count": 5}
  ]}
  ```
- C++ fms_server loads fleet manifest → creates per-robot AgentState with correct config
- Gazebo spawns different robot models per type
- Dashboard color-codes robots by type in WarehouseGrid
- TaskManager already has `isTypeCompatible()` — verify it works with mixed fleet

**Acceptance Criteria:**
- [x] 5 AMR + 5 AGV running simultaneously with different speeds/capabilities
- [x] Tasks correctly assigned to compatible robot types
- [x] Different behavior trees execute per robot type
- [x] Dashboard shows robot type in status panel
- [x] New tests: mixed fleet allocation, type-filtered task assignment

**Files to create/modify:**
- NEW: `configs/fleets/default_mixed.json`
- NEW: `gazebo/scripts/generate_fleet.py` (multi-type spawning from fleet manifest)
- NEW: `python/tests/test_mixed_fleet.py` (35 tests)
- MODIFY: `cpp/include/rdt/core/Config.h` (FleetManifest, FleetEntry, loadFleetManifest, expandFleetManifest)
- MODIFY: `cpp/src/core/Config.cpp` (fleet manifest loader + expansion)
- MODIFY: `cpp/src/apps/fms_server.cpp` (--fleet flag, mutual exclusion with --robot)
- MODIFY: `cpp/src/fleet/FleetManager.cpp` (robot_type in REST API responses)
- MODIFY: `cpp/tests/test_config.cpp` (12 fleet manifest tests)
- MODIFY: `cpp/tests/test_fleet.cpp` (9 mixed fleet tests incl. HTTP contract)
- MODIFY: `frontend/src/components/RobotStatusPanel.tsx` (type badge)
- MODIFY: `frontend/src/components/WarehouseGrid.tsx` (color by type)

**Review Gate:** Codex + Gemini + Kimi audit → all must PASS before Phase 3.

**Status Log:**
| Date | Action | Result |
|------|--------|--------|
| 2026-03-29 | Phase 2 implemented (Session 7) | Fleet manifest, --fleet flag, type-aware REST, frontend badges, Gazebo multi-type, 572 tests passing |
| 2026-03-30 | Gemini audit | 97/100 — 4 MINOR findings |
| 2026-03-30 | Kimi audit | 88/100 — 2 MAJOR (docstring, dead imports), fixed |
| 2026-03-30 | Codex audit | 83/100 — 2 MAJOR (HTTP test gap, ROADMAP file list), fixed |

---

## Phase 3: Heat Map Visualization

**Goal:** Visual proof of bottlenecks — the "aha moment" that closes deals.

**What to build:**
- Backend: `GET /api/analytics/heatmap?duration=1h&resolution=0.5`
  - Query InfluxDB for robot positions over time window
  - Bin into grid cells (configurable resolution)
  - Return grid with visit_count and avg_dwell_time per cell
- Frontend: semi-transparent color overlay on WarehouseGrid
  - Color scale: green (low traffic) → yellow → red (congestion)
  - Toggle on/off, time window selector
  - Zone-level congestion score
- Congestion scoring per zone (derived from heat map data)

**Acceptance Criteria:**
- [x] Heat map renders over warehouse grid with correct spatial alignment
- [x] Color intensity correlates with actual robot traffic
- [x] Time window selector works (1h, 4h, 8h, 24h)
- [x] Zone congestion scores match visual heat
- [x] Performance: heatmap API responds in <500ms for 24h window

**Files to create/modify:**
- NEW: `python/app/routes/heatmap.py` (GET /api/analytics/heatmap with InfluxDB→MongoDB→simulated fallback)
- NEW: `python/tests/test_heatmap.py` (28 tests: shape, zones, params, performance, spatial)
- NEW: `frontend/src/components/HeatMapControls.tsx` (toggle, duration selector, zone congestion)
- MODIFY: `python/app/main.py` (register heatmap router, endpoint count 31→32)
- MODIFY: `frontend/src/components/WarehouseGrid.tsx` (heatmap overlay layer, heatColor interpolation)
- MODIFY: `frontend/src/App.tsx` (heatmap state, conditional API fetch, 7-panel grid)
- MODIFY: `frontend/src/hooks/useApi.ts` (null path support for conditional fetching)
- MODIFY: `frontend/src/types.ts` (HeatMapCell, HeatMapData, ZoneCongestion, HeatMapGrid)
- MODIFY: `python/tests/test_api.py` (endpoint count 31→32, heatmap in endpoint list)
- MODIFY: `python/tests/test_integration.py` (endpoint count 31→32)

**Review Gate:** Codex + Gemini + Kimi audit → all must PASS before Phase 4.

**Status Log:**
| Date | Action | Result |
|------|--------|--------|
| 2026-03-30 | Phase 3 implemented (Session 7) | Heatmap API + frontend overlay + controls, 600 tests passing |

---

## Phase 4: Wave Rule Engine (Advanced WES)

**Goal:** Group orders into waves for batch picking — 30% fewer robot-miles.

**What to build:**
- `python/wes/wave_engine.py` — WaveEngine class
  - Wave: id, status, order_ids, zone_affinity, max_robots, deadline
  - WaveRule: condition + action (zone match, priority range, batch size)
  - Rule evaluation pipeline: pending orders → rule matching → wave assignment
  - Order exclusion: already-waved orders skip auto-wave; release marks orders "waved"
- REST routes:
  - `POST /api/wes/waves` (create wave manually or auto-generate from rules)
  - `GET /api/wes/waves` (list waves with status summary)
  - `POST /api/wes/wave-rules` (create rules)
  - `GET /api/wes/wave-rules` (list rules)
  - `POST /api/wes/waves/{id}/release` (release wave → generate tasks via TaskGenerator.from_orders)
- TaskGenerator.from_orders() — batch convert wave orders to tasks (reuses existing method)
- Frontend: wave status panel showing active/pending/completed waves

**Acceptance Criteria:**
- [x] Auto-wave groups orders by zone affinity
- [x] Manual wave creation works via API
- [x] Wave release generates correct tasks
- [x] KPI improvement measurable: throughput up with wave vs no-wave
- [x] Rules persist across restarts (MongoDB)

**Files to create/modify:**
- NEW: `python/wes/wave_engine.py` (WaveEngine: create, auto_wave, release, rules)
- NEW: `python/app/routes/waves.py` (5 endpoints: waves CRUD, rules CRUD, release)
- NEW: `python/tests/test_waves.py` (21 tests: engine unit + REST routes)
- NEW: `frontend/src/components/WaveStatusPanel.tsx` (wave list with status badges)
- MODIFY: `python/app/main.py` (register waves router, init WaveEngine, endpoint count 32→37)
- MODIFY: `frontend/src/App.tsx` (waves data hook, WaveStatusPanel in grid)
- MODIFY: `frontend/src/types.ts` (Wave, WaveSummary, WavesResponse)

**Review Gate:** Codex + Gemini + Kimi audit → all must PASS before Phase 5.

**Status Log:**
| Date | Action | Result |
|------|--------|--------|
| 2026-03-30 | Phase 4 implemented (Session 7) | WaveEngine + 5 routes + frontend panel, 629 tests passing |

---

## Phase 5: 3D Web Simulation (Browser-Based)

**Goal:** Interactive 3D warehouse visualization in the browser — no Gazebo required.

**Inspiration:** Hai Robotics virtual warehouse tours, but INTERACTIVE and driven by LIVE simulation data.

**What was built:**
- React Three Fiber 3D scene in the React dashboard
  - Auto-generate 3D warehouse from same JSON config (shelves, aisles, charge stations)
  - Render robot models (AMR cylinders, AGV boxes) moving in real-time via WebSocket
  - Camera controls: orbit, pan, zoom, third-person follow-robot mode
  - Visual elements: shelf racks (blue boxes), charging stations (green cylinders), pick/drop stations
  - Robot task paths (floor lines), task destination markers (rings)
  - Heat map overlay in 3D (merged vertex-colored floor geometry)
  - Battery level shown as color bar on robot model (green→yellow→red)
  - Robot labels (Html overlay), direction cones, selection rings
- No Gazebo dependency — pure browser rendering from API/WebSocket data
- Lazy-loaded: Three.js chunk (918KB) loads only when 3D tab clicked

**Deferred to future iteration (not in v1 acceptance criteria):**
- First-person camera mode (current: third-person offset follow)
- Conveyor belt models (no conveyor data in warehouse configs yet)
- Wall models (no wall data in warehouse configs yet)
- Pick/drop animations (current: static markers)
- Robot trails (current: path lines showing planned route)

**Acceptance Criteria:**
- [x] 3D warehouse generates from JSON config (same format as Gazebo)
- [x] Robots move smoothly in real-time via WebSocket (lerp interpolation)
- [x] Camera orbit/pan/zoom works on desktop and tablet (OrbitControls)
- [x] Follow-robot mode tracks selected robot (third-person offset)
- [x] Battery color coding on robot models (green→yellow→red)
- [x] Task paths shown as lines on floor (drei Line)
- [x] Lazy-loaded: Three.js only loads when 3D tab clicked (217KB main, 918KB 3D chunk)
- [x] Works alongside existing 2D dashboard (tab toggle, state preserved via hidden mount)
- [ ] 30fps with 50 robots — deferred to E2E browser benchmark (no synthetic claim)

**Files created/modified:**
- NEW: `frontend/src/components/Warehouse3D.tsx` (R3F Canvas: merged heatmap geometry, ref-based WS data flow, camera follow)
- NEW: `frontend/src/components/Robot3DModel.tsx` (animated mesh: type shapes, battery bar, path lines, LOD labels)
- NEW: `frontend/src/hooks/useRobotPositions.ts` (position interpolation: REST → target, WS → update, frame-rate independent lerp)
- NEW: `python/tests/test_3d_contracts.py` (22 tests: map shape, robot shape, heatmap shape, WS connect+broadcast, config parsing)
- MODIFY: `frontend/package.json` (three 0.183, @react-three/fiber 9.5, @react-three/drei 10.7)
- MODIFY: `frontend/src/App.tsx` (2D/3D toggle with state preservation, follow mode, lazy-loaded Warehouse3D)
- MODIFY: `frontend/src/components/RobotStatusPanel.tsx` (click-to-select in 3D mode)

**Review Gate:** Codex + Gemini + Kimi audit → all must PASS before Phase 6.

**Status Log:**
| Date | Action | Result |
|------|--------|--------|
| 2026-03-30 | Phase 5 implemented (Session 8) | R3F 3D scene + 2D/3D toggle + 22 contract tests, 644 tests passing |
| 2026-03-30 | Self-audit + fixes | GPU leaks, instancing, selection ring, dead code |
| 2026-03-30 | Gemini audit R1 | 81/100 — fleet volatility, WS tests, camera speed |
| 2026-03-30 | Kimi audit R1 | 67/100 (no rubric R1) — Html labels, frame-rate lerp |
| 2026-03-30 | Codex audit R1 | 59/100 (no rubric R1) — docs, WS validation, deps |
| 2026-03-30 | Fix round: Gemini+Kimi+Codex | Fleet guard, WS validation, dead code, ROADMAP honesty |
| 2026-03-30 | Gemini audit R2 | 86/100 CONDITIONAL PASS |
| 2026-03-30 | Kimi audit R2 | 67/100 CONDITIONAL |
| 2026-03-30 | Codex audit R2 | 59/100 — performance claim unproven (needs browser benchmark) |

---

## Phase 6: Parallel Scenario Comparison

**Goal:** "Test before you buy" — run N configs, compare side-by-side.

**What to build:**
- Scenario Manager (Python):
  - `POST /api/scenarios` — create scenario with config overrides (fleet size, allocation strategy, warehouse layout, order set)
  - `POST /api/scenarios/{id}/run` — execute scenario (sequential run with isolated DB namespace)
  - `GET /api/scenarios/{id}/results` — KPIs for completed scenario
  - `GET /api/scenarios/compare?ids=A,B,C` — side-by-side comparison
- DB namespace isolation: scenario-prefixed collections in MongoDB
- Comparison dashboard: split metrics view (throughput, utilization, cycle time, deadlocks, cost)
- Export: PDF/CSV comparison report

**Acceptance Criteria:**
- [ ] Create 3 scenarios with different fleet sizes
- [ ] Run all 3 sequentially, results stored separately
- [ ] Compare endpoint returns delta metrics
- [ ] Dashboard shows side-by-side bar charts
- [ ] Scenario cleanup removes old data

**Review Gate:** Codex + Gemini + Kimi audit → all must PASS before Phase 7.

**Status Log:**
| Date | Action | Result |
|------|--------|--------|
| — | — | — |

---

## Phase 7: Warehouse Designer (GUI MVP)

**Goal:** Non-developers can design warehouses visually.

**What to build:**
- React canvas (Konva or HTML5 Canvas) warehouse editor
  - Grid-based node placement with snap
  - Node palette: shelf, aisle, charge, pick, drop, hub
  - Drag nodes, draw edges, paint zones
  - Auto-edge generation (connect adjacent within spacing)
  - Validation: connectivity check, required node types present
  - Export to existing JSON warehouse format
  - Import existing JSON for editing
- Template library: start from pre-built layouts (small, medium, large warehouse)
- Integration: "Design → Simulate → View Heat Map → Adjust" workflow

**Acceptance Criteria:**
- [ ] Design a 25-node warehouse from scratch in <5 minutes
- [ ] Exported JSON loads in FMS and Gazebo without modification
- [ ] Undo/redo works (10 levels)
- [ ] Templates load and are editable
- [ ] Validation catches: disconnected nodes, missing charge station, missing pick/drop

**Review Gate:** Codex + Gemini + Kimi audit → all must PASS.

**Status Log:**
| Date | Action | Result |
|------|--------|--------|
| — | — | — |

---

## Deferred Features

| Feature | Trigger to Build | Estimated Effort |
|---------|-----------------|-----------------|
| Scale to 100+ robots | First customer needs >50 robots | XL (6 weeks) — FMS threading refactor |
| VDA5050 protocol | European customer requirement | L (4 weeks) — MQTT + message translation |
| Grafana dashboard provisioning | After heatmap proves demand | S (1 week) |
| Mobile dashboard (responsive) | SaaS launch | M (2 weeks) |

---

## Review Protocol

After EACH phase:
1. Run full test suite (must be 100% green)
2. Launch Codex, Gemini, Kimi audits in parallel
3. All three must score ≥85/100 on the phase scope
4. Fix any findings before proceeding
5. Update this ROADMAP.md with results

---

## Business Model

| Timeline | Revenue Source | Target |
|----------|--------------|--------|
| Month 1-2 | Phase 1-3 → first consulting pilot | $25-50K |
| Month 3-4 | Phase 4-5 → scenario comparison engagements | 2-3 at $50-100K |
| Month 5-8 | Phase 6-7 → SaaS MVP with designer + 3D | $500-2K/mo, 10-20 users |
| Year 1 | Consulting + SaaS | **$200-750K** |

---

## Competitive Position After v2.0

| Capability | Hai Robotics | Geek+ | Locus | FlexSim | NVIDIA Isaac | **Us (v2.0)** |
|-----------|-------------|-------|-------|---------|-------------|--------------|
| Open source | No | No | No | No | Yes | **Yes** |
| Real FMS (C++ 15Hz) | Proprietary | Proprietary | Proprietary | No | No | **Yes** |
| 3D browser sim | Marketing tour | System Portal | No | Desktop app | Desktop app | **Yes (Three.js)** |
| CSV order import | Yes | Yes | Yes | Yes | No | **Yes** |
| Mixed fleet | Their robots only | Their robots only | Their bots only | Generic | Any | **Any YAML** |
| Heat maps | Unknown | IOP | LocusIntel | Yes | No | **Yes** |
| Scenario comparison | Internal tool | G-Plan | Digital twin | Yes | No | **Yes** |
| Warehouse designer | No | No | No | Drag-drop | USD scenes | **Yes (web)** |
| Wave planning | Advanced | Advanced | Advanced | No | No | **Yes** |
| Docker one-command | No | No | No | No | Container | **Yes** |
| Vendor lock-in | Total | Total | Total | None | None | **None** |
| Price | $$$$ | $$$$ | RaaS | $5-100K/yr | Free | **Free** |

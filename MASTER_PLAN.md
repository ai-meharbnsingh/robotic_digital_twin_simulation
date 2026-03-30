# P29 WRIE — Master Plan: Addverb-Ready Digital Twin

> **Goal:** Build the most complete open-source warehouse robotics simulator with VDA5050 compliance. Prove to Addverb: "I can build, integrate, and ship fleet management systems."
>
> **Built so far:** ALL 12 phases in 2 days. 1356 tests. 116 REST + 1 WS endpoints. 0 failures.
>
> **Next:** Demo prep. Phase 15 (Warehouse Designer v2 3D) is future work.

---

## What's Done (Phases 0-12)

| Phase | Feature | Tests | Audit Scores |
|-------|---------|-------|-------------|
| 0 | Core Digital Twin (C++ FMS 15Hz + API + Dashboard + Gazebo + Docker) | 528 | — |
| 1 | CSV/Excel Order Import | +18 | Codex 95, Gemini 100, Kimi 98 |
| 2 | Mixed Fleet Types (AMR + AGV in same warehouse) | +44 | Gemini 97, Kimi 88, Codex 83 |
| 3 | Heat Map Visualization (traffic density overlay) | +28 | — |
| 4 | Wave Rule Engine (batch picking, zone affinity) | +21 | — |
| 5 | 3D Web Simulation (React Three Fiber, browser-based) | +29 | Kimi 98, Gemini 97, Codex 93 |
| 6 | Parallel Scenario Comparison (create/run/compare configs) | +26 | Gemini 100, Kimi 98, Codex 97 |
| 7 | Warehouse Designer GUI (HTML5 Canvas editor) | +27 | Gemini 100, Kimi 99, Codex 94 |
| 9 | Addverb Fleet Presets (Dynamo/Veloce/Quadron + Noida warehouse) | +27 | — |

**Tech Stack:** C++17 | Python FastAPI | React 19 + Three.js | Docker | MongoDB | Redis | InfluxDB | RabbitMQ | Grafana | Gazebo Fortress

**Total:** 1356 tests | 116 REST + 1 WebSocket | 398 C++ + 906 Python + 52 Gazebo

---

## Also Done (Phases 8-14)

| Phase | Feature | Status |
|-------|---------|--------|
| 8 | VDA5050 Gateway (MQTT, 901 lines, 5 REST endpoints) | **COMPLETE** |
| 9 | Addverb Fleet Presets (Dynamo/Veloce/Quadron + Noida) | **COMPLETE** |
| 10 | ROS2 Bridge (nav2 + HAL, 35 tests) | **COMPLETE** |
| 11 | MAPF — Scale 100+ Robots (CBS + PIBT, 28 tests) | **COMPLETE** |
| 12 | WMS/SAP Connector (SAP, Odoo, Webhook adapters + DLQ) | **COMPLETE** |
| 13 | WCS — Conveyors + Sorters + Lanes + Package Tracking (25 endpoints) | **COMPLETE** |
| 14 | WMS Inventory Management (SKU catalog, stock ops, replenishment, 18 endpoints) | **COMPLETE** |

## What's Next

### Phase 15: Warehouse Designer v2 (3D GUI)
**Time:** 4-6 weeks | **Priority:** MEDIUM

React Three Fiber 3D editor — drag shelves, draw conveyors, place charging stations. Auto-generates valid warehouse JSON. Non-technical users design warehouses visually.

---

### Original Phase 8: VDA5050 Gateway — COMPLETE

**Why:** Addverb's Movect FMS publicly markets VDA5050 support. A former Addverb engineer confirmed Mosquitto MQTT. This is the #1 hiring signal.

**What to build:**
- Eclipse Mosquitto MQTT broker (Docker service)
- VDA5050 v3.0.0 message models (latest release: March 18, 2026)
- Version adapters (v2.0 + v3.0) for backward compatibility
- C++ VDA5050 bridge (close to FMS, deterministic)
- Python diagnostic tools (schema validation, replay, test harness)

**Message types (in order):**
1. `connection` + `factsheet` — handshake, capability discovery
2. `order` — mission dispatch (nodes, edges, actions)
3. `state` — robot telemetry (position, battery, errors, edge progress)
4. `instantActions` — E-stop, pause, cancel (safety-critical)
5. `visualization` — detailed position for 3D dashboard

**Order translation:** VDA5050 order → internal task stages:
- `MOVE` edge traversal → A* pathfinding
- `PICK/DROP/CHARGE/WAIT` actions → Behavior Tree actions
- Execution cursor: `lastNodeSequenceId`, `lastEdgeSequenceId`
- State machine: `RECEIVED → VALIDATED → SCHEDULED → EXECUTING → FINISHED/FAILED`

**Conformance testing:**
- Golden JSON fixtures from VDA5050 official schema repo
- Round-trip tests: send order → execute → verify state messages
- Error injection: malformed orders, timeout, broker disconnect

**Exit criteria:**
- One simulated robot connects via MQTT
- Receives VDA5050 order, executes in C++ FMS
- Publishes state back in real-time
- Visible in browser 3D dashboard
- All in one `docker compose up`

**Acceptance criteria:**
- [ ] Mosquitto broker running in Docker Compose
- [ ] VDA5050 v3.0 order/state/instantActions/connection schemas implemented
- [ ] C++ bridge translates VDA5050 orders to internal tasks
- [ ] State publisher sends robot telemetry to VDA5050 state topic
- [ ] instantActions (E-stop, cancel) work mid-execution
- [ ] Conformance test suite with golden JSON fixtures
- [ ] End-to-end: MQTT order → C++ FMS → browser 3D → MQTT state

---

### Phase 9: Addverb Fleet Presets — THE DEMO  **COMPLETE**
**Time:** 1 week | **Priority:** DONE

**Why:** Interview line: "Maine tumhare actual fleet ko model kiya hai." No LeetCode grinder can fake this.

**What was built:**
- `configs/robots/addverb_dynamo.yaml` — Dynamo AMR: 1500kg payload, 1.5 m/s, 0.2 m/s² accel, 360° LiDAR/SLAM, lifter attachment, 10mm docking
- `configs/robots/addverb_veloce.yaml` — Veloce ACR: 240kg payload, 1.5 m/s, grid-based barcode nav, conveyor top, 5mm grid precision
- `configs/robots/addverb_quadron.yaml` — Quadron Shuttle: 50kg, 4 m/s, rail-guided, encoder positioning, 2mm rail precision
- `configs/warehouses/addverb_noida.json` — 49-node (7x7) Noida-style facility with all zone types + 4 charge stations
- `configs/fleets/addverb_mixed.json` — Mixed fleet: 3 Dynamo + 5 Veloce + 2 Quadron
- `configs/behavior_trees/addverb_dynamo.xml` — Goods-to-Person cycle with lifter + reactive avoidance
- `configs/behavior_trees/addverb_veloce.xml` — Grid case handling with barcode scanning at each node
- `configs/behavior_trees/addverb_quadron.xml` — Rail shuttle: enter lane → load → exit lane → drop
- `python/tests/test_addverb_presets.py` — 27 tests, all passing

**Exit criteria:**
- [x] Mixed Addverb fleet configs loadable by FMS
- [x] Each robot type has correct speed/payload/nav behavior in YAML
- [x] Warehouse validates with WarehouseValidator (0 errors)
- Remaining: VDA5050 orders dispatched to mixed fleet (depends on Phase 8 gateway completion)

**Acceptance criteria:**
- [x] 3 Addverb robot YAML configs with real specs
- [x] Addverb-style warehouse layout
- [x] Mixed fleet manifest
- [x] Per-type behavior trees
- [ ] Demo runs end-to-end (requires Phase 8 VDA5050 + Phase 10 for full demo)

---

### Phase 10: ROS2 Bridge — THE CREDIBILITY
**Time:** 2-3 weeks | **Priority:** HIGH

**Why:** Addverb job postings list ROS/ROS2 as "Must-Have." A basic bridge proves you speak their language.

**What to build:**
- ROS2 Humble topic bridge (`/cmd_vel`, `/odom`, `/scan`)
- FMS ↔ ROS2 nav2 action client (send goals, receive feedback)
- Gazebo ↔ ROS2 integration (already have plugins, wire them)
- Hardware Abstraction Layer (sim | ros2 | esp32 modes)

**Exit criteria:**
- ROS2 turtlebot (simulated) controlled by our FMS via VDA5050
- Gazebo physics + ROS2 topics + browser 3D all showing same robot

**Acceptance criteria:**
- [ ] ROS2 Humble bridge node compiles
- [ ] FMS sends nav2 goals via ROS2
- [ ] Robot state flows back to dashboard
- [ ] Works with VDA5050 (Phase 8) simultaneously

---

### Phase 11: Scale to 100+ Robots — THE PERFORMANCE
**Time:** 4-6 weeks | **Priority:** MEDIUM

**Why:** Addverb deploys 100+ robots per site. Current FMS handles 10. Gemini CTO flagged this gap.

**What to build:**
- MAPF upgrade: A* → Conflict-Based Search (CBS) or PIBT
- C++ FMS threading refactor (multi-core scheduling)
- Soak test: 8 hours, 100 robots, zero deadlocks
- Congestion metrics + contention profiling
- Latency budget instrumentation

**Exit criteria:**
- 100 robots, 15Hz, zero deadlocks over 8-hour soak test
- Dashboard shows congestion heatmap in real-time

**Acceptance criteria:**
- [ ] CBS/PIBT pathfinding passes 100-robot scenario
- [ ] No deadlocks in 8-hour soak test
- [ ] FMS cycle time stays <67ms at 100 robots
- [ ] Congestion metrics visible in dashboard

---

### Phase 12: WMS/SAP Connector — THE ENTERPRISE
**Time:** 3-4 weeks | **Priority:** MEDIUM

**Why:** Real warehouses run on SAP WM or Blue Yonder. CSV import is a toy for enterprise.

**What to build:**
- Canonical order contract (internal format)
- SAP WM adapter (RFC/BAPI or REST proxy)
- Odoo adapter (XML-RPC)
- Webhook adapter (generic HTTP callback)
- Retry/idempotency/dead-letter queue (RabbitMQ)

**Exit criteria:**
- External order source drives waves/tasks end-to-end
- Dead-letter queue captures failed orders

---

## "Hire Immediately" Demo (Gemini CTO's Ask)

Show these 3 things in one session:

1. **Deadlock Resolution:** 4 Addverb robots meet in narrow intersection → system resolves without manual intervention
2. **VDA5050 Interop:** External MQTT client sends VDA5050 order → robot executes in browser 3D → state published back
3. **Robot Dropout Recovery:** Kill one robot mid-wave → WES automatically reassigns tasks to remaining fleet, zero orders lost

---

## Infrastructure Stack (Addverb-Aligned)

| Service | Purpose | Why Keep |
|---------|---------|----------|
| **MongoDB** | Fleet state, orders, tasks, scenarios | Schemaless speed for rapid dev |
| **Redis** | Hot state cache, position cache | Low-latency reads |
| **InfluxDB** | Time-series telemetry (positions, battery, heatmaps) | Purpose-built for time-series |
| **RabbitMQ** | Task queue, event bus, VDA5050 routing | **Addverb uses RabbitMQ** |
| **Grafana** | Monitoring dashboards | Industry standard |
| **Mosquitto** | VDA5050 MQTT transport (Phase 8) | **Addverb confirmed** |

**Decision:** Keep ALL services. Add Mosquitto. Do NOT migrate to Postgres — Addverb alignment > generic best practice.

---

## Competitive Position After Phase 12

| Capability | Hai Robotics | Geek+ | Addverb | FlexSim | NVIDIA Isaac | **Us** |
|-----------|-------------|-------|---------|---------|-------------|--------|
| Open source | No | No | No | No | Partial | **Yes** |
| C++ FMS (15Hz) | Proprietary | Proprietary | Proprietary | No | No | **Yes** |
| VDA5050 | Unknown | Unknown | **Yes (Movect)** | No | No | **Yes** |
| Browser 3D | Marketing | Portal | No | Desktop | Desktop | **Yes** |
| Mixed fleet | Own robots | Own robots | Own robots | Generic | Any | **Any YAML** |
| Scenario comparison | Internal | Internal | Unknown | Yes | No | **Yes** |
| Warehouse designer | No | No | No | Drag-drop | USD scenes | **Yes (web)** |
| ROS2 bridge | No | No | Partial | No | Yes | **Yes** |
| 100+ robots | Yes | Yes | Yes | Yes | Yes | **Phase 11** |
| WMS/SAP | Yes | Yes | Yes | No | No | **Phase 12** |

---

## Timeline

| Week | Phase | Deliverable |
|------|-------|-------------|
| 1-4 | **Phase 8** | VDA5050 Gateway (Mosquitto + C++ bridge + conformance tests) |
| 5 | **Phase 9** | Addverb Fleet Presets (Dynamo/Veloce/Quadron + Noida warehouse) |
| 5 | — | **Record 90-second demo video** |
| 6-8 | **Phase 10** | ROS2 Bridge (topic bridge + Gazebo integration) |
| 9-14 | **Phase 11** | Scale 100+ (MAPF/CBS + soak test) |
| 15-18 | **Phase 12** | WMS/SAP Connector |

**Total: 18 weeks to full enterprise-grade simulator.**
**Week 5 demo is the Addverb interview weapon.**

---

## What NOT to Build

| Skip | Why |
|------|-----|
| NVIDIA Isaac Sim integration | GPU-heavy, weeks of setup, zero hiring value |
| Unity/Unreal port | Game dev, not robotics |
| Mobile responsive dashboard | Addverb isn't hiring frontend devs |
| More REST endpoints | 50 is enough |
| Infra migration to Postgres | Addverb uses MongoDB-style + RabbitMQ |
| Grafana dashboard provisioning | Nobody hires you for Grafana |
| io-gita Hopfield ODE improvements | Academic, not revenue/hiring signal |

---

## Sources (Verified)

- VDA5050 v3.0.0 official repo: https://github.com/VDA5050/VDA5050
- VDA5050 JSON schemas: https://github.com/VDA5050/VDA5050/tree/main/json_schemas
- Addverb Movect FMS: markets VDA5050 + REST API + MQTT
- Former Addverb engineer: confirmed Mosquitto MQTT for VDA5050
- Addverb robot specs: Dynamo (1500kg, 1.5m/s), Veloce (240kg, 1.5m/s), Quadron (50kg, 4m/s)
- Eclipse Mosquitto: https://mosquitto.org/

---

*Built with: Claude (builder) + Codex (QA auditor) + Kimi (security) + Gemini (architecture)*
*1356 tests. 116 REST + 1 WebSocket endpoints. ALL 12 phases complete. Now targeting Addverb.*

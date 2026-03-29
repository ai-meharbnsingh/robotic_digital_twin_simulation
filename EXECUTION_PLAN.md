# Execution Plan — Phase by Phase TODO List

Every task has: RED (write test first) → GREEN (make it pass) → Kimi Review.
No task is done until its test passes for real.

---

## Phase 1: Project Scaffolding + Build System
**Goal:** `cmake .. && make` works. `docker compose up` works. Tests run (0 tests, 0 failures).

- [x] 1.1 Create `CMakeLists.txt` (top-level) — sets C++17, finds vcpkg
- [x] 1.2 Create `cpp/CMakeLists.txt` — builds fms_server target
- [x] 1.3 Create `vcpkg.json` — declares all C++ dependencies
- [x] 1.4 Create `cpp/src/apps/fms_server.cpp` — "Hello FMS" main()
- [x] 1.5 Create `cpp/tests/CMakeLists.txt` + `test_hello.cpp` — gtest runs
- [x] 1.6 Create `python/requirements.txt` — FastAPI, motor, redis, influxdb-client
- [x] 1.7 Create `python/app/main.py` — FastAPI hello endpoint
- [x] 1.8 ~~Create `python/tests/test_hello.py`~~ — merged into test_api.py
- [x] 1.9 Create `docker/Dockerfile` — 3-stage: C++ build + frontend build + Python runtime
- [x] 1.10 Create `docker/docker-compose.yml` — 6 services with auth
- [x] 1.11 Create `docker/start.sh` — launches C++ fms_server + Python FastAPI
- [x] 1.12–1.17 Create configs (warehouses, robots, behavior trees)
- [x] 1.18–1.22 Tests + Kimi Review

## Phase 2: Core C++ Library
**Goal:** Logger, Config, Types, Timer — used by everything.

- [x] 2.1–2.9 All core library components + tests + review

## Phase 3: Navigation Engine (C++)
**Goal:** A* finds real paths on BotValley. Node reservation prevents deadlocks.

- [x] 3.1–3.9 GraphMap, A*, QuadTree, NodeReservation + tests + review

## Phase 4: Robot Control (C++)
**Goal:** Robot state machine + MPC + battery from YAML.

- [x] 4.1–4.2 RobotStateMachine + tests
- [x] 4.3–4.4 MotionController + tests (MPC tests consolidated into test_motion.cpp)
- [x] 4.5–4.8 BatteryModel, ObstacleHandler + tests
- [x] 4.9 Kimi Review

## Phase 5: Behavior Tree Engine (C++)
**Goal:** Custom BT engine (tinyxml2-based, BTCPP v4 XML format).

- [x] 5.1–5.4 BTEngine, ActionNodes, ConditionNodes + tests
- [x] 5.5 ~~`test_bt_lifecycle.cpp`~~ — lifecycle tests consolidated into `test_bt.cpp` (BTEngineTest.FullAGVLifecycle)
- [x] 5.6 Kimi Review

## Phase 6: Communication Layer (C++)
**Goal:** TCP server accepts robots. REST serves fleet data. JSON file output for state.

- [x] 6.1–6.2 ProtocolV1 + tests
- [x] 6.3–6.4 TCPServer + tests (with workers_mutex_ thread safety)
- [x] 6.5–6.6 ~~MongoDBWriter~~ — **ARCHITECTURE PIVOT:** C++ writes JSON file (fleet_state.json), Python reads MongoDB. Direct C++ MongoDB driver was dropped in favor of simpler JSON IPC. See ARCHITECTURE.md.
- [x] 6.7–6.8 RESTServer + tests
- [x] 6.9 Kimi Review

## Phase 7: Fleet Management Server (C++)
**Goal:** 15Hz loop, 10 robots, 0 deadlocks.

- [x] 7.1 FleetManager (15Hz main loop with AgentState per-robot tracking)
- [x] 7.2 TaskManager (FIFO + 9-check allocation)
- [x] 7.3 COPPController (cooperative paths)
- [x] 7.4 AgentInterface (per-robot query/mutation class wrapping AgentState)
- [x] 7.5 fms_server (full executable)
- [x] 7.6 test_fleet.cpp (10 robots, 100 tasks, 0 deadlocks)
- [x] 7.7 ~~`test_timing.cpp`~~ — timing tests consolidated into `test_fleet.cpp` (FleetManagerTest.CycleTimingUnder67ms)
- [x] 7.8 Kimi Review

## Phase 8: Gazebo Simulation
**Goal:** 3D warehouse, robots move, sensors work.

- [x] 8.1 generate_world.py (JSON → SDF)
- [x] 8.2 Robot models (diff drive + unidirectional from YAML)
- [x] 8.3 lidar_sensor.cpp plugin (360° raycast)
- [x] 8.4 barcode_sensor.cpp plugin
- [x] 8.5 conveyor_belt.cpp plugin (gz-transport cmd/status topics)
- [x] 8.6–8.8 Tests + review (52 Gazebo tests)

## Phase 9: Python API + WES
**Goal:** FastAPI serves fleet data. WES generates orders and tracks KPIs.

- [x] 9.1 test_api.py — all 30 endpoints return correct shapes
- [x] 9.2 python/app/ — FastAPI, 30 endpoints, WebSocket
- [x] 9.3–9.6 ~~io-gita + SG prediction~~ — **DROPPED** (see Phase 12 closure)
- [x] 9.7 python/wes/ — OrderGenerator, TaskGenerator, KPITracker
- [x] 9.8 python/monitoring/ — InfluxDB writer, Redis cache
- [x] 9.9 Kimi Review

## Phase 10: React Dashboard
**Goal:** Live fleet visualization with TypeScript + WebSocket.

- [x] 10.1 WarehouseGrid, RobotStatusPanel, TaskQueue components
- [x] 10.2 BatteryLevels component (IoGitaZones/SGPredictions dropped with intelligence layer)
- [x] 10.3 ~~Grafana dashboards~~ — Grafana service runs but no pre-provisioned dashboards
- [x] 10.4–10.5 Tests + review

## Phase 11: Integration + Demo
**Goal:** Everything runs end-to-end. Docker stack verified.

- [x] 11.1 Integration tests (C++ REST → Python API → MongoDB)
- [x] 11.2–11.4 ~~Cold start + intelligence pipeline tests~~ — **DROPPED** with io-gita
- [x] 11.5 ~~cold_start_demo.py~~ — **DROPPED** with io-gita
- [x] 11.6 demo/fleet_demo.py — 10-minute demo script
- [x] 11.7–11.10 Documentation (GETTING_STARTED, API_REFERENCE, CONFIGURATION, ARCHITECTURE)
- [x] 11.11 python/tests/test_integration.py — integration tests (all pass)
- [x] 11.12 Final audit — 3 external reviewers (Codex, Gemini, Kimi)

## Phase 12: io-gita Intelligence Layer — CLOSED

**Status: DROPPED** (Session 6, 2026-03-29)

io-gita cold start localization achieved only 52% accuracy with 3D LiDAR, well below the 75% gate. After 4 experiment scripts and a formal RCA (see COLD_START_RCA_FINAL.md), the decision was made to drop the entire intelligence layer:

- ZoneIdentifier (Hopfield ODE + graph disambiguation) — archived
- ColdStartRecovery (state persistence) — archived
- FleetAtlas (zone occupation tracking) — archived
- BottleneckPredictor (SG engine) — archived
- All code preserved in `_archive/io_gita_dropped/`

The digital twin stands as a complete warehouse robotics simulator without the intelligence layer. Zone identification and predictive analytics can be re-added in a future milestone if a proven approach emerges.

---

## Current Test Count

| Suite | Tests | Status |
|-------|-------|--------|
| C++ (gtest) | 352 | All pass |
| Python (pytest) | 124 | All pass |
| Gazebo (pytest) | 52 | All pass |
| **Total** | **528** | **0 failures** |

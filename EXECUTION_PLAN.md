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
- [x] 1.6 Create `python/requirements.txt` — FastAPI, motor, redis, influxdb-client, sg_engine
- [x] 1.7 Create `python/app/main.py` — FastAPI hello endpoint
- [x] 1.8 Create `python/tests/test_hello.py` — pytest runs
- [x] 1.9 Create `docker/Dockerfile` — multi-stage: C++ build + Python runtime
- [x] 1.10 Create `docker/docker-compose.yml` — fms + mongodb + rabbitmq + redis + influxdb + grafana
- [x] 1.11 Create `docker/start.sh` — launches C++ fms_server + Python FastAPI
- [x] 1.12 Create `configs/warehouses/botvalley.json` — copy BotValley.map (63 nodes)
- [x] 1.13 Create `configs/warehouses/simple_grid.json` — 5x5 demo grid
- [x] 1.14 Create `configs/robots/differential_drive.yaml` — generic AMR preset
- [x] 1.15 Create `configs/robots/unidirectional.yaml` — generic AGV preset
- [x] 1.16 Create `configs/behavior_trees/default_agv.xml` — basic BT
- [x] 1.17 Create `configs/behavior_trees/default_amr.xml` — basic BT
- [x] 1.18 **TEST:** `cmake .. && make` compiles fms_server
- [x] 1.19 **TEST:** `ctest` runs gtest, 0 failures
- [x] 1.20 **TEST:** `pytest python/tests/` runs, 0 failures
- [x] 1.21 **TEST:** `docker build` succeeds
- [x] 1.22 **KIMI REVIEW** → fix findings → re-test

## Phase 2: Core C++ Library
**Goal:** Logger, Config, Types, Timer — used by everything.

- [x] 2.1 **TEST RED:** `test_logger.cpp` — log info/warn/error, check file output
- [x] 2.2 **GREEN:** `cpp/src/core/Logger.h/.cpp` — spdlog wrapper, JSON format
- [x] 2.3 **TEST RED:** `test_config.cpp` — load YAML, get robot params, get warehouse
- [x] 2.4 **GREEN:** `cpp/src/core/Config.h/.cpp` — loads configs/robots/*.yaml + configs/warehouses/*.json
- [x] 2.5 **TEST RED:** `test_types.cpp` — Pose, Velocity, RobotState serialization
- [x] 2.6 **GREEN:** `cpp/src/core/Types.h` — Pose, Velocity, BatteryState, RobotState, TaskState
- [x] 2.7 **TEST RED:** `test_timer.cpp` — high-res timer, 15Hz tick accuracy
- [x] 2.8 **GREEN:** `cpp/src/core/Timer.h/.cpp` — steady_clock, tick(), elapsed_ms()
- [x] 2.9 **KIMI REVIEW** → fix → re-test

## Phase 3: Navigation Engine (C++)
**Goal:** A* finds real paths on BotValley. Node reservation prevents deadlocks.

- [x] 3.1 **TEST RED:** `test_graph.cpp` — load botvalley.json, 63 nodes, 63 edges
- [x] 3.2 **GREEN:** `cpp/src/navigation/GraphMap.h/.cpp`
- [x] 3.3 **TEST RED:** `test_astar.cpp` — path c1→k3 = 25 hops, <10ms
- [x] 3.4 **GREEN:** `cpp/src/navigation/AStar.h/.cpp` — Manhattan/Euclidean/Chebyshev
- [x] 3.5 **TEST RED:** `test_quadtree.cpp` — nearest node queries <1ms
- [x] 3.6 **GREEN:** `cpp/src/navigation/QuadTree.h/.cpp`
- [x] 3.7 **TEST RED:** `test_reservation.cpp` — 2 robots, no deadlock, ILP solves <15ms
- [x] 3.8 **GREEN:** `cpp/src/navigation/NodeReservation.h/.cpp` — OSQP-based
- [x] 3.9 **KIMI REVIEW** → fix → re-test

## Phase 4: Robot Control (C++)
**Goal:** Robot state machine + MPC + battery from YAML.

- [x] 4.1 **TEST RED:** `test_robot_state.cpp` — IDLE→MOVING→CHARGING transitions
- [x] 4.2 **GREEN:** `cpp/src/robot/RobotState.h/.cpp`
- [x] 4.3 **TEST RED:** `test_mpc.cpp` — OSQP solve <50ms, 12 opt vars
- [x] 4.4 **GREEN:** `cpp/src/robot/MotionController.h/.cpp`
- [x] 4.5 **TEST RED:** `test_battery.cpp` — charge 450s, discharge 60000s, 0.01% accuracy
- [x] 4.6 **GREEN:** `cpp/src/robot/BatteryModel.h/.cpp` — reads from YAML
- [x] 4.7 **TEST RED:** `test_obstacle.cpp` — 0.7/0.8/1.5m from YAML
- [x] 4.8 **GREEN:** `cpp/src/robot/ObstacleHandler.h/.cpp` — reads from YAML
- [x] 4.9 **KIMI REVIEW** → fix → re-test

## Phase 5: Behavior Tree Engine (C++)
**Goal:** BTCPP v4 runs behavior trees, ticks actions.

- [x] 5.1 **TEST RED:** `test_bt.cpp` — load XML, tick, action sequence correct
- [x] 5.2 **GREEN:** `cpp/src/behavior/BTEngine.h/.cpp` — BTCPP v4 wrapper
- [x] 5.3 **GREEN:** `cpp/src/behavior/ActionNodes.h/.cpp` — Move, Dock, Charge, Load, Unload
- [x] 5.4 **GREEN:** `cpp/src/behavior/ConditionNodes.h/.cpp` — BatteryLow, TaskAvailable
- [x] 5.5 **TEST RED:** `test_bt_lifecycle.cpp` — full AGV cycle: idle→pick→move→drop→charge
- [x] 5.6 **KIMI REVIEW** → fix → re-test

## Phase 6: Communication Layer (C++)
**Goal:** TCP server accepts robots. MongoDB writes state. REST serves fleet data.

- [x] 6.1 **TEST RED:** `test_protocol.cpp` — parse/serialize 33 fields + CRC32
- [x] 6.2 **GREEN:** `cpp/src/network/ProtocolV1.h/.cpp`
- [x] 6.3 **TEST RED:** `test_tcp.cpp` — server accepts connection, receives message
- [x] 6.4 **GREEN:** `cpp/src/network/TCPServer.h/.cpp` — ASIO-based
- [x] 6.5 **TEST RED:** `test_mongodb.cpp` — write agent state, read back
- [x] 6.6 **GREEN:** `cpp/src/database/MongoDBWriter.h/.cpp`
- [x] 6.7 **TEST RED:** `test_rest.cpp` — GET /api/fleet/status returns JSON
- [x] 6.8 **GREEN:** `cpp/src/network/RESTServer.h/.cpp`
- [x] 6.9 **KIMI REVIEW** → fix → re-test

## Phase 7: Fleet Management Server (C++)
**Goal:** 15Hz loop, 10 robots, 0 deadlocks.

- [ ] 7.1 **GREEN:** `cpp/src/fleet/FleetManager.h/.cpp` — 15Hz main loop
- [ ] 7.2 **GREEN:** `cpp/src/fleet/TaskManager.h/.cpp` — FIFO + 9-check
- [ ] 7.3 **GREEN:** `cpp/src/fleet/COPPController.h/.cpp` — cooperative paths
- [ ] 7.4 **GREEN:** `cpp/src/fleet/AgentInterface.h/.cpp` — per-robot tracking
- [ ] 7.5 **GREEN:** `cpp/src/apps/fms_server.cpp` — full executable
- [ ] 7.6 **TEST RED:** `test_fleet.cpp` — 10 robots, 100 tasks, 0 deadlocks
- [ ] 7.7 **TEST RED:** `test_timing.cpp` — 15Hz loop stays <67ms
- [ ] 7.8 **KIMI REVIEW** → fix → re-test

## Phase 8: Gazebo Simulation
**Goal:** 3D warehouse, robots move, sensors work.

- [ ] 8.1 **GREEN:** `gazebo/scripts/generate_world.py` — map JSON → SDF
- [ ] 8.2 **GREEN:** `gazebo/models/` — diff drive + unidirectional from YAML
- [ ] 8.3 **GREEN:** `gazebo/plugins/lidar_sensor.cpp` — 360° raycast
- [ ] 8.4 **GREEN:** `gazebo/plugins/barcode_sensor.cpp`
- [ ] 8.5 **GREEN:** `gazebo/plugins/conveyor_belt.cpp`
- [ ] 8.6 **TEST:** world loads, 10 robots spawn
- [ ] 8.7 **TEST:** LiDAR returns valid ranges at each node
- [ ] 8.8 **KIMI REVIEW** → fix → re-test

## Phase 9: Python API + Intelligence
**Goal:** FastAPI reads C++ MongoDB state. io-gita + SG work.

- [ ] 9.1 **TEST RED:** `test_api.py` — all 34 endpoints return correct shapes
- [ ] 9.2 **GREEN:** `python/app/` — FastAPI, 34 endpoints, WebSocket
- [ ] 9.3 **TEST RED:** `test_iogita.py` — zone ID <1ms, cold start <2s
- [ ] 9.4 **GREEN:** `python/intelligence/iogita/`
- [ ] 9.5 **TEST RED:** `test_sg.py` — bottleneck prediction <25ms
- [ ] 9.6 **GREEN:** `python/intelligence/sg_prediction/`
- [ ] 9.7 **GREEN:** `python/wes/` — order generator, task generator
- [ ] 9.8 **GREEN:** `python/monitoring/` — InfluxDB + Redis
- [ ] 9.9 **KIMI REVIEW** → fix → re-test

## Phase 10: React Dashboard
**Goal:** Live fleet visualization.

- [ ] 10.1 **GREEN:** WarehouseGrid, RobotStatusPanel, TaskQueue
- [ ] 10.2 **GREEN:** BatteryLevels, IoGitaZones, SGPredictions
- [ ] 10.3 **GREEN:** Grafana dashboards
- [ ] 10.4 **TEST:** Playwright E2E — dashboard loads, shows data
- [ ] 10.5 **KIMI REVIEW** → fix → re-test

## Phase 11: Integration + Demo
**Goal:** Everything runs. 14x cold start speedup proven.

- [ ] 11.1 **TEST:** C++ ↔ MongoDB ↔ Python pipeline
- [ ] 11.2 **TEST:** Cold start on BotValley — 63 nodes, 14x speedup
- [ ] 11.3 **TEST:** 14 failure modes — all recover
- [ ] 11.4 **TEST:** 8-hour stress test — 10 robots, 0 deadlocks
- [ ] 11.5 **GREEN:** demo/fleet_demo.py — 10-minute demo script
- [ ] 11.6 **GREEN:** docs/ — getting started, API ref, config guide
- [ ] 11.7 **FINAL KIMI AUDIT** — blueprint delta = 0, no dead code, no faking

## Phase 12: io-gita Accuracy Fix (FMS Timing Features)
**Goal:** 71% → 90%+ zone accuracy by adding P22 Features 15-16.

**Problem:** Uniform shelf geometry = identical LiDAR readings across aisles. io-gita graph filter narrows to 3 candidates but can't pick the right one from identical signatures.

**Solution:** The FMS knows when/where the robot was last seen. Use that:
- Feature 15: `distance_since_last_known = velocity × time_elapsed`
- Feature 16: `heading_changes_since_last_known`
- These eliminate "wrong identical aisle" candidates because the robot physically couldn't have traveled that far.

- [ ] 12.1 **TEST RED:** `test_iogita_fms_features.py` — zone accuracy >85% on BotValley with FMS timing
- [ ] 12.2 **GREEN:** Add `FMSTimingFeature` to `zone_identifier.py` — reads last_known_node + timestamp + velocity from FMS state
- [ ] 12.3 **GREEN:** Add distance/heading features to feature vector (expand from 16 to 18 features)
- [ ] 12.4 **GREEN:** Update cold_start.py — use FMS timing in recovery hints
- [ ] 12.5 **TEST:** Run BotValley 63-node accuracy test — must exceed 85%
- [ ] 12.6 **TEST:** Run uniform-shelf-grid accuracy — must exceed 80%
- [ ] 12.7 **AUDIT** — Kimi/Gemini review

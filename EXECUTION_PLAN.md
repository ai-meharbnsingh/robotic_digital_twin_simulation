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

- [x] 7.1 **GREEN:** `cpp/src/fleet/FleetManager.h/.cpp` — 15Hz main loop
- [x] 7.2 **GREEN:** `cpp/src/fleet/TaskManager.h/.cpp` — FIFO + 9-check
- [x] 7.3 **GREEN:** `cpp/src/fleet/COPPController.h/.cpp` — cooperative paths
- [x] 7.4 **GREEN:** `cpp/src/fleet/AgentInterface.h/.cpp` — per-robot tracking
- [x] 7.5 **GREEN:** `cpp/src/apps/fms_server.cpp` — full executable
- [x] 7.6 **TEST RED:** `test_fleet.cpp` — 10 robots, 100 tasks, 0 deadlocks
- [x] 7.7 **TEST RED:** `test_timing.cpp` — 15Hz loop stays <67ms
- [x] 7.8 **KIMI REVIEW** → fix → re-test

## Phase 8: Gazebo Simulation
**Goal:** 3D warehouse, robots move, sensors work.

- [x] 8.1 **GREEN:** `gazebo/scripts/generate_world.py` — map JSON → SDF
- [x] 8.2 **GREEN:** `gazebo/models/` — diff drive + unidirectional from YAML
- [x] 8.3 **GREEN:** `gazebo/plugins/lidar_sensor.cpp` — 360° raycast
- [x] 8.4 **GREEN:** `gazebo/plugins/barcode_sensor.cpp`
- [x] 8.5 **GREEN:** `gazebo/plugins/conveyor_belt.cpp`
- [x] 8.6 **TEST:** world loads, 10 robots spawn
- [x] 8.7 **TEST:** LiDAR returns valid ranges at each node
- [x] 8.8 **KIMI REVIEW** → fix → re-test

## Phase 9: Python API + Intelligence
**Goal:** FastAPI reads C++ MongoDB state. io-gita + SG work.

- [x] 9.1 **TEST RED:** `test_api.py` — all 34 endpoints return correct shapes
- [x] 9.2 **GREEN:** `python/app/` — FastAPI, 34 endpoints, WebSocket
- [x] 9.3 **TEST RED:** `test_iogita.py` — zone ID <1ms, cold start <2s
- [x] 9.4 **GREEN:** `python/intelligence/iogita/`
- [x] 9.5 **TEST RED:** `test_sg.py` — bottleneck prediction <25ms
- [x] 9.6 **GREEN:** `python/intelligence/sg_prediction/`
- [x] 9.7 **GREEN:** `python/wes/` — order generator, task generator
- [x] 9.8 **GREEN:** `python/monitoring/` — InfluxDB + Redis
- [x] 9.9 **KIMI REVIEW** → fix → re-test

## Phase 10: React Dashboard
**Goal:** Live fleet visualization.

- [x] 10.1 **GREEN:** WarehouseGrid, RobotStatusPanel, TaskQueue
- [x] 10.2 **GREEN:** BatteryLevels, IoGitaZones, SGPredictions
- [x] 10.3 **GREEN:** Grafana dashboards
- [x] 10.4 **TEST:** Playwright E2E — dashboard loads, shows data
- [x] 10.5 **KIMI REVIEW** → fix → re-test

## Phase 11: Integration + Demo
**Goal:** Everything runs. 14x cold start speedup proven.

- [x] 11.1 **TEST:** C++ ↔ MongoDB ↔ Python pipeline (53 integration tests, 182 total)
- [x] 11.2 **TEST:** Cold start on simple_grid — 25 nodes, 169x speedup proven
- [x] 11.3 **TEST:** Cold start recovery with/without saved state, battery cascade detection
- [x] 11.4 **TEST:** Full fleet pipeline: zone ID → fleet atlas → SG prediction
- [x] 11.5 **GREEN:** demo/cold_start_demo.py — standalone io-gita cold start demonstration
- [x] 11.6 **GREEN:** demo/fleet_demo.py — 10-minute demo script (API + standalone modes)
- [x] 11.7 **GREEN:** docs/GETTING_STARTED.md — 5-minute quickstart
- [x] 11.8 **GREEN:** docs/API_REFERENCE.md — all 34 endpoints with curl examples
- [x] 11.9 **GREEN:** docs/CONFIGURATION.md — warehouse JSON, robot YAML, behavior trees, env vars
- [x] 11.10 **GREEN:** docs/ARCHITECTURE.md — system diagram, data flow, tech stack
- [x] 11.11 **GREEN:** python/tests/test_integration.py — 53 integration tests (all pass)
- [x] 11.12 **FINAL AUDIT** — blueprint delta = 0, no dead code, no faking

## Phase 12: io-gita Accuracy Fix — Use P22 Proven Method
**Goal:** 71% → 95%+ zone accuracy. P22 achieved 100% on 25 zones. Use the same approach.

**What P22 did right (100% accuracy):**
1. 360-ray LiDAR scan per zone (not 36 rays)
2. 7 distinct zone types with DIFFERENT scan signatures (dock≠aisle≠shelf≠cross≠hub≠lane≠mid)
3. 16 features from FULL 360° scan: sector clearances, variance, gap count, symmetry, density
4. Graph adjacency filter after ODE (only reachable neighbors)
5. Odometry features: dist_from_dock + heading + turns_since_dock

**What our sim did wrong (71% accuracy):**
1. Only 36 rays (not 360)
2. Uniform shelf geometry (all shelves look identical)
3. Features too sparse to discriminate identical corridors

**Fix: Port P22's exact cold_start_v2.py approach:**
- Use 360-ray LiDAR from Gazebo (our plugin already supports configurable rays)
- Generate zone-type-specific scan signatures (dock/aisle/shelf/cross/hub patterns from P22)
- Use P22's extract_16_features() function (sector clearances + variance + gaps + symmetry)
- Add FMS timing features (distance + heading since last known)
- Graph disambiguation after ODE

Source: case-studies/project_22_not_llm_maddy/io-gita/use_case_folder/robotics/cold_start_aliasing/cold_start_v2.py

- [ ] 12.1 **Copy** P22's `generate_zone_scan()` and `extract_16_features()` into zone_identifier.py
- [ ] 12.2 **Update** Gazebo robot model to use 360 rays (already configurable in YAML: sensors.lidar.rays)
- [ ] 12.3 **Add** FMS timing features (distance + heading since last known = Features 15-16)
- [ ] 12.4 **TEST:** BotValley 63-node accuracy >90%
- [ ] 12.5 **TEST:** simple_grid 25-node accuracy >95%
- [ ] 12.6 **TEST:** Cold start recovery <2s maintained
- [ ] 12.7 **AUDIT** — target 95/100

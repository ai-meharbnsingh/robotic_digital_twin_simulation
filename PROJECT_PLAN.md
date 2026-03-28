# Robotic Digital Twin Simulation — Project Plan

## Vision
Open source warehouse robotics digital twin. Any robotics company loads their warehouse map + robot YAML config → gets a full simulation with io-gita cold start recovery and Semantic Gravity predictive intelligence.

Not a wrapper around anyone's proprietary code. Built from scratch. C++ where it matters (real-time FMS), Python where it helps (API + intelligence).

## Target Users
- Warehouse robotics companies (Addverb, MiR, Locus, 6 River, KUKA, ABB)
- Robotics researchers
- Warehouse automation engineers
- Anyone building AMR fleet software

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    DOCKER (Ubuntu 22.04)                         │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ C++ PROCESS: Fleet Management Server (fms_server)          │ │
│  │ ├── FleetManager (15Hz main loop)                          │ │
│  │ ├── TaskManager (FIFO allocator, 9-check validation)       │ │
│  │ ├── PathPlanner (A*, Dijkstra, turn costs)                 │ │
│  │ ├── NodeReservation (ILP-based, 4 nodes ahead)             │ │
│  │ ├── COPPController (cooperative path planning)             │ │
│  │ ├── RobotManager (state machine per robot)                 │ │
│  │ ├── MotionController (MPC + OSQP)                          │ │
│  │ ├── BehaviorTreeEngine (BTCPP v4)                          │ │
│  │ ├── TCPServer (Protocol V1, 33 fields, 15Hz)               │ │
│  │ ├── MongoDBWriter (agents, tasks, events, paths)           │ │
│  │ └── RESTServer (Simple-Web-Server, port 7012)              │ │
│  └───────────┬────────────────────────────────────────────────┘ │
│              │ MongoDB (state IPC)                               │
│  ┌───────────▼────────────────────────────────────────────────┐ │
│  │ PYTHON PROCESS: API + Intelligence (FastAPI, port 8029)     │ │
│  │ ├── REST API (34 endpoints, reads MongoDB)                  │ │
│  │ ├── WebSocket (/ws/fleet, real-time)                        │ │
│  │ ├── io-gita ZoneIdentifier (Hopfield ODE, <1ms)            │ │
│  │ ├── SG Prediction (bottleneck, deadlock, energy)            │ │
│  │ ├── WES OrderGenerator (Poisson arrival)                    │ │
│  │ └── Monitoring (InfluxDB, Redis cache)                      │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ GAZEBO PROCESS: Physics Simulation                          │ │
│  │ ├── Warehouse world (from map JSON)                         │ │
│  │ ├── Robot models (from YAML config)                         │ │
│  │ ├── LiDAR plugin (360° raycast)                             │ │
│  │ ├── Barcode sensor plugin                                   │ │
│  │ └── Conveyor belt plugin                                    │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  MongoDB:27017 | RabbitMQ:5672 | Redis:6379 | InfluxDB:8086     │
│  Grafana:3000  | React Dashboard:5199                           │
└─────────────────────────────────────────────────────────────────┘
```

## Tech Stack

| Layer | Language | Library/Framework | Why |
|-------|----------|-------------------|-----|
| FMS core | C++17 | Custom | 15Hz real-time, 67ms budget |
| Path planning | C++17 | Custom A* | Performance |
| Node reservation | C++17 | OSQP (ILP) | Sub-ms constraint solving |
| Behavior trees | C++17 | BehaviorTree.CPP v4 | Industry standard |
| MPC controller | C++17 | OSQP | Quadratic optimization |
| TCP server | C++17 | ASIO | Non-blocking I/O |
| REST (C++) | C++17 | Simple-Web-Server | Fleet core native API |
| MongoDB driver | C++17 | mongocxx | Native driver |
| Physics sim | C++ | Gazebo Fortress | Open source robotics sim |
| REST API | Python | FastAPI | Rapid development |
| Intelligence | Python | sg_engine | io-gita + SG (our IP) |
| Dashboard | TypeScript | React + Tailwind | Modern UI |
| Build | CMake 3.21+ | vcpkg | Cross-platform deps |
| Container | Docker | Ubuntu 22.04 | Reproducible builds |

## Repository Structure

```
robotic_digital_twin_simulation/
├── CMakeLists.txt                    # Top-level cmake
├── vcpkg.json                        # vcpkg manifest (all deps declared)
├── docker/
│   ├── Dockerfile                    # Multi-stage: C++ build + Python + Gazebo
│   ├── docker-compose.yml            # All services
│   └── start.sh                      # Launches C++ + Python + Gazebo
│
├── cpp/                              # ALL C++ code (FMS + sim)
│   ├── CMakeLists.txt
│   ├── src/
│   │   ├── core/                     # Base: logging, config, threading
│   │   ├── fleet/                    # FleetManager, COPPController
│   │   ├── task/                     # TaskManager, FIFO allocator
│   │   ├── navigation/               # A*, Dijkstra, QuadTree, NodeReservation
│   │   ├── robot/                    # RobotState, MotionController (MPC+OSQP)
│   │   ├── behavior/                 # BTCPP v4 engine + action nodes
│   │   ├── network/                  # TCP server, Protocol V1, REST server
│   │   ├── database/                 # MongoDB writer
│   │   └── apps/
│   │       ├── fms_server.cpp        # Main FMS executable
│   │       └── robot_sim.cpp         # Robot simulator executable
│   ├── include/                      # Public headers
│   └── tests/                        # gtest unit tests
│
├── python/                           # ALL Python code
│   ├── app/                          # FastAPI REST API
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models.py
│   │   ├── websocket.py
│   │   └── routes/                   # 34 endpoints
│   ├── intelligence/                 # io-gita + SG (our IP)
│   │   ├── iogita/
│   │   │   ├── zone_identifier.py
│   │   │   ├── cold_start.py
│   │   │   └── fleet_atlas.py
│   │   └── sg_prediction/
│   │       ├── sg_engine.py
│   │       ├── state_encoder.py
│   │       └── bottleneck_predictor.py
│   ├── wes/                          # Warehouse Execution
│   │   ├── order_generator.py
│   │   ├── task_generator.py
│   │   └── kpi_tracker.py
│   ├── monitoring/
│   │   ├── influx_writer.py
│   │   └── redis_cache.py
│   ├── requirements.txt
│   └── tests/                        # pytest
│
├── gazebo/                           # Gazebo simulation
│   ├── plugins/                      # C++ sensor plugins
│   │   ├── lidar_sensor.cpp
│   │   ├── barcode_sensor.cpp
│   │   └── conveyor_belt.cpp
│   ├── worlds/                       # SDF world files
│   ├── models/                       # Robot SDF models
│   └── scripts/
│       └── generate_world.py         # Map JSON → Gazebo SDF
│
├── configs/                          # PLUGGABLE robot + warehouse configs
│   ├── robots/
│   │   ├── differential_drive.yaml   # Generic diff drive AMR
│   │   ├── unidirectional.yaml       # Generic unidirectional AGV
│   │   └── example_custom.yaml       # Template for user's robot
│   ├── warehouses/
│   │   ├── botvalley.json            # Demo warehouse (63 nodes)
│   │   ├── simple_grid.json          # Simple 5x5 grid
│   │   └── example_custom.json       # Template for user's warehouse
│   └── behavior_trees/
│       ├── default_agv.xml           # Generic AGV behavior
│       └── default_amr.xml           # Generic AMR behavior
│
├── frontend/                         # React dashboard
│   └── src/
│
├── docs/                             # Documentation
│   ├── ARCHITECTURE.md
│   ├── GETTING_STARTED.md
│   ├── API_REFERENCE.md
│   ├── CONFIGURATION.md
│   └── CONTRIBUTING.md
│
└── demo/                             # Demo scripts
    ├── cold_start_demo.py
    └── fleet_demo.py
```

---

## Phases (TDD — RED → GREEN → REFACTOR per phase)

### Phase 1: Project Scaffolding + Build System
**Goal:** CMake builds, vcpkg installs deps, Docker compiles, "Hello World" C++ runs.

| Task | Type | Output |
|------|------|--------|
| 1.1 | CMakeLists.txt (top-level + cpp/) | cmake .. builds |
| 1.2 | vcpkg.json manifest | All C++ deps declared |
| 1.3 | Dockerfile (multi-stage: build + runtime) | docker build succeeds |
| 1.4 | docker-compose.yml (all 6 services) | docker compose up works |
| 1.5 | cpp/src/apps/fms_server.cpp "Hello FMS" | Compiles and runs |
| 1.6 | gtest scaffold | cpp/tests/ runs with 0 tests |
| 1.7 | Python scaffold (FastAPI hello) | python/ runs |
| 1.8 | pytest scaffold | python/tests/ runs with 0 tests |

**Kimi Review:** Build system, CMake correctness, Dockerfile reproducibility.

### Phase 2: Core C++ Library
**Goal:** Logging, config loading, threading — the foundation everything uses.

| Task | Type | Output |
|------|------|--------|
| 2.1 | core/Logger (spdlog wrapper) | Structured JSON logging |
| 2.2 | core/Config (YAML loader) | Loads robot + warehouse configs |
| 2.3 | core/ThreadPool | Worker threads for FMS loop |
| 2.4 | core/Timer | High-resolution timing for 15Hz loop |
| 2.5 | core/Types | Pose, Velocity, BatteryState, RobotState |
| 2.6 | Tests for all core modules | gtest, 100% coverage |

**Kimi Review:** C++ code quality, memory safety, thread safety.

### Phase 3: Navigation Engine (C++)
**Goal:** A* pathfinding + ILP node reservation on real warehouse graphs.

| Task | Type | Output |
|------|------|--------|
| 3.1 | navigation/GraphMap (load JSON warehouse) | Nodes, edges, zones |
| 3.2 | navigation/AStar (Manhattan/Euclidean/Chebyshev) | Path + distance + time |
| 3.3 | navigation/QuadTree (spatial indexing) | Nearest node queries |
| 3.4 | navigation/NodeReservation (OSQP-based ILP) | 4 nodes ahead, 12 constraints |
| 3.5 | Tests: A* on BotValley (63 nodes) | Correct paths, <10ms |
| 3.6 | Tests: Node reservation deadlock prevention | No deadlocks in 100 runs |

**Kimi Review:** Algorithm correctness, performance benchmarks, edge cases.

### Phase 4: Robot Control (C++)
**Goal:** Robot state machine + MPC motion controller + battery model.

| Task | Type | Output |
|------|------|--------|
| 4.1 | robot/RobotState (state machine: IDLE→MOVING→CHARGING→...) | Transitions validated |
| 4.2 | robot/MotionController (MPC + OSQP, 12 opt vars) | Velocity commands |
| 4.3 | robot/BatteryModel (charge/discharge curves from YAML) | Exact timing |
| 4.4 | robot/ObstacleHandler (0.7/0.8/1.5m thresholds from YAML) | Stop/slow/replan |
| 4.5 | robot/BarcodeLocalizer (grid tracking, failure detection) | Position + health |
| 4.6 | Tests: state machine transitions | All valid/invalid transitions |
| 4.7 | Tests: MPC solve time <50ms | OSQP benchmarks |
| 4.8 | Tests: battery accuracy to 0.01% | Charge/discharge curves |

**Kimi Review:** State machine completeness, MPC correctness, YAML parameter fidelity.

### Phase 5: Behavior Tree Engine (C++)
**Goal:** BTCPP v4 running real behavior trees for AGV and AMR.

| Task | Type | Output |
|------|------|--------|
| 5.1 | behavior/BTEngine (BTCPP v4 wrapper) | Loads XML, ticks tree |
| 5.2 | behavior/ActionNodes (Move, Dock, Charge, Load, Unload, Reset) | All action codes |
| 5.3 | behavior/ConditionNodes (BatteryLow, TaskAvailable, ObstacleDetected) | Checks |
| 5.4 | configs/behavior_trees/default_agv.xml | Full AGV lifecycle |
| 5.5 | configs/behavior_trees/default_amr.xml | Full AMR lifecycle |
| 5.6 | Tests: BT tick sequences | Correct action order |

**Kimi Review:** BT structure vs real robot lifecycles, action code correctness.

### Phase 6: Communication Layer (C++)
**Goal:** TCP Protocol V1 server + MongoDB writer + REST server.

| Task | Type | Output |
|------|------|--------|
| 6.1 | network/TCPServer (ASIO, port 65123) | Accepts robot connections |
| 6.2 | network/ProtocolV1 (33 fields, pipe-delimited, CRC32) | Parse + serialize |
| 6.3 | database/MongoDBWriter (agents, tasks, events, paths, stats) | Write to MongoDB |
| 6.4 | network/RESTServer (Simple-Web-Server, port 7012) | Basic fleet API |
| 6.5 | Tests: Protocol V1 parse/serialize roundtrip | All 33 fields |
| 6.6 | Tests: MongoDB write + read | All 5 collections |
| 6.7 | Tests: TCP 15Hz sustained throughput | 10 robots × 15Hz = 150 msg/s |

**Kimi Review:** Protocol compliance, MongoDB schema, connection handling.

### Phase 7: Fleet Management Server (C++)
**Goal:** FleetManager ties everything together. 15Hz main loop running.

| Task | Type | Output |
|------|------|--------|
| 7.1 | fleet/FleetManager (15Hz loop: telemetry→allocate→path→reserve→send) | Main loop |
| 7.2 | fleet/TaskManager (FIFO allocator, 9-check validation) | Task lifecycle |
| 7.3 | fleet/COPPController (cooperative path planning) | Multi-robot coordination |
| 7.4 | fleet/AgentInterface (TCP robot communication) | Per-robot state tracking |
| 7.5 | apps/fms_server.cpp (full executable) | Runs standalone |
| 7.6 | Tests: 10 robots, 100 tasks, 0 deadlocks | Stress test |
| 7.7 | Tests: 15Hz loop stays under 67ms budget | Timing test |

**Kimi Review:** Architecture, loop timing, deadlock freedom proof.

### Phase 8: Gazebo Simulation
**Goal:** Physics-accurate warehouse with robots moving.

| Task | Type | Output |
|------|------|--------|
| 8.1 | gazebo/scripts/generate_world.py (map JSON → SDF) | Auto-generate worlds |
| 8.2 | gazebo/models/ (diff drive + unidirectional from YAML) | Robot SDF models |
| 8.3 | gazebo/plugins/lidar_sensor.cpp (360° raycast) | LiDAR data |
| 8.4 | gazebo/plugins/barcode_sensor.cpp | Grid position |
| 8.5 | gazebo/plugins/conveyor_belt.cpp | Belt physics |
| 8.6 | Tests: world loads with 10 robots | Gazebo runs |
| 8.7 | Tests: LiDAR returns valid ranges | Sensor data correct |

**Kimi Review:** SDF correctness, sensor fidelity, real-time factor.

### Phase 9: Python API + Intelligence Layer
**Goal:** FastAPI reads C++ MongoDB state + io-gita + SG prediction.

| Task | Type | Output |
|------|------|--------|
| 9.1 | app/ (FastAPI, 34 endpoints, WebSocket) | REST API |
| 9.2 | intelligence/iogita/ (zone ID, cold start, fleet atlas) | io-gita integration |
| 9.3 | intelligence/sg_prediction/ (state encoder, bottleneck) | SG prediction |
| 9.4 | wes/ (order generator, task generator, KPI) | WES simulation |
| 9.5 | monitoring/ (InfluxDB writer, Redis cache) | Observability |
| 9.6 | Tests: all 34 endpoints return correct shapes | Contract tests |
| 9.7 | Tests: io-gita cold start <2s recovery | Timing test |
| 9.8 | Tests: SG prediction <25ms | Performance test |

**Kimi Review:** API contract compliance, io-gita coupling (must be CORE), SG integration.

### Phase 10: React Dashboard
**Goal:** Live visualization of fleet state.

| Task | Type | Output |
|------|------|--------|
| 10.1 | WarehouseGrid (map nodes, robot positions) | Real-time map |
| 10.2 | RobotStatusPanel + TaskQueue + BatteryLevels | Fleet status |
| 10.3 | IoGitaZones + SGPredictions | Intelligence panels |
| 10.4 | Grafana dashboards (InfluxDB) | A/B SG comparison |
| 10.5 | E2E tests (Playwright) | Dashboard works |

**Kimi Review:** UI functionality, WebSocket real-time updates.

### Phase 11: Integration + Demo
**Goal:** Everything runs together. 10-minute demo.

| Task | Type | Output |
|------|------|--------|
| 11.1 | Integration tests (C++ ↔ MongoDB ↔ Python ↔ Dashboard) | Full pipeline |
| 11.2 | Cold start simulation on BotValley (63 nodes) | 14x speedup proven |
| 11.3 | 14 failure mode / chaos scenarios | All recover |
| 11.4 | 10-minute demo script (4 acts) | Demoable |
| 11.5 | 8-hour stress test (simulated) | Stable |
| 11.6 | Documentation (getting started, API ref, config guide) | Complete docs |

**Kimi Review:** Full system audit, blueprint delta = 0, no dead code.

---

## Dependencies (vcpkg.json)

```json
{
  "name": "robotic-digital-twin",
  "version": "0.1.0",
  "dependencies": [
    "spdlog",
    "fmt",
    "asio",
    "mongo-cxx-driver",
    "rabbitmq-c",
    "rapidjson",
    "eigen3",
    "gtest",
    "osqp",
    "tinyxml2",
    "jsoncpp"
  ]
}
```

Plus BehaviorTree.CPP v4 (FetchContent from GitHub — it's open source).

## Performance Targets

| Metric | Target |
|--------|--------|
| FMS main loop | <67ms (15Hz) |
| A* pathfinding (100 nodes) | <10ms |
| MPC solve (OSQP) | <50ms |
| ILP node reservation | <15ms |
| io-gita zone ID | <1ms |
| Cold start recovery | <2s total |
| SG prediction | <25ms |
| TCP throughput | 150 msg/s (10 robots × 15Hz) |
| REST API p95 | <200ms |
| Dashboard LCP | <2s |

## Success Criteria

1. `docker compose up` → everything runs
2. Load any warehouse JSON + robot YAML → simulation starts
3. Cold start: 14x speedup proven on BotValley
4. SG prediction: catches bottleneck before it happens
5. 10 robots, 0 deadlocks, 8-hour stability
6. Any robotics company can fork and configure in 1 day

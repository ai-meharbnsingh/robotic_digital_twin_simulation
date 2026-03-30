# Robotic Digital Twin Simulation — Project Plan

## Vision
Open source warehouse robotics digital twin. Any robotics company loads their warehouse map + robot YAML config → gets a full simulation with real-time fleet management, task allocation, and warehouse execution.

Written from scratch. C++ where it matters (real-time FMS), Python where it helps (API + monitoring). No proprietary dependencies.

> **Note:** io-gita v1-v3 were dropped. v4 reinstated with hierarchical zone-first approach. See ARCHITECTURE.md for details.

---

## Current Status (All 11 core phases + Phases 1-6 enhancements complete)

Note: "Tests" column shows cumulative count at time of phase completion (historical snapshot).

| Phase | Status | Tests | Key Deliverable |
|-------|--------|-------|-----------------|
| 1. Scaffolding | DONE (88/100 Kimi) | 39 Python | CMake, Docker, FastAPI, configs |
| 2. Core Library | DONE (95/100 Kimi) | 75 C++ | Logger, Timer, Types, Config |
| 3. Navigation | DONE | 150 C++ | A*, GraphMap, QuadTree, NodeReservation |
| 4. Robot Control | DONE | 244 C++ | StateMachine, MPC, Battery, Obstacle |
| 5. Behavior Trees | DONE | 275 C++ | Custom BT engine (tinyxml2), 11 actions |
| 6. Communication | DONE | 319 C++ | TCP Protocol V1 + CRC32, REST server |
| 7. Fleet Manager | DONE | 319 C++ | 15Hz main loop, COPP, TaskManager |
| 8. Gazebo | DONE | 319 C++ | Physics sim, sensor plugins |
| 9. Python API | DONE | 129 Python | 64 endpoints, WES, monitoring, ROS2 |
| 10. Dashboard | DONE | 129 Python | React + Grafana |
| 11. Integration | DONE | 182 Python | Demo, integration tests, docs |

**Total: 390 C++ + 414 Python + 52 Gazebo = 856 tests. Zero failures (32 skipped in sandbox).**

(Test counts updated to include Phases 1-5: order import, mixed fleet, heatmap, waves, 3D contracts + perf, Gazebo plugins)

---

## Architecture (ACTUAL — matches code)

```
┌─────────────────────────────────────────────────────────────────┐
│                    DOCKER (Ubuntu 22.04)                         │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ C++ PROCESS: fms_server (cpp/src/apps/fms_server.cpp)      │ │
│  │                                                            │ │
│  │ rdt_core static library:                                   │ │
│  │ ├── core/    Logger, Timer, Config, Types                  │ │
│  │ ├── navigation/ GraphMap, AStar, QuadTree, NodeReservation │ │
│  │ ├── robot/   RobotState, MotionController, Battery,        │ │
│  │ │            ObstacleHandler                               │ │
│  │ ├── behavior/ BTEngine, ActionNodes, ConditionNodes        │ │
│  │ ├── network/ TCPServer(:65123), RESTServer(:7012),         │ │
│  │ │            ProtocolV1 (33 fields + CRC32)                │ │
│  │ └── fleet/   [Phase 7] FleetManager, TaskManager, COPP    │ │
│  └───────────┬──────���────────────────────────���────────────────┘ │
│              │ JSON file output (fleet_state.json)               │
│  ┌───────────▼────────────────────────────────────────────────┐ │
│  │ PYTHON PROCESS: FastAPI (python/app/main.py :8029)          │ │
│  │ ├── REST API (64 endpoints — reads MongoDB)                 │ │
│  │ ├── WebSocket (/ws/fleet)                                   │ │
│  │ └── [Phase 9] WES OrderGenerator                            │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  [Phase 8] Gazebo: Physics + Sensor Plugins                     │
│  MongoDB:27017 | RabbitMQ:5672 | Redis:6379 | InfluxDB:8086    │
└─────────────────────────────────────────────────────────────────┘
```

## Tech Stack (ACTUAL — what's compiled and tested)

| Component | Language | Library | Status |
|-----------|----------|---------|--------|
| Logger | C++17 | spdlog + fmt | DONE |
| Config | C++17 | yaml-cpp + jsoncpp | DONE |
| Types | C++17 | jsoncpp | DONE |
| Timer | C++17 | std::chrono | DONE |
| A* Pathfinding | C++17 | Custom | DONE |
| QuadTree | C++17 | Custom | DONE |
| Node Reservation | C++17 | Custom (greedy, mutex) | DONE |
| Robot State Machine | C++17 | Custom | DONE |
| Motion Controller | C++17 | Custom (proportional) | DONE |
| Battery Model | C++17 | Custom | DONE |
| Obstacle Handler | C++17 | Custom | DONE |
| Behavior Tree Engine | C++17 | Custom (tinyxml2 parser) | DONE |
| Action Nodes (11) | C++17 | Custom | DONE |
| Condition Nodes (7) | C++17 | Custom | DONE |
| Protocol V1 (33 fields) | C++17 | Custom + CRC32 | DONE |
| TCP Server | C++17 | POSIX sockets | DONE |
| REST Server | C++17 | POSIX sockets | DONE |
| Fleet Manager | C++17 | — | Phase 7 |
| Task Manager | C++17 | — | Phase 7 |
| COPP Controller | C++17 | — | Phase 7 |
| State Writer | C++17 | jsoncpp (JSON file) | DONE |
| FastAPI | Python | FastAPI | DONE (scaffold) |
| Health Checks | Python | Real probes | DONE |
| Pydantic Models | Python | Pydantic v2 | DONE |
| WES (Order/Task/KPI) | Python | Custom (Poisson) | DONE |
| Monitoring | Python | InfluxDB + Redis | DONE |
| Gazebo World | C++ | Gazebo Fortress | DONE |
| React Dashboard | TypeScript | React + Tailwind | DONE |

## vcpkg Dependencies (ACTUAL — in vcpkg.json)

```
spdlog, fmt, asio, eigen3, gtest, osqp, tinyxml2, jsoncpp, yaml-cpp
```

Note: C++ uses JSON file output for state. MongoDB is accessed only from Python via Motor (async driver).

## Repository Structure (ACTUAL — matches filesystem)

```
robotic_digital_twin_simulation/
├── CMakeLists.txt                     # Top-level cmake
├── vcpkg.json                         # vcpkg manifest (9 deps)
├── CLAUDE.md                          # Project rules
├── PROJECT_PLAN.md                    # THIS FILE
├── EXECUTION_PLAN.md                  # Phase-by-phase TODO
├── .env.example                       # Environment variables
├── .gitignore
│
├── cpp/                               # ALL C++ code
│   ├── CMakeLists.txt                 # Builds rdt_core + fms_server + rdt_tests
│   ├── include/rdt/
│   │   ├── version.h
│   │   ├── core/       Logger.h Timer.h Types.h Config.h
│   │   ├── navigation/ GraphMap.h AStar.h QuadTree.h NodeReservation.h
│   │   ├── robot/      RobotState.h MotionController.h BatteryModel.h ObstacleHandler.h
│   │   ├── behavior/   BTEngine.h ActionNodes.h ConditionNodes.h
│   │   └── network/    ProtocolV1.h TCPServer.h RESTServer.h
│   ├── src/
│   │   ├── apps/       fms_server.cpp
│   │   ├── core/       Logger.cpp Timer.cpp Config.cpp
│   │   ├── navigation/ GraphMap.cpp AStar.cpp QuadTree.cpp NodeReservation.cpp
│   │   ├── robot/      RobotState.cpp MotionController.cpp BatteryModel.cpp ObstacleHandler.cpp
│   │   ├── behavior/   BTEngine.cpp ActionNodes.cpp ConditionNodes.cpp
│   │   └── network/    ProtocolV1.cpp TCPServer.cpp RESTServer.cpp
│   └── tests/          15 test files (319 tests)
│
├── python/                            # Python API + intelligence
│   ├── app/            main.py config.py
│   ├── tests/          conftest.py test_config.py test_health.py
│   └── requirements.txt
│
├── configs/                           # PLUGGABLE configs (user edits these)
│   ├── robots/         differential_drive.yaml unidirectional.yaml
│   ├── warehouses/     botvalley.json simple_grid.json
│   └── behavior_trees/ default_agv.xml default_amr.xml
│
├── docker/                            # Container infrastructure
│   ├── Dockerfile      (multi-stage: C++ build + Python runtime)
│   ├── docker-compose.yml (6 services)
│   └── start.sh        (graceful shutdown)
│
├── demo/                              # Demo scripts
│   └── fleet_demo.py                  # Full fleet operations demo (API + standalone)
│
├── docs/                              # Documentation
│   ├── USER_EXPERIENCE.md
│   ├── GETTING_STARTED.md             # 5-minute quickstart
│   ├── API_REFERENCE.md               # All 64 endpoints with curl examples
│   ├── CONFIGURATION.md               # Warehouse, robot, BT customization guide
│   └── ARCHITECTURE.md                # System diagram, data flow, tech stack
│
├── gazebo/             [Phase 8]
└── frontend/           [Phase 10]
```

## Performance Targets

| Metric | Target | Proven? |
|--------|--------|---------|
| FMS main loop | <67ms (15Hz) | Timer tested at 15Hz ✓ |
| A* pathfinding (63 nodes) | <10ms | Tested <10ms ✓ |
| MPC solve | <50ms | Proportional controller (Phase 4), MPC upgrade Phase 7 |
| Node reservation | <15ms | Tested <15ms for 10 robots ✓ |
| TCP throughput | 150 msg/s | Phase 7 integration test |
| Protocol V1 parse | <0.1ms | Tested ✓ |
| REST API p95 | <200ms | Proven via test suite ✓ |

## What's NOT in this project

- No Addverb proprietary code — everything written from scratch
- No ROS2/Nav2 — custom navigation stack
- No AMCL — barcode grid navigation
- No proprietary dependencies — all open source
- No GUI compilation needed by end user — Docker handles everything

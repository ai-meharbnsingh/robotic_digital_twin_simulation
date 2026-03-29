# Architecture

## System Diagram

The simulation runs as three primary processes plus supporting infrastructure services, all orchestrated by Docker Compose.

```
                              DOCKER (python:3.11-slim + ubuntu:22.04 builder)
  ┌─────────────────────────────────────────────────────────────────────┐
  │                                                                     │
  │  ┌──────────────────────────────────────────────────────────────┐  │
  │  │  C++ PROCESS: fms_server                                     │  │
  │  │  Ports: :65123 (TCP), :7012 (REST)                           │  │
  │  │                                                              │  │
  │  │  rdt_core static library (C++17, -Wall -Wextra -Wpedantic):  │  │
  │  │  ├── core/        Logger, Timer, Config, Types               │  │
  │  │  ├── navigation/  GraphMap, A*, QuadTree, NodeReservation    │  │
  │  │  ├── robot/       StateMachine, MotionController, Battery    │  │
  │  │  ├── behavior/    BTEngine, ActionNodes, ConditionNodes      │  │
  │  │  ├── network/     TCPServer, RESTServer, ProtocolV1          │  │
  │  │  └── fleet/       FleetManager, TaskManager, COPP, Agent     │  │
  │  └──────────┬─────────────────────────────────────────────┬─────┘  │
  │             │  TCP (:65123)               JSON file output │        │
  │             │  Protocol V1               (fleet_state.json)│        │
  │             ▼                                              │        │
  │   ┌──────────────┐                                         │        │
  │   │  Simulated   │                         C++ REST :7012  │        │
  │   │  Robots      │                         (fleet status)  │        │
  │   │  (or Gazebo) │                                         │        │
  │   └──────────────┘                                         │        │
  │                                                            │        │
  │  ┌─────────────────────────────────────────────────────────▼─────┐  │
  │  │  PYTHON PROCESS: FastAPI (:8029)                              │  │
  │  │                                                               │  │
  │  │  ├── REST API (30 endpoints)                                  │  │
  │  │  ├── WebSocket (/ws/fleet) — 100 connection limit             │  │
  │  │  ├── API Key Auth (X-API-Key header on write endpoints)       │  │
  │  │  ├── CORS (configurable via CORS_ORIGINS env var)             │  │
  │  │  ├── WES (Warehouse Execution System)                         │  │
  │  │  │   ├── OrderGenerator (Poisson arrival)                     │  │
  │  │  │   ├── TaskGenerator (orders → tasks)                       │  │
  │  │  │   └── KPITracker (throughput metrics)                      │  │
  │  │  └── Monitoring                                               │  │
  │  │      ├── InfluxWriter (time-series telemetry)                 │  │
  │  │      └── RedisCache (real-time positions)                     │  │
  │  └──────────────────────────────────────────────────────────────┘  │
  │                                                                     │
  │  ┌──────────────────────────────────────────────────────────────┐  │
  │  │  REACT DASHBOARD (served at /dashboard by FastAPI)           │  │
  │  │  TypeScript + Vite + Tailwind, WebSocket live updates        │  │
  │  └──────────────────────────────────────────────────────────────┘  │
  │                                                                     │
  │  ┌───────────────────────────────────────────────────────────────┐  │
  │  │  INFRASTRUCTURE (all with auth, ports bound to 127.0.0.1)    │  │
  │  │  MongoDB :27017  │  RabbitMQ :5672  │  Redis :6379            │  │
  │  │  InfluxDB :8086  │  Grafana :3000                             │  │
  │  └───────────────────────────────────────────────────────────────┘  │
  └─────────────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. Robot State (C++ → JSON → Python → Dashboard)

```
Simulated Robot
    │  TCP Protocol V1 (33 fields + CRC32) at 15Hz
    ▼
C++ TCPServer (:65123)
    │  Parse ProtocolV1 message
    ▼
C++ FleetManager
    │  Update robot state, run A* pathfinding, tick behavior trees
    │  Write state to JSON file (fleet_state.json) each cycle
    │  Expose state via REST (:7012)
    ▼
Python FastAPI reads from MongoDB (populated via API calls)
    │
    ├──► REST: GET /api/robots, GET /api/fleet/status
    │       └──► JSON response to client
    │
    └──► WebSocket (/ws/fleet)
            └──► Real-time push to React dashboard
```

**Note:** C++ writes JSON files, not directly to MongoDB. The Python API is the MongoDB owner. This was an intentional architecture simplification — decoupling C++ from MongoDB driver complexity. The C++ REST server at :7012 provides fleet state for any consumer.

### 2. Task Lifecycle

```
REST API: POST /api/tasks (X-API-Key required)
    │  Create task in MongoDB
    ▼
MongoDB "tasks" collection
    │
    ├──► C++ TaskManager (reads pending tasks via REST)
    │       │  Assign to nearest available robot
    │       ▼
    │   C++ FleetManager (plan path, set behavior tree)
    │       │  Robot executes: move → pick → move → drop
    │       ▼
    │   Task completion reported via REST
    │
    └──► Python WebSocket (broadcast task_update event)
```

## Dropped: Intelligence Pipeline (io-gita)

The io-gita intelligence layer was **dropped in Session 6** after the cold start localization experiment failed (52% accuracy, below 75% gate). The following components were archived:

- ZoneIdentifier (Hopfield ODE + graph disambiguation)
- ColdStartRecovery (state persistence + recovery hints)
- FleetAtlas (zone occupation tracking)
- SG BottleneckPredictor (fleet state pattern matching)

All code is preserved in `_archive/io_gita_dropped/`. Closure documented in `COLD_START_CLOSED.md`.

The digital twin is fully functional without the intelligence layer. Zone identification and predictive analytics can be re-added in a future milestone.

## Technology Stack

| Layer | Component | Technology | Purpose |
|-------|-----------|------------|---------|
| **C++ Core** | FMS Server | C++17, CMake, vcpkg | Real-time fleet management at 15Hz |
| | Navigation | Custom A*, QuadTree | Pathfinding on warehouse graph |
| | Robot Control | Custom state machine | MPC motion control, battery management |
| | Behavior Trees | Custom engine (tinyxml2) | Decision logic (11 action + 7 condition nodes) |
| | Protocol | Custom V1 (33 fields + CRC32) | TCP communication with robots |
| | Network | POSIX sockets | TCP server + REST server (thread-safe) |
| **Python API** | REST API | FastAPI, Pydantic v2 | 30 endpoints for fleet data |
| | WebSocket | FastAPI WebSocket | Real-time fleet event streaming (100 conn limit) |
| | Auth | API Key (X-API-Key header) | Write endpoint protection (configurable) |
| | CORS | CORSMiddleware | Configurable origins via CORS_ORIGINS env var |
| | WES | Custom (Poisson generator) | Order generation, task management, KPIs |
| | Monitoring | InfluxDB client, Redis | Time-series telemetry, position cache |
| **Frontend** | Dashboard | React 19, TypeScript, Vite | Live fleet visualization |
| **Simulation** | Gazebo | gz-sim7 (Fortress) | 3D warehouse with LiDAR, barcode, conveyor plugins |
| **Infrastructure** | Database | MongoDB 7 (with auth) | Fleet state storage |
| | Message Broker | RabbitMQ 3 (with auth) | Task queue and event bus |
| | Cache | Redis 7 (with auth) | Real-time robot position cache |
| | Time-Series | InfluxDB 2 (with auth) | Telemetry storage |
| | Dashboards | Grafana | Visual monitoring |
| **Build** | C++ | CMake + vcpkg | Cross-platform build |
| | Frontend | Node.js 20 + npm | React build (Dockerfile stage 2) |
| | Container | Docker 3-stage | C++ builder + frontend builder + runtime |
| | Orchestration | Docker Compose | 6-service stack with health checks + auth |

## Performance Targets

| Metric | Target | Status |
|--------|--------|--------|
| FMS main loop | <67ms (15Hz) | Tested |
| A* pathfinding (63 nodes) | <10ms | Tested |
| Node reservation (10 robots) | <15ms | Tested |
| Protocol V1 parse | <0.1ms | Tested |
| TCP throughput | 150 msg/s | Target |
| REST API p95 | <200ms | Target |

## Repository Structure

```
robotic_digital_twin_simulation/
├── CMakeLists.txt                # Top-level CMake
├── vcpkg.json                    # C++ dependency manifest
├── CLAUDE.md                     # Project rules
├── EXECUTION_PLAN.md             # Phase-by-phase tasks (honest status)
├── .env.example                  # Environment variables template
│
├── cpp/                          # ALL C++ code
│   ├── CMakeLists.txt            # Builds rdt_core + fms_server + tests (-Wall -Wextra)
│   ├── include/rdt/              # Headers
│   │   ├── core/                 # Logger, Timer, Config, Types
│   │   ├── navigation/           # GraphMap, AStar, QuadTree, NodeReservation
│   │   ├── robot/                # RobotState, MotionController, Battery, Obstacle
│   │   ├── behavior/             # BTEngine, ActionNodes, ConditionNodes
│   │   ├── network/              # ProtocolV1, TCPServer, RESTServer
│   │   └── fleet/                # FleetManager, TaskManager, COPP, AgentInterface
│   ├── src/                      # Implementation files
│   └── tests/                    # 18 test files (352 C++ tests)
│
├── python/                       # Python API
│   ├── app/                      # FastAPI application
│   │   ├── main.py               # App entry point, lifespan, health, CORS
│   │   ├── config.py             # Settings + config loaders
│   │   ├── auth.py               # API key auth for write endpoints
│   │   ├── websocket.py          # WebSocket manager (100 conn limit + origin check)
│   │   └── routes/               # 13 route modules (30 endpoints)
│   ├── wes/                      # Warehouse Execution System
│   ├── monitoring/               # InfluxDB writer, Redis cache
│   └── tests/                    # Python test suite (124 tests)
│
├── configs/                      # Pluggable configuration files
│   ├── warehouses/               # JSON warehouse maps (simple_grid, botvalley)
│   ├── robots/                   # YAML robot presets (differential_drive, unidirectional)
│   └── behavior_trees/           # XML behavior tree definitions
│
├── docker/                       # Container infrastructure
│   ├── Dockerfile                # 3-stage: C++ build + frontend build + runtime
│   ├── docker-compose.yml        # 6 services with auth (secrets via .env)
│   ├── .env.docker.example       # Docker secrets template
│   └── start.sh                  # Process launcher with graceful shutdown
│
├── frontend/                     # React dashboard (TypeScript + Vite)
│   └── src/                      # Components, hooks, types
│
├── gazebo/                       # Gazebo simulation
│   ├── scripts/                  # generate_world.py, generate_robot.py
│   ├── plugins/                  # lidar_sensor, barcode_sensor, conveyor_belt
│   ├── models/                   # SDF robot models
│   └── tests/                    # 52 Gazebo tests
│
├── demo/                         # Demo scripts
│   └── fleet_demo.py             # Full fleet operations demo
│
├── docs/                         # Documentation
│   ├── GETTING_STARTED.md        # 5-minute quickstart
│   ├── API_REFERENCE.md          # All 30 endpoints
│   ├── CONFIGURATION.md          # Customization guide
│   ├── ARCHITECTURE.md           # This file
│   └── USER_EXPERIENCE.md        # UX design notes
│
└── _archive/                     # Archived code (not in git)
    └── io_gita_dropped/          # Dropped intelligence layer (52% accuracy)
```

## Design Decisions

### Why C++ for FMS?

The Fleet Management Server must run at 15Hz (67ms per tick) with 10 robots, performing A* pathfinding, collision detection, behavior tree execution, and TCP communication in each tick. Python cannot meet this timing budget for real-time control loops.

### Why Python for API?

FastAPI provides automatic OpenAPI docs, WebSocket support, async MongoDB queries, and rapid development. The WES and monitoring layers benefit from Python's ecosystem.

### Why JSON file IPC (not direct MongoDB from C++)?

Originally planned as C++ writing directly to MongoDB (MongoDBWriter). This was dropped in favor of JSON file output because:
1. MongoDB C++ driver adds significant build complexity (mongocxx, bsoncxx, boost)
2. The Python API already owns the MongoDB connection via Motor
3. JSON file output is simpler and debuggable
4. The C++ REST server at :7012 provides the same data for programmatic access

### Why io-gita was dropped

io-gita (Hopfield ODE zone identification + cold start recovery) was implemented across Phases 9-12. The cold start localization experiment achieved only 52% accuracy with 3D LiDAR, well below the 75% gate. After 4 experiment scripts and a formal RCA, the entire intelligence layer was archived. The digital twin is complete and functional without it. See `COLD_START_CLOSED.md` for the full closure report.

### Why Pluggable Configs?

The goal is for any robotics company to use this simulation by providing their warehouse map (JSON) and robot specs (YAML). No code changes needed:
- Set `WAREHOUSE_CONFIG=my_warehouse` and `ROBOT_CONFIG=my_robot` env vars
- Drop files in `configs/warehouses/` and `configs/robots/`
- Run `docker compose up --build`

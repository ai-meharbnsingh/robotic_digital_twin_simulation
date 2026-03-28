# Architecture

## System Diagram

The simulation runs as three primary processes plus supporting infrastructure services, all orchestrated by Docker Compose.

```
                              DOCKER (Ubuntu 22.04)
  ┌─────────────────────────────────────────────────────────────────────┐
  │                                                                     │
  │  ┌──────────────────────────────────────────────────────────────┐  │
  │  │  C++ PROCESS: fms_server                                     │  │
  │  │  Ports: :65123 (TCP), :7012 (REST)                           │  │
  │  │                                                              │  │
  │  │  rdt_core static library (C++17):                            │  │
  │  │  ├── core/        Logger, Timer, Config, Types               │  │
  │  │  ├── navigation/  GraphMap, A*, QuadTree, NodeReservation    │  │
  │  │  ├── robot/       StateMachine, MotionController, Battery    │  │
  │  │  ├── behavior/    BTEngine, ActionNodes, ConditionNodes      │  │
  │  │  ├── network/     TCPServer, RESTServer, ProtocolV1          │  │
  │  │  └── fleet/       FleetManager, TaskManager, COPP            │  │
  │  └──────────┬─────────────────────────────────────────────┬─────┘  │
  │             │  TCP (:65123)               JSON file output │        │
  │             │  Protocol V1               (fleet_state.json)│        │
  │             ▼                                              ▼        │
  │   ┌──────────────┐                            ┌──────────────┐     │
  │   │  Simulated   │                            │   MongoDB    │     │
  │   │  Robots      │                            │   :27017     │     │
  │   │  (or Gazebo) │                            │              │     │
  │   └──────────────┘                            └──────┬───────┘     │
  │                                                      │ Reads       │
  │  ┌───────────────────────────────────────────────────▼──────────┐  │
  │  │  PYTHON PROCESS: FastAPI (:8029)                             │  │
  │  │                                                              │  │
  │  │  ├── REST API (34 endpoints)                                 │  │
  │  │  ├── WebSocket (/ws/fleet)                                   │  │
  │  │  ├── Intelligence Layer                                      │  │
  │  │  │   ├── io-gita ZoneIdentifier (Hopfield / sg_engine)      │  │
  │  │  │   ├── io-gita ColdStartRecovery                          │  │
  │  │  │   ├── io-gita FleetAtlas                                  │  │
  │  │  │   └── SG BottleneckPredictor                              │  │
  │  │  ├── WES (Warehouse Execution System)                        │  │
  │  │  │   ├── OrderGenerator (Poisson arrival)                    │  │
  │  │  │   ├── TaskGenerator                                       │  │
  │  │  │   └── KPITracker                                          │  │
  │  │  └── Monitoring                                              │  │
  │  │      ├── InfluxWriter (time-series telemetry)                │  │
  │  │      └── RedisCache (real-time positions)                    │  │
  │  └──────────────────────────────────────────────────────────────┘  │
  │                                                                     │
  │  ┌───────────────────────────────────────────────────────────────┐  │
  │  │  INFRASTRUCTURE SERVICES                                      │  │
  │  │  MongoDB :27017  │  RabbitMQ :5672  │  Redis :6379            │  │
  │  │  InfluxDB :8086  │  Grafana :3000                             │  │
  │  └───────────────────────────────────────────────────────────────┘  │
  └─────────────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. Robot State (C++ -> MongoDB -> Python -> Dashboard)

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
    ▼
MongoDB "robots" collection (populated by Python API from FMS REST)
    │
    ├──► Python FastAPI (REST: GET /api/robots)
    ��       └──► JSON response to client
    │
    └──► Python WebSocket (/ws/fleet)
            └──► Real-time push to dashboard
```

### 2. Task Lifecycle

```
REST API: POST /api/tasks
    │  Create task in MongoDB
    ▼
MongoDB "tasks" collection
    │
    ├──► C++ TaskManager (reads pending tasks)
    │       │  Assign to nearest available robot
    │       ▼
    │   C++ FleetManager (plan path, set behavior tree)
    │       │  Robot executes: move → pick → move → drop
    │       ▼
    │   MongoDB update (status: completed)
    │
    └──► Python WebSocket (broadcast task_update event)
```

### 3. Intelligence Pipeline

```
MongoDB "robots" collection (current robot positions)
    │
    ▼
io-gita ZoneIdentifier
    │  Classify each robot into a warehouse zone (<1ms)
    ▼
io-gita FleetAtlas
    │  Aggregate zone occupation, detect transitions
    ▼
SG BottleneckPredictor
    │  Encode fleet state → Hopfield attractor landscape
    │  Predict: congestion, battery cascade, deadlock risk
    ▼
REST API: GET /api/analytics/predictions
WebSocket: sg_prediction event
```

### 4. Cold Start Recovery

```
Robot power-cycles / crashes
    │
    ▼
POST /api/iogita/cold-start/{robot_id}
    │
    ├──► io-gita ZoneIdentifier: identify zone from (x,y) (<1ms)
    │
    ├──► ColdStartRecovery: load last saved state
    │       Generate recovery hints:
    │       1. Restore position
    │       2. Localize to nearest node
    │       3. Check battery (charge if <20%)
    │       4. Resume interrupted task
    │
    └──► Return hints to caller (total <2ms)
```

## Technology Stack

| Layer | Component | Technology | Purpose |
|-------|-----------|------------|---------|
| **C++ Core** | FMS Server | C++17, CMake, vcpkg | Real-time fleet management at 15Hz |
| | Navigation | Custom A*, QuadTree | Pathfinding on warehouse graph |
| | Robot Control | Custom state machine | MPC motion control, battery management |
| | Behavior Trees | Custom engine (tinyxml2) | Decision logic (11 action + 7 condition nodes) |
| | Protocol | Custom V1 (33 fields + CRC32) | TCP communication with robots |
| | Network | POSIX sockets, ASIO | TCP server + REST server |
| **Python API** | REST API | FastAPI, Pydantic v2 | 34 endpoints for fleet data + intelligence |
| | WebSocket | FastAPI WebSocket | Real-time fleet event streaming |
| | Intelligence | io-gita (Hopfield network) | Zone identification (<1ms), cold start recovery |
| | SG Prediction | Custom (Hopfield attractor) | Bottleneck prediction 2-5 min in advance |
| | WES | Custom (Poisson generator) | Order generation, task management, KPIs |
| | Monitoring | InfluxDB client, Redis | Time-series telemetry, position cache |
| **Infrastructure** | Database | MongoDB 7 | State IPC between C++ and Python |
| | Message Broker | RabbitMQ 3 | Task queue and event bus |
| | Cache | Redis 7 | Real-time robot position cache |
| | Time-Series | InfluxDB 2 | Telemetry storage (battery, velocity, etc.) |
| | Dashboards | Grafana | Visual monitoring and alerting |
| **Build** | C++ | CMake + vcpkg | Cross-platform build with dependency management |
| | Python | pip + requirements.txt | Python package management |
| | Container | Docker multi-stage | C++ build stage + Python runtime stage |
| | Orchestration | Docker Compose | 6-service stack with health checks |

## Performance Targets

| Metric | Target | Proven? |
|--------|--------|---------|
| FMS main loop | <67ms (15Hz) | Timer tested at 15Hz |
| A* pathfinding (63 nodes) | <10ms | Tested <10ms |
| MPC solve | <50ms | Proportional controller |
| Node reservation (10 robots) | <15ms | Tested <15ms |
| io-gita zone identification | <1ms | Tested <1ms |
| Cold start recovery | <2s | Tested <2ms typical |
| SG prediction | <25ms | Tested <25ms |
| Protocol V1 parse | <0.1ms | Tested |
| TCP throughput | 150 msg/s | Phase 7 target |
| REST API p95 | <200ms | Phase 9 target |

## Repository Structure

```
robotic_digital_twin_simulation/
├── CMakeLists.txt                # Top-level CMake
├── vcpkg.json                    # C++ dependency manifest
├── CLAUDE.md                     # Project rules
├── PROJECT_PLAN.md               # Project plan + status
├── EXECUTION_PLAN.md             # Phase-by-phase tasks
├── .env.example                  # Environment variables template
│
├── cpp/                          # ALL C++ code
│   ├── CMakeLists.txt            # Builds rdt_core + fms_server + tests
│   ├── include/rdt/              # Headers
│   │   ├── core/                 # Logger, Timer, Config, Types
│   │   ├── navigation/           # GraphMap, AStar, QuadTree, NodeReservation
│   │   ├── robot/                # RobotState, MotionController, Battery, Obstacle
│   │   ├── behavior/             # BTEngine, ActionNodes, ConditionNodes
│   │   └── network/              # ProtocolV1, TCPServer, RESTServer
│   ├── src/                      # Implementation files
│   └── tests/                    # 15 test files (319 C++ tests)
│
├── python/                       # Python API + Intelligence
│   ├── app/                      # FastAPI application
│   │   ├── main.py               # App entry point, lifespan, health
│   │   ├── config.py             # Settings + config loaders
│   │   ├── models.py             # Pydantic data models
│   │   ├── websocket.py          # WebSocket manager
│   │   └── routes/               # 14 route modules (34 endpoints)
│   ├── intelligence/             # io-gita + SG prediction
│   │   ├── iogita/               # ZoneIdentifier, ColdStart, FleetAtlas
│   │   └── sg_prediction/        # StateEncoder, SGEngine, BottleneckPredictor
│   ├── wes/                      # Warehouse Execution System
│   ├── monitoring/               # InfluxDB writer, Redis cache
│   └── tests/                    # Python test suite
│
├── configs/                      # Pluggable configuration files
│   ├── warehouses/               # JSON warehouse maps
│   ├── robots/                   # YAML robot presets
│   └── behavior_trees/           # XML behavior tree definitions
│
├── docker/                       # Container infrastructure
│   ├── Dockerfile                # Multi-stage: C++ build + Python runtime
│   ├── docker-compose.yml        # 6-service stack
│   └── start.sh                  # Process launcher with graceful shutdown
│
├── demo/                         # Demo scripts
│   ├── cold_start_demo.py        # io-gita cold start demonstration
│   └── fleet_demo.py             # Full fleet operations demo
│
├── docs/                         # Documentation
│   ├── GETTING_STARTED.md        # 5-minute quickstart
│   ├── API_REFERENCE.md          # All 34 endpoints
│   ├── CONFIGURATION.md          # Customization guide
│   ├── ARCHITECTURE.md           # This file
│   └── USER_EXPERIENCE.md        # UX design notes
│
├── gazebo/                       # Gazebo simulation (Phase 8)
└── frontend/                     # React dashboard (Phase 10)
```

## Design Decisions

### Why C++ for FMS?

The Fleet Management Server must run at 15Hz (67ms per tick) with 10 robots, performing A* pathfinding, collision detection, behavior tree execution, and TCP communication in each tick. Python cannot meet this timing budget for real-time control loops.

### Why Python for API?

FastAPI provides automatic OpenAPI docs, WebSocket support, async MongoDB queries, and rapid development. The intelligence layer (io-gita, SG prediction) uses NumPy and benefits from Python's scientific computing ecosystem.

### Why MongoDB for IPC?

MongoDB serves as the shared state between C++ and Python processes. The C++ FMS writes robot states, and the Python API reads them. This decouples the two processes and allows independent scaling. Motor (async MongoDB driver) provides non-blocking reads in FastAPI.

### Why Pluggable Configs?

The goal is for any robotics company to use this simulation by providing their warehouse map (JSON) and robot specs (YAML). No code changes should be needed for basic customization.

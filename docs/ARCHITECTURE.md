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
  │  │  ├── REST API (116 endpoints)                                  │  │
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
  │  │  InfluxDB :8086  │  Grafana :3000   │  Mosquitto :1883/:9001  │  │
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

## Intelligence Pipeline (io-gita v4 — Reinstated)

io-gita v1-v3 were **dropped in Session 6** after cold start localization failed (52% accuracy with 3D LiDAR, below 75% gate). The original approach used 16-feature LiDAR extraction which was too similar between zones.

**v4 was reinstated** with a hierarchical zone-first approach:
- ZoneIdentifier v4: geometry-only zone features (12-dim) + zone-first hierarchy → >90% zone accuracy
- ColdStartRecovery: state persistence + recovery hints (3 endpoints)
- Backend: `hierarchical_hopfield_d10000`

v1-v3 code is preserved in `_archive/io_gita_dropped/`. Closure documented in `COLD_START_CLOSED.md`.

4 REST endpoints: `GET /api/iogita/status`, `GET /api/iogita/zones`, `POST /api/iogita/cold-start/{id}`, `POST /api/iogita/recover/{id}`

## Phases 1-5 Enhancements (v2.0)

### Phase 1: CSV/Excel Order Import
- `POST /api/wes/orders/import` — multipart CSV upload
- Row-by-row validation, OWASP CSV injection protection, MAX_FILE_SIZE/MAX_ROWS limits

### Phase 2: Mixed Fleet Types
- Fleet manifest: `configs/fleets/default_mixed.json`
- C++ `--fleet` flag loads heterogeneous robots (AMR + AGV) with different configs
- Dashboard color-codes robots by type

### Phase 3: Heat Map Visualization
- `GET /api/analytics/heatmap` — grid-based traffic density over time window
- Frontend: semi-transparent color overlay (green→yellow→red) on WarehouseGrid
- Zone congestion scoring

### Phase 4: Wave Rule Engine (Advanced WES)
- WaveEngine: group orders into waves for batch picking
- 5 REST endpoints: waves CRUD, rules CRUD, wave release
- Rules persist in MongoDB, loaded on startup

### Phase 5: 3D Web Simulation (React Three Fiber)
- Browser-based 3D warehouse visualization — no Gazebo required
- React Three Fiber + drei: auto-generated 3D scene from warehouse JSON config
- Shared geometry pools (1 per type, reused by all instances) for 50+ robot scalability
- Dual update path: REST polling (3s) for full state + WebSocket for low-latency position updates
- WS events bypass React re-renders (ref callback pattern → useFrame interpolation)
- Lazy-loaded: Three.js chunk (~918KB) loads only when 3D tab clicked
- Camera orbit/pan/zoom + follow-robot mode
- Heat map overlay in 3D (merged vertex-colored floor geometry)
- Battery color bars, direction cones, path lines, selection rings on robot models

## Phase 8: VDA5050 Gateway (MQTT + Standard AGV Protocol)

VDA5050 v2.0 is the open European standard for AGV/AMR communication. Phase 8 adds a VDA5050 Gateway that bridges the internal C++ FMS protocol to the industry-standard MQTT-based VDA5050 message format.

### Infrastructure

Eclipse Mosquitto MQTT broker runs as a Docker Compose service:
- Port 1883: MQTT (TCP) for robot-to-gateway communication
- Port 9001: WebSocket for browser-based monitoring tools
- Health-checked and auto-started before the main application

### VDA5050 Topic Structure

All topics follow the VDA5050 v2.0 namespace:
```
{interfaceName}/{version}/{manufacturer}/{serialNumber}/{topic}
```

Example for robot AMR-001:
```
uagv/v2/RDT/AMR-001/order          ← Master Control → AGV (orders)
uagv/v2/RDT/AMR-001/instantActions  ← Master Control → AGV (e-stop, cancel)
uagv/v2/RDT/AMR-001/state           ← AGV → Master Control (robot state at 1-10Hz)
uagv/v2/RDT/AMR-001/visualization   ← AGV → Master Control (position updates)
uagv/v2/RDT/AMR-001/connection      ← AGV → Broker (online/offline/connectionBroken)
uagv/v2/RDT/AMR-001/factsheet       ← AGV → Master Control (capabilities)
```

### Message Flow

```
                    MQTT Broker (Mosquitto :1883)
                         │
    ┌────────────────────┼────────────────────┐
    │                    │                    │
    ▼                    ▼                    ▼
VDA5050 Gateway    Third-party tools    Browser monitor
(Python service)   (any VDA5050 client)  (WS :9001)
    │
    ▼
C++ FMS (via REST :7012 / internal API)
    │
    ▼
Robot fleet (TCP :65123)
```

The gateway translates between:
- **Inbound:** VDA5050 JSON orders/instantActions → internal FMS task format
- **Outbound:** Internal robot state → VDA5050 state/visualization/connection messages

### Conformance Testing

Golden JSON fixtures in `python/tests/fixtures/vda5050/` provide reference messages for conformance testing:
- `order_simple.json` — 3-node pick→shelf→drop order
- `order_complex.json` — 5-node order with actions at each node
- `state_moving.json` — Robot moving along edge with load and battery state
- `state_idle.json` — Robot idle awaiting orders
- `instant_action_estop.json` — Emergency stop command
- `instant_action_cancel.json` — Cancel order command
- `connection_online.json` — AGV online announcement
- `factsheet_amr.json` — AMR capabilities and protocol limits

All fixtures follow VDA5050 v2.0 schema and are used by `test_vda5050.py` for schema validation, topic construction, and message translation correctness.

## Phase 10: ROS2 Bridge (Simulated + Production-Ready)

The ROS2 Bridge provides bidirectional communication between the FMS REST API and ROS2 nav2 stack. Locally, it runs in **simulated mode** (no rclpy required). In Docker with `ros:humble` base image, it connects to real ROS2 topics.

### Components

- **ROS2Bridge** (`python/ros2_bridge/bridge.py`): Core bridge with nav goal, pose, scan, e-stop
- **TopicMapper** (`python/ros2_bridge/topic_mapper.py`): Bidirectional FMS <-> ROS2 topic translation
- **HAL** (`python/ros2_bridge/hal.py`): Hardware Abstraction Layer (SIMULATED / ROS2_SIM / ROS2_REAL modes)
- **REST Endpoints** (`python/app/routes/ros2.py`): 4 endpoints with input validation and rate limiting

### Input Validation

All `robot_id` parameters are validated by `sanitize_robot_id()` before use in topic names. This prevents ROS2 topic injection attacks. The validation rejects: `/`, `#`, `+`, `..`, whitespace, and IDs over 50 characters. Only alphanumeric characters, dashes, underscores, and dots are allowed. This follows the same pattern as VDA5050's `sanitize_topic_component()`.

### Rate Limiting

Navigation goals are rate-limited to 100 per robot per minute (sliding window) to prevent resource exhaustion.

### ROS2 Security Best Practices (Production Deployment)

When deploying with real ROS2 hardware, the following security measures are recommended:

1. **ROS_DOMAIN_ID Isolation**: Set a unique `ROS_DOMAIN_ID` (0-232) for the fleet to isolate DDS discovery from other ROS2 systems on the same network. Each isolated environment (dev, staging, production) should use a different domain ID.

2. **SROS2 Encrypted Topics**: Enable SROS2 (Secure ROS2) for encrypted and authenticated DDS communication. This uses DDS Security with X.509 certificates for:
   - Authentication (mutual TLS between nodes)
   - Access control (per-topic publish/subscribe permissions)
   - Encryption (AES-GCM for topic data in transit)

   Generate security keys with: `ros2 security create_keystore`, `ros2 security create_enclave`

3. **Dedicated VLAN for Robot Network**: Place all robot-to-FMS communication on a dedicated VLAN (e.g., VLAN 100) with:
   - Firewall rules restricting DDS multicast traffic to the robot VLAN only
   - No direct internet access from the robot network
   - VPN or SSH tunnel for remote monitoring access
   - MAC address filtering for robot network interfaces

4. **DDS Discovery Restriction**: Use `FASTDDS_DISCOVERY_SERVER` or `RMW_IMPLEMENTATION=rmw_cyclonedds_cpp` with unicast peer lists instead of multicast discovery to prevent unauthorized node joins.

## Technology Stack

| Layer | Component | Technology | Purpose |
|-------|-----------|------------|---------|
| **C++ Core** | FMS Server | C++17, CMake, vcpkg | Real-time fleet management at 15Hz |
| | Navigation | Custom A*, QuadTree | Pathfinding on warehouse graph |
| | Robot Control | Custom state machine | MPC motion control, battery management |
| | Behavior Trees | Custom engine (tinyxml2) | Decision logic (11 action + 7 condition nodes) |
| | Protocol | Custom V1 (33 fields + CRC32) | TCP communication with robots |
| | Network | POSIX sockets | TCP server + REST server (thread-safe) |
| **Python API** | REST API | FastAPI, Pydantic v2 | 116 endpoints for fleet data |
| | WebSocket | FastAPI WebSocket | Real-time fleet event streaming (100 conn limit) |
| | Auth | API Key (X-API-Key header) | Write endpoint protection (configurable) |
| | CORS | CORSMiddleware | Configurable origins via CORS_ORIGINS env var |
| | WES | Custom (Poisson generator) | Order generation, task management, KPIs |
| | Monitoring | InfluxDB client, Redis | Time-series telemetry, position cache |
| **Frontend** | Dashboard | React 19, TypeScript, Vite | Live fleet visualization (2D + 3D) |
| | 3D Scene | React Three Fiber, drei, Three.js | Browser-based 3D warehouse sim |
| **Simulation** | Gazebo | gz-sim7 (Fortress) | 3D warehouse with LiDAR, barcode, conveyor plugins |
| **Infrastructure** | Database | MongoDB 7 (with auth) | Fleet state storage |
| | Message Broker | RabbitMQ 3 (with auth) | Task queue and event bus |
| | MQTT Broker | Eclipse Mosquitto 2 | VDA5050 AGV communication (TCP :1883 + WS :9001) |
| | Cache | Redis 7 (with auth) | Real-time robot position cache |
| | Time-Series | InfluxDB 2 (with auth) | Telemetry storage |
| | Dashboards | Grafana | Visual monitoring |
| **Build** | C++ | CMake + vcpkg | Cross-platform build |
| | Frontend | Node.js 20 + npm | React build (Dockerfile stage 2) |
| | Container | Docker 3-stage | C++ builder + frontend builder + runtime |
| | Orchestration | Docker Compose | 7-service stack with health checks + auth |

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
│   └── tests/                    # 18 test files (398 C++ tests)
│
├── python/                       # Python API
│   ├── app/                      # FastAPI application
│   │   ├── main.py               # App entry point, lifespan, health, CORS
│   │   ├── config.py             # Settings + config loaders
│   │   ├── auth.py               # API key auth for write endpoints
│   │   ├── websocket.py          # WebSocket manager (100 conn limit + origin check)
│   │   └── routes/               # 26 route modules (116 endpoints)
│   ├── wes/                      # Warehouse Execution System
│   ├── monitoring/               # InfluxDB writer, Redis cache
│   ├── intelligence/             # io-gita v4 (hierarchical zone ID)
│   └── tests/                    # Python test suite (387 tests)
│
├── configs/                      # Pluggable configuration files
│   ├── warehouses/               # JSON warehouse maps (simple_grid, botvalley)
│   ├── robots/                   # YAML robot presets (differential_drive, unidirectional)
│   ├── fleets/                   # Fleet manifests (mixed fleet definitions)
│   └── behavior_trees/           # XML behavior tree definitions
│
├── docker/                       # Container infrastructure
│   ├── Dockerfile                # 3-stage: C++ build + frontend build + runtime
│   ├── docker-compose.yml        # 7 services with auth (secrets via .env)
│   ├── .env.docker.example       # Docker secrets template
│   ├── mosquitto/                # MQTT broker config
│   │   └── mosquitto.conf        # Mosquitto listeners + persistence
│   └── start.sh                  # Process launcher with graceful shutdown
│
├── frontend/                     # React dashboard (TypeScript + Vite + React Three Fiber)
│   └── src/
│       ├── components/           # WarehouseGrid, Warehouse3D, Robot3DModel, etc.
│       ├── hooks/                # useApi, useFleetWebSocket, useRobotPositions
│       └── types.ts              # TypeScript interfaces matching Pydantic models
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
│   ├── API_REFERENCE.md          # All 116 endpoints
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

### Why io-gita v4 was reinstated

io-gita v1-v3 (Hopfield ODE zone identification) failed — cold start localization achieved only 52% accuracy with 3D LiDAR, well below the 75% gate. Root cause: 16-feature LiDAR extraction was too similar between zones (see `COLD_START_CLOSED.md`).

io-gita v4 uses a hierarchical zone-first approach: geometry-only zone features (12-dim) with zone-first hierarchy, achieving >90% zone accuracy. The intelligence layer now provides zone identification per robot and cold start recovery hints via 3 REST endpoints.

### Why Pluggable Configs?

The goal is for any robotics company to use this simulation by providing their warehouse map (JSON) and robot specs (YAML). No code changes needed:
- Set `WAREHOUSE_CONFIG=my_warehouse` and `ROBOT_CONFIG=my_robot` env vars
- Drop files in `configs/warehouses/` and `configs/robots/`
- Run `docker compose up --build`

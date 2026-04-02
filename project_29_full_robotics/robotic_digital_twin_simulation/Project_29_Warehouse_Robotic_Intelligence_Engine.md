# Project 29a — WRIE: Warehouse Robotics Intelligence Engine

## Complete Technical Reference — Agnostic Platform Edition

> **Base:** P29 (18 phases, ~1,428+ tests, ~118 endpoints, 86+ audit) | **Evolution:** P29a (robot/map/WMS agnostic SaaS)
>
> **Live at:** Dashboard `http://localhost:8029/dashboard` | API Docs `http://localhost:8029/docs` | Grafana `http://localhost:3000`
>
> **Vision:** Web-based simulation platform — any robot, any warehouse, any ERP. Users sign up, upload configs, run simulations, watch 3D in browser.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement & Goals](#2-problem-statement--goals)
3. [Architecture Overview](#3-architecture-overview)
4. [Technology Stack](#4-technology-stack)
5. [Docker Deployment](#5-docker-deployment)
6. [C++ Fleet Core (FMS)](#6-c-fleet-core-fms)
7. [Python FastAPI Backend](#7-python-fastapi-backend)
8. [Complete API Reference (~118 Endpoints)](#8-complete-api-reference-118-endpoints)
9. [Robot Models & Properties](#9-robot-models--properties)
10. [Gazebo Simulation Environments](#10-gazebo-simulation-environments)
11. [Navigation & Path Planning](#11-navigation--path-planning)
12. [Behavior Trees (BTCPP v4)](#12-behavior-trees-btcpp-v4)
13. [io-gita Zone Intelligence](#13-io-gita-zone-intelligence)
14. [Warehouse Execution System (WES)](#14-warehouse-execution-system-wes)
15. [Warehouse Control System (WCS)](#15-warehouse-control-system-wcs)
16. [Warehouse Management System (WMS)](#16-warehouse-management-system-wms)
17. [Inventory Management](#17-inventory-management)
18. [VDA5050 Protocol](#18-vda5050-protocol)
19. [Multi-Agent Path Finding (MAPF)](#19-multi-agent-path-finding-mapf)
20. [Predictive Maintenance](#20-predictive-maintenance)
21. [Smart Charging](#21-smart-charging)
22. [Human Dynamic Agents](#22-human-dynamic-agents)
23. [ROS2 Bridge](#23-ros2-bridge)
24. [React 3D Dashboard](#24-react-3d-dashboard)
25. [Analytics & Monitoring](#25-analytics--monitoring)
26. [Warehouse Designer](#26-warehouse-designer)
27. [Scenario Simulation & Fault Injection](#27-scenario-simulation--fault-injection)
28. [Configuration System](#28-configuration-system)
29. [Database Architecture](#29-database-architecture)
30. [WebSocket Real-Time Streaming](#30-websocket-real-time-streaming)
31. [Testing & Quality](#31-testing--quality)
32. [Online Use Cases (Docker + Gazebo)](#32-online-use-cases-docker--gazebo)
33. [Performance Benchmarks](#33-performance-benchmarks)
34. [Project File Structure](#34-project-file-structure)
35. [Quick Start Guide](#35-quick-start-guide)
36. [Appendix A: ADRs](#appendix-a-architectural-decision-records-adrs) (11 ADRs)
37. [Appendix B: Security](#appendix-b-security)
38. [Appendix C: Known Limitations & Future Work](#appendix-c-known-limitations--future-work)
39. [Appendix D: Port Reference](#appendix-d-port-reference)

---

## 1. Executive Summary

P29 WRIE is a **production-grade warehouse robotics digital twin** that compiles and runs **actual production fleet_core C++ code** (~200K LOC) alongside a Python FastAPI intelligence layer, Gazebo Fortress physics simulation, and a React 3D dashboard — all fully Dockerized as 8 services.

### Key Metrics

| Metric | Value |
|--------|-------|
| API Endpoints | **~118** documented in feature table (28 route modules) |
| Tests | **~1,428+** (398 C++ gtest + 928 pytest + ~50 Playwright E2E + ~52 Gazebo integration) |
| C++ Core LOC | 12,287 across 63 files |
| Python Backend LOC | 45,791 across 28 route modules |
| Docker Services | **8** (MongoDB, Redis, RabbitMQ, InfluxDB, Grafana, Mosquitto, ROS2 Bridge, main app) |
| Robot Models | **9** (5 industrial + 2 generic + 2 base) |
| Gazebo Worlds | **6** SDF environments (5x5 grid to 150x200m) |
| Phases Completed | **18** |
| FMS Cycle Rate | **15Hz** (67ms budget, 30-40ms typical) |
| Zone ID Speed | **0.008ms** per query (KDTree v5) |
| Blueprint Score | Kimi 95+, Codex 96 |
| Self-Audit Score | 86/100 |

### Core Principle

**Compile and run ACTUAL production fleet_core C++ code. No rewrites. No "equivalent" Python.** The simulation runs the SAME binary that runs on physical robots. Python exists only for NEW layers that don't exist in fleet_core (analytics, io-gita intelligence, WES order generation, REST API wrapper, dashboard).

---

## 2. Problem Statement & Goals

### The Problem

No unified simulation engine replicates the exact production fleet behavior (~200K LOC C++ fleet_core). Testing FMS logic, pathfinding, collision avoidance, or behavior tree changes requires physical robots. Additionally, warehouse robots relying on barcode grid localization — when barcodes are damaged or missing, robots are blind with no spatial awareness fallback. There is no predictive intelligence layer to prevent bottlenecks and deadlocks before they happen.

### Target Users

1. **Robotics engineering team** — validate FMS/navigation changes without hardware
2. **Warehouse automation engineers** — test fleet configurations and workflows
3. **Robotics simulation developers** — extend and customize the simulation

### Success Metrics

| Metric | Target | How Measured |
|--------|--------|-------------|
| Sim-to-real behavioral gap | < 5% | Velocity profile comparison against fleet_core outputs |
| io-gita zone identification | < 1ms | Timing instrumentation on sg_engine |
| Cold start recovery | < 2s total | Time from robot restart to barcode-confirmed position |
| Fleet concurrency | 10 robots (mixed fleet) | All robots active simultaneously |
| Telemetry loop | 15Hz sustained (67ms budget) | Main loop timing instrumentation |
| Zero deadlocks | 0 in 1-hour run | Deadlock counter in fleet events |
| Pathfinding response | < 10ms for 100-node graph | A* timing instrumentation |
| MPC solve time | < 50ms per step | OSQP timing instrumentation |
| SG prediction budget | < 25ms per cycle | Must fit in remaining FMS loop budget |
| Node reservation ILP | < 15ms | ILP solver timing |

---

## 3. Architecture Overview

### System Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    DOCKER CONTAINER (Ubuntu 22.04)                        │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ FLEET_CORE C++ (COMPILED — ACTUAL PRODUCTION CODE)                  │   │
│  │  src/fleet/  → FleetManager, FleetController, COPP Controller    │   │
│  │  src/task/   → TaskManager, TaskPool, FIFO allocator             │   │
│  │  src/graph/  → A*, Dijkstra, NodeReservation (ILP)               │   │
│  │  src/robot/  → Robot state machine, BatteryModel, MotionCtrl     │   │
│  │  src/network/→ TCP:65123 (ProtocolV1), REST:7012                 │   │
│  │  src/database/→ MongoDB native C++ driver (mongocxx)             │   │
│  │  fleet_core_assets/ → BTCPP v4 behavior tree XMLs                │   │
│  └──────────┬──────────────┬──────────────┬─────────────────────────┘   │
│             │              │              │                              │
│             │ TCP:65123    │ MongoDB      │ REST:7012                    │
│             ▼              ▼              ▼                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │
│  │ GAZEBO       │  │ MongoDB 7    │  │ RabbitMQ 3   │                  │
│  │ FORTRESS     │  │ :27017       │  │ :5672        │                  │
│  │ (Physics Sim)│  │ State IPC    │  │ Task queues  │                  │
│  │ 9 Robot      │  │ (C++ writes, │  │ Event bus    │                  │
│  │ Models       │  │  Python reads)│  │ DLQ          │                  │
│  │ 6 Worlds     │  └──────────────┘  └──────────────┘                  │
│  └──────────────┘                                                       │
│                                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │
│  │ io-gita      │  │ Redis 7      │  │ InfluxDB 2   │                  │
│  │ (compiled    │  │ Hot state    │  │ Time-series  │                  │
│  │  binary)     │  │ cache        │  │ telemetry    │                  │
│  │ KDTree v5    │  └──────────────┘  └──────────────┘                  │
│  │ 0.008ms/qry  │                                                       │
│  └──────────────┘  ┌──────────────┐  ┌──────────────┐                  │
│                    │ Mosquitto 2  │  │ Grafana      │                  │
│                    │ MQTT:1883    │  │ :3000        │                  │
│                    │ VDA5050      │  │ Dashboards   │                  │
│                    └──────────────┘  └──────────────┘                  │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ PYTHON FastAPI (:8029) — ~118 REST endpoints + WebSocket          │   │
│  │  Fleet | Tasks | WES | WCS | WMS | Inventory | VDA5050 | MAPF   │   │
│  │  Scenarios | io-gita | Maintenance | Charging | Human Agents    │   │
│  │  Designer | Analytics | Heatmap | ROS2 | Telemetry | Health     │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌──────────────┐                                                       │
│  │ ROS2 Bridge  │                                                       │
│  │ (Humble)     │                                                       │
│  │ nav2 + HAL   │                                                       │
│  └──────────────┘                                                       │
└──────────────────────────────────────────────────────────────────────────┘
         │ HTTP + WebSocket
         ▼
┌────────────────────────┐
│ React Dashboard :5199  │
│ ├─ 2D Warehouse Grid   │
│ ├─ 3D Three.js View    │
│ ├─ Warehouse Designer  │
│ ├─ 12+ Metric Panels   │
│ └─ WebSocket Live Feed │
└────────────────────────┘
```

### Three-Process Architecture (One IPC Method: MongoDB)

```
fleet_core C++ process (fmsApp)
    ├── Listens TCP:65123 (robot communication — ProtocolV1)
    ├── Connects to MongoDB:27017 (writes ALL state here at 15Hz)
    ├── Connects to RabbitMQ:5672 (receives tasks, events)
    ├── Runs 15Hz main loop (actual fleet_core Application.cpp)
    ├── Has its own REST API on port 7012 (fleet_core RESTInterface.cpp)
    └── ALL fleet state lives in MongoDB (agents, tasks, events, paths)

FastAPI Python process
    ├── Reads fleet state FROM MongoDB (same DB fleet_core writes to)
    ├── Reads Redis hot state (populated by Python poller reading MongoDB)
    ├── Serves REST API :8029 (adds intelligence/analytics endpoints)
    ├── Serves WebSocket /ws/fleet (polls MongoDB, broadcasts changes)
    ├── Writes to InfluxDB (time-series telemetry from MongoDB data)
    └── Runs SG prediction engine (reads MongoDB fleet state)

Gazebo C++ process
    ├── Physics simulation of warehouse + robots
    ├── Robot models connect to fmsApp via TCP:65123 (same as real hardware)
    └── Sensor plugins (barcode, obstacle, conveyor)
```

### IPC Decision: MongoDB (Not pybind11, Not shared memory)

**Why MongoDB:** fleet_core already writes ALL state to MongoDB (agents collection updated at 15Hz, tasks/events/paths on change). Python reads the SAME MongoDB. No new IPC needed. This is how fleet_core works in production — external systems read MongoDB.

**Latency:** MongoDB read < 5ms. For 15Hz position updates, Python polls agents collection. For dashboard (1-2Hz updates), more than sufficient.

---

## 4. Technology Stack

| Layer | Technology | Language | Source |
|-------|-----------|----------|--------|
| Container | Docker Desktop | — | New |
| OS | Ubuntu 22.04 | — | New |
| Physics Sim | Gazebo Fortress | C++ | New |
| FMS Core | fleet_core (compiled fmsApp) | C++17 | **ACTUAL production code** |
| Robot Control | fleet_core (robot state machine) | C++17 | **ACTUAL production code** |
| Navigation | A* + NodeReservation (ILP) | C++17 | **ACTUAL production code** |
| Behavior Trees | BTCPP v4 | C++17 | **ACTUAL production code** |
| TCP Protocol | ProtocolV1 (33 fields, CRC32) | C++17 | **ACTUAL production code** |
| Fleet DB Driver | mongocxx (native C++) | C++17 | **ACTUAL production code** |
| Zone Intelligence | io-gita sg_engine (KDTree v5) | C++ (compiled binary) | Existing io-gita code |
| SG Prediction | Semantic Gravity engine | Python | **NEW** |
| WES | Order flow engine | Python | **NEW** |
| WCS | Conveyor + sorter simulation | C++ + Python | **NEW** |
| Backend API | FastAPI + Uvicorn | Python 3.11 | **NEW** |
| Dashboard | React 18 + Vite + Tailwind CSS | TypeScript | **NEW** |
| 3D Rendering | Three.js | TypeScript | **NEW** |
| State DB | MongoDB 7 | — | Infrastructure |
| Message Queue | RabbitMQ 3 | — | Infrastructure |
| Hot Cache | Redis 7 | — | Infrastructure |
| Time-Series | InfluxDB 2 | — | Infrastructure |
| MQTT Broker | Eclipse Mosquitto 2 | — | Infrastructure |
| Monitoring | Grafana | — | Infrastructure |
| ROS2 | ROS Humble (nav2 bridge) | Python | **NEW** |
| Testing | pytest + httpx + gtest + Playwright | Python/C++ | — |

---

## 5. Docker Deployment

### Service Architecture (8 Services)

| Service | Container | Ports | Purpose | Resources |
|---------|-----------|-------|---------|-----------|
| **wrie / rdt** | `rdt-app` | 65123, 7012, 8029 | C++ FMS + Python API + Gazebo | 2 CPU, 4GB RAM |
| **mongodb** | `rdt-mongodb` | 27017 | State IPC (C++ writes, Python reads) | 1 CPU, 1GB RAM |
| **rabbitmq** | `rdt-rabbitmq` | 5672, 15672 | Task queue + event bus + DLQ | Default |
| **redis** | `rdt-redis` | 6380 (mapped from 6379) | Real-time hot state cache | 0.5 CPU, 512MB RAM |
| **influxdb** | `rdt-influxdb` | 8086 | Time-series telemetry (7-day retention) | 1 CPU, 1GB RAM |
| **mosquitto** | `rdt-mosquitto` | 1883, 9001 | MQTT broker for VDA5050 AGV protocol | Default |
| **ros2_bridge** | `rdt-ros2-bridge` | — | ROS Humble nav2 integration | Default |
| **grafana** | `rdt-grafana` | 3000 | Telemetry dashboards (InfluxDB source) | Default |

### Multi-Stage Dockerfile

**Stage 1 — C++ Builder:**
```
FROM ubuntu:22.04 AS cpp-builder
→ Installs: build-essential, cmake, git, python3, protobuf, flex, OpenSSH
→ Clones fleet_core submodules via SSH forwarding
→ Runs: cmake + vcpkg (auto-downloads: grpc, mongocxx, rabbitmq-c, spdlog, etc.)
→ Builds: fmsApp + fmsSimulatorApp with -j4 parallelism
→ Output: /fleet_core/install/bin/, /fleet_core/install/lib/
```

**Stage 2 — Runtime:**
```
FROM ubuntu:22.04
→ Installs: libssl3, curl, python3.11, python3-pip
→ Adds Gazebo Fortress from OSRF repos
→ Copies: fleet_core binaries + assets (maps, BTs, configs)
→ Copies: Python app (FastAPI routers, services)
→ Copies: io-gita compiled binary
→ Copies: Gazebo world configs (SDF files)
→ Sets: LD_LIBRARY_PATH=/fleet_core/lib
→ Runs: start.sh → fmsApp + uvicorn
```

### Startup Process (`start.sh`)

1. Tries `fmsSimulatorApp` first (simulation mode), falls back to `fmsApp` (production mode)
2. C++ process listens on TCP:65123 + REST:7012, runs in background
3. FastAPI starts on port 8029 with uvicorn, connects to MongoDB/Redis/InfluxDB
4. Dual-process trap: if C++ dies → shutdown Python, if Python dies → shutdown C++
5. SIGTERM/SIGINT handled gracefully

### Build & Run Commands

```bash
# Build (Apple Silicon):
docker build --platform linux/amd64 -f docker/Dockerfile -t wrie .

# Build (with SSH for private repos):
DOCKER_BUILDKIT=1 docker build --ssh default --platform linux/amd64 -t wrie .

# Run full stack:
cd case-studies/project_29_full_robotics/robotic_digital_twin_simulation
cp docker/.env.docker.example docker/.env  # Edit passwords!
docker compose -f docker/docker-compose.yml up --build

# Verify all services:
docker compose ps
curl http://localhost:8029/health
```

### Environment Variables

```env
# MongoDB
MONGO_USER=rdt
MONGO_PASSWORD=changeme          # CHANGE IN PRODUCTION

# Redis
REDIS_PASSWORD=changeme

# InfluxDB
INFLUXDB_USER=admin
INFLUXDB_PASSWORD=changeme
INFLUXDB_TOKEN=changeme
INFLUXDB_ORG=rdt
INFLUXDB_BUCKET=fleet_telemetry

# RabbitMQ
RABBITMQ_USER=fms
RABBITMQ_PASSWORD=changeme

# MQTT (Mosquitto)
MQTT_USER=rdt
MQTT_PASSWORD=changeme

# FMS Ports
FMS_TCP_PORT=65123
FMS_REST_PORT=7012
API_PORT=8029

# Config
WAREHOUSE_CONFIG=production_50x60
ROBOT_CONFIG=differential_drive
API_KEY=disabled                 # Set to actual key for write protection
LOG_LEVEL=info
```

### Health Checks

All services have Docker healthchecks configured:

- **MongoDB**: `mongosh --eval "db.adminCommand('ping')"` every 5s
- **RabbitMQ**: `rabbitmq-diagnostics -q ping` every 5s
- **Mosquitto**: `mosquitto_sub -C 1 -W 3` every 10s
- **Main app**: `curl http://localhost:8029/health` every 10s (30s start period)

The `/health` endpoint probes each service:
- MongoDB: `admin.command("ping")` → `{ok: 1.0}`
- Redis: `client.ping()` → `True`
- InfluxDB: `GET /health` → status == "pass"
- RabbitMQ: `GET /api/health/checks/alarms` → HTTP 200

---

## 6. C++ Fleet Core (FMS)

### What Is Compiled From Production Fleet Core

| Component | fleet_core Source | Lines |
|-----------|------------------|-------|
| FleetManager (15Hz orchestration loop) | `src/fleet/` | 1,200 |
| FleetController / COPP Controller | `src/fleet/controller/aCopp/` | 300 |
| TaskManager + TaskPool + FIFO allocator | `src/task/` | 800 |
| A* Pathfinder + Dijkstra | `src/graph/` | 600 |
| NodeReservation (Coupled, ILP) | `src/graph/nodeReservation/` | 500 |
| QuadTree Spatial Index | `src/graph/` | 300 |
| Robot State Machine | `src/robot/` | 250 |
| MotionController (P-controller) | `src/robot/` | 350 |
| BatteryModel | `src/robot/` | 400 |
| ObstacleHandler | `src/robot/` | 350 |
| BehaviorTree Engine (BTCPP v4) | `src/behavior/` | 700 |
| TCP Server (ProtocolV1) | `src/network/` | 600 |
| REST Server | `src/network/` | 400 |
| MongoDB Driver (native C++) | `src/database/` | 300 |
| Sanitizer + Notification | `src/fleet/sanitizer/`, `notification/` | 200 |
| WCS Interface | `src/wcs/` | 200 |
| **Total** | | **~12,287** |

### 15Hz Main Loop (67ms Budget)

Each cycle, the C++ FleetManager executes:

```
Step 1: Receive robot telemetry (TCP:65123)        2-3ms
Step 2: Update agent states (parse frames)          3-5ms
Step 3: Tick behavior trees (all robots)            3-5ms
Step 4: Allocate pending tasks (FIFO/nearest/prio)  2-5ms
Step 5: Generate/update paths (A*)                  2-5ms
Step 6: Node reservation (ILP, 4 nodes ahead)       5-15ms
Step 7: Send commands to robots (TCP)               1-2ms
Step 8: Database flush (async MongoDB write)        Async
Step 9: Event system dispatch                       1-3ms
────────────────────────────────────────────────────
TOTAL CRITICAL PATH: 15-38ms (well within 67ms budget)
```

### TCP Protocol V1

- **Port:** 65123
- **Frame Format:** Newline-delimited, `robot_id|timestamp|type|payload`
- **Fields:** 33 per frame + CRC32 checksum
- **Rate:** 15Hz bidirectional (telemetry in, commands out)
- **Same protocol used by actual physical warehouse robots**

### C++ REST API (Port 7012)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/robots` | Fleet status from C++ engine |
| GET | `/api/fleet/kpis` | Real-time KPIs |
| POST | `/api/command` | Dispatch robot command |
| GET | `/health` | C++ process health |

---

## 7. Python FastAPI Backend

### Architecture

- **Framework:** FastAPI + Uvicorn
- **Port:** 8029
- **Routers:** 28 route modules (~118 endpoints)
- **MongoDB Driver:** `motor` (async)
- **Redis Client:** `redis-py` (async)
- **InfluxDB Client:** `influxdb-client`
- **MQTT Client:** `aiomqtt` (for VDA5050)

### Key Files

```
python/app/
├── main.py              # FastAPI app initialization, lifespan, 33 service initializers
├── config.py            # Pydantic Settings (env vars → typed config)
├── auth.py              # API key / JWT middleware
├── websocket.py         # ConnectionManager + broadcast logic (max 100 connections)
├── routes/
│   ├── fleet.py         # GET /api/fleet/status, robots
│   ├── robots.py        # GET/POST /api/robots/{id}
│   ├── tasks.py         # CRUD /api/tasks
│   ├── maps.py          # GET /api/map, pathfinding
│   ├── wes.py           # Order injection, KPIs
│   ├── waves.py         # Wave management
│   ├── wcs.py           # Conveyor + sorter + lanes + packages
│   ├── wms.py           # WMS connector + DLQ
│   ├── inventory.py     # SKU, stock, replenishment, optimizer
│   ├── vda5050.py       # VDA5050 MQTT gateway
│   ├── mapf.py          # CBS + PIBT solvers
│   ├── iogita.py        # Zone intelligence
│   ├── ros2.py          # ROS2 bridge
│   ├── maintenance.py   # Predictive maintenance
│   ├── charging.py      # Smart charging
│   ├── human_agents.py  # Human dynamic agents
│   ├── simulation.py    # Sim control + fault injection
│   ├── scenarios.py     # Scenario CRUD + run + compare
│   ├── designer.py      # Layout editor backend
│   ├── analytics.py     # Fleet analytics
│   ├── heatmap.py       # Traffic density grid
│   ├── stats.py         # Throughput stats
│   ├── events.py        # Event log
│   ├── telemetry.py     # Robot telemetry
│   ├── telemetry_export.py  # CSV/PDF export
│   ├── config_routes.py # Runtime config
│   ├── reservations.py  # Active node reservations
│   └── order_import.py  # External order import
└── models/              # Pydantic schemas (Robot, Task, FleetState, etc.)
```

---

## 8. Complete API Reference (~118 Endpoints)

### A. Fleet Management

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/fleet/status` | Aggregate fleet overview (total, status counts, utilization %) |
| GET | `/api/robots` | All robots with position, battery, status, task, model |
| GET | `/api/robots/{robot_id}` | Single robot with all telemetry fields |
| POST | `/api/robots/{robot_id}/command` | Send action (move, load, charge, idle) |
| GET | `/api/telemetry/{robot_id}?limit=100` | Time-series telemetry (up to 10K points) |
| GET | `/api/reservations/active` | Current node reservations for deadlock prevention |

### B. Task Management

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/tasks` | All tasks (paginated, 10K cap) |
| POST | `/api/tasks` | Create pick-and-drop task `{type, source_node, destination_node, priority}` |
| GET | `/api/tasks/{task_id}` | Task with full lifecycle timestamps |
| DELETE | `/api/tasks/{task_id}` | Delete task (cascades to robot) |
| POST | `/api/tasks/{task_id}/cancel` | Cancel running/pending task |

### C. Warehouse Map

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/map` | Complete warehouse graph (nodes + edges + zones) |
| GET | `/api/map/nodes` | All nodes with type (pick, drop, shelf, charge, aisle, hub, staging) |
| GET | `/api/map/zones` | All zones with coordinates, names, types |
| GET | `/api/map/path?from=A&to=B` | A* shortest path (node list + distance + hops) |

### D. WES (Warehouse Execution)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/wes/inject-orders` | Generate random pick/drop orders `{num_orders, type}` |
| GET | `/api/wes/kpi` | Live metrics: orders/hr, pick_accuracy_%, throughput, cycle_time_s |
| GET | `/api/wes/waves` | List all waves (pending/active/completed) |
| POST | `/api/wes/waves` | Group orders into wave (manual `{order_ids}` or auto) |
| POST | `/api/wes/waves/{wave_id}/release` | Convert wave orders → robot tasks |
| POST | `/api/wes/wave-rules` | Create wave generation rule |
| GET | `/api/wes/wave-rules` | List all wave rules |
| POST | `/api/wes/orders/import` | Import orders from external source |

### E. WCS (Warehouse Control)

**Conveyors:**

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/wcs/conveyors` | All segments with speed_mps, status, jammed flag |
| GET | `/api/wcs/conveyors/{id}/status` | Single segment status |
| POST | `/api/wcs/conveyors/{id}/control` | Start/stop/set_speed/maintenance |
| POST | `/api/wcs/conveyors/start-all` | Emergency start all |
| POST | `/api/wcs/conveyors/stop-all` | Emergency stop all |
| POST | `/api/wcs/conveyors/{id}/jam` | Simulate jam event |
| POST | `/api/wcs/conveyors/transfer` | Move package between segments |

**Sorter:**

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/wcs/sorter/rules` | All barcode routing rules (regex) |
| POST | `/api/wcs/sorter/rules` | Create barcode→lane rule (max 500) |
| DELETE | `/api/wcs/sorter/rules/{rule_id}` | Delete routing rule |
| POST | `/api/wcs/sorter/sort` | Process barcode → determine target lane |
| GET | `/api/wcs/sorter/stats` | Sort performance: count, errors, misreads |
| GET | `/api/wcs/sorter/log` | Detailed sort event log |
| GET | `/api/wcs/sorter/diverts` | Divert point configuration |

**Lanes:**

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/wcs/lanes` | All lanes (inbound/outbound/express/returns/staging) |
| GET | `/api/wcs/lanes/by-type/{type}` | Filter by lane type |
| GET | `/api/wcs/lanes/{lane_id}` | Single lane status |
| POST | `/api/wcs/lanes/{lane_id}/control` | Open/close/clear lane |
| POST | `/api/wcs/lanes/{lane_id}/package` | Add package to lane |

**Packages:**

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/wcs/packages/{tracking_id}` | Full lifecycle journey with events |
| GET | `/api/wcs/packages/in-transit` | All packages currently moving |
| GET | `/api/wcs/packages/at-location` | Packages at specific location |
| GET | `/api/wcs/packages/by-barcode?barcode=...` | Find by barcode |
| GET | `/api/wcs/stats` | Aggregate conveyor + sorter + lane + package stats |

### F. WMS (Warehouse Management)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/wms/status` | Connector health (SAP/Odoo/webhook, connected, DLQ summary) |
| POST | `/api/wms/sync` | Pull orders from WMS system |
| POST | `/api/wms/webhook/receive` | Receive order via HTTP webhook |
| GET | `/api/wms/orders?offset=0&limit=50` | List synced orders (paginated, 10K cap) |
| GET | `/api/wms/dlq` | Dead Letter Queue — failed orders |
| POST | `/api/wms/dlq/{message_id}/retry` | Retry failed order |

### G. Inventory Management

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/inventory/skus` | All SKUs with metadata |
| GET | `/api/inventory/skus/{sku_id}` | Single SKU detail |
| GET | `/api/inventory/stock-levels` | Current stock per SKU across all nodes |
| GET | `/api/inventory/stock/{node_name}` | Stock at specific warehouse location |
| POST | `/api/inventory/receive` | Add inventory (putaway) `{sku_id, node, qty}` |
| POST | `/api/inventory/pick` | Remove inventory (fulfillment) `{sku_id, node, qty}` |
| POST | `/api/inventory/adjust` | Correct stock (cycle count) `{sku_id, node, qty, reason}` |
| POST | `/api/inventory/transfer` | Move stock between nodes `{sku_id, from_node, to_node, qty}` |
| POST | `/api/inventory/cycle-count` | Perform count + auto-adjust `{node, counts: [{sku_id, qty}]}` |
| GET | `/api/inventory/movements?limit=50` | Audit log of all changes |
| GET | `/api/inventory/replenishment` | Pending replenishment orders |
| POST | `/api/inventory/replenishment/check` | Auto-generate replenishment orders |
| POST | `/api/inventory/replenishment/{id}/complete` | Mark replenishment complete |
| POST | `/api/inventory/replenishment/{id}/cancel` | Cancel replenishment |
| GET | `/api/inventory/optimizer/abc` | ABC classification (A=20% fast, B=30%, C=50%) |
| GET | `/api/inventory/optimizer/recommendations` | Suggest node reassignments |
| GET | `/api/inventory/optimizer/zone-balance` | Inventory distribution heatmap |
| GET | `/api/inventory/stats` | Combined inventory + replenishment KPIs |

### H. VDA5050 Protocol

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/vda5050/status` | MQTT broker connection + AGV count |
| POST | `/api/vda5050/orders` | Dispatch VDA5050 order (max 500 nodes, 200 AGVs) |
| POST | `/api/vda5050/instant-actions` | Emergency commands (E-stop, cancel, pause) |
| GET | `/api/vda5050/agvs` | All connected AGVs with latest state |
| GET | `/api/vda5050/agvs/{agv_id}/state` | Full VDA5050 state JSON |

### I. MAPF (Multi-Agent Path Finding)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/mapf/solve` | Optimal path planning `{agents: [{id, start, goal}], solver: "cbs"\|"pibt"}` |
| POST | `/api/mapf/step` | Single-tick move for 15Hz integration (PIBT, max 500 agents) |
| GET | `/api/mapf/status` | Last solve time, conflicts, total solves |
| GET | `/api/mapf/benchmarks` | Solve time vs agent count history |
| GET | `/api/mapf/congestion` | Traffic hotspots + top 10 bottleneck nodes |

### J. ROS2 Bridge

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/ros2/status` | ROS2 availability + mode (live/sim) |
| GET | `/api/ros2/topics` | Active ROS2 topics (or simulated list) |
| POST | `/api/ros2/nav-goal` | Send nav2 goal `{robot_id, x, y, theta}` (100/min rate limit) |
| GET | `/api/ros2/pose/{robot_id}` | Robot position from ROS2 odom (fallback: sim pose) |

### K. Predictive Maintenance

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/maintenance/status` | Current maintenance state |
| GET | `/api/maintenance/predictions/{robot_id}` | Component degradation forecast |
| GET | `/api/maintenance/schedule` | All scheduled maintenance windows |
| POST | `/api/maintenance/schedule` | Create maintenance window |
| POST | `/api/maintenance/schedule/{id}/complete` | Mark complete |
| POST | `/api/maintenance/schedule/{id}/cancel` | Cancel window |
| GET | `/api/maintenance/schedule/{id}/impact` | Impact on fleet KPIs |
| GET | `/api/maintenance/component-health/{robot_id}` | Component-level health |
| GET | `/api/maintenance/fleet-mtbf` | Mean Time Between Failures |
| POST | `/api/maintenance/simulate-degradation` | Inject degradation for testing |
| GET | `/api/maintenance/alerts` | Critical maintenance alerts |

### L. Smart Charging

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/charging/status` | Charge station states + queue |
| GET | `/api/charging/strategy` | Active strategy (conservative/aggressive/balanced) |
| POST | `/api/charging/strategy` | Switch charging strategy |
| GET | `/api/charging/queue` | Robots waiting to charge |
| GET | `/api/charging/battery-health` | Health degradation per robot |
| GET | `/api/charging/energy-forecast` | Predicted energy consumption |
| GET | `/api/charging/stats` | Charging statistics (cycles, times, efficiency) |
| GET | `/api/charging/recommendations` | Optimal charging times |
| POST | `/api/charging/request/{robot_id}` | Request charge slot |
| POST | `/api/charging/release/{robot_id}` | Release charge slot |
| POST | `/api/charging/simulate-cycle` | Simulate full charge/discharge cycle |

### M. Human Dynamic Agents

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/human-agents` | List all human agents in warehouse |
| POST | `/api/human-agents` | Create human agent |
| GET | `/api/human-agents/{agent_id}` | Single agent detail |
| PATCH | `/api/human-agents/{agent_id}` | Update agent state |
| DELETE | `/api/human-agents/{agent_id}` | Remove agent |
| POST | `/api/human-agents/{agent_id}/move` | Move agent to location |
| GET | `/api/human-agents/safety-zones` | All defined safety zones |
| GET | `/api/human-agents/blocked-nodes` | Nodes blocked by humans |
| GET | `/api/human-agents/{agent_id}/nearby-robots` | Robots near this human |
| GET | `/api/human-agents/interactions` | Log of robot-human interactions |
| GET | `/api/human-agents/stats` | Collision avoidance, near-miss stats |
| POST | `/api/human-agents/simulate` | Simulate human movement patterns |

### N. io-gita Intelligence

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/iogita/status` | Engine version, backend (kdtree/hopfield), zone/node counts |
| GET | `/api/iogita/zones` | All zones with KDTree nearest-neighbor mapping |
| POST | `/api/iogita/cold-start/{robot_id}` | 5-phase recovery `{hint_x, hint_y}` |
| POST | `/api/iogita/recover/{robot_id}` | Direct KDTree-based 360-degree scan recovery |

### O. Scenarios & Simulation

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/scenarios` | List all simulation scenarios |
| POST | `/api/scenarios` | Create scenario `{name, fleet_size, warehouse_config, strategy}` |
| POST | `/api/scenarios/{id}/run` | Execute: orders → simulate → KPIs |
| GET | `/api/scenarios/{id}/results` | KPIs (throughput, cycle_time, utilization) |
| GET | `/api/scenarios/compare?ids=A,B` | Side-by-side comparison (JSON/CSV/PDF) |
| DELETE | `/api/scenarios/{id}` | Archive scenario |
| GET | `/api/simulation/status` | Sim state (running, tick count, active faults) |
| POST | `/api/simulation/start` | Start simulation loop |
| POST | `/api/simulation/stop` | Stop simulation |
| POST | `/api/simulation/inject-fault` | Resilience test `{robot_id, type, duration_s}` |

### P. Warehouse Designer

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/designer/validate` | Check warehouse JSON for errors |
| POST | `/api/designer/export` | Save design to `configs/warehouses/` |
| POST | `/api/designer/import` | Load existing warehouse JSON |
| POST | `/api/designer/validate-3d` | 3D validation + charge station recommendations |
| POST | `/api/designer/export-all` | Full config bundle (warehouse + conveyor + fleet) |
| GET | `/api/designer/templates` | Pre-built templates (small/medium/large/industrial) |
| GET | `/api/designer/templates/categories` | Template categories |
| GET | `/api/designer/templates/{name}` | Single template detail |
| POST | `/api/designer/auto-edges` | Generate edges by distance |
| POST | `/api/designer/template/scale` | Scale template up/down |

### Q. Analytics & Monitoring

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/analytics/fleet` | Fleet KPIs (throughput, avg task time, battery) |
| GET | `/api/analytics/ab-comparison` | Compare strategies (FIFO/nearest/priority) |
| GET | `/api/analytics/heatmap?duration=1h&resolution=0.5` | Robot traffic density grid |
| GET | `/api/stats/throughput` | Task completion rates over time window |
| GET | `/api/events?severity=warning&robot_id=X` | Filtered event log |
| GET | `/api/telemetry/{robot_id}?limit=100` | Time-series telemetry (up to 10K) |
| GET | `/api/telemetry/export?format=csv` | Export telemetry to CSV |
| GET | `/api/telemetry/export/production` | Production telemetry export |
| GET | `/api/config/robots` | Runtime robot config from YAML |

### R. System Health

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/health` | Real service probes (MongoDB, Redis, InfluxDB, RabbitMQ) |
| WebSocket | `ws://localhost:8029/ws/fleet` | Real-time fleet events (poses, state changes) |
| GET | `/docs` | OpenAPI/Swagger interactive documentation |
| GET | `/redoc` | ReDoc documentation |

---

## 9. Robot Models & Properties

### Available Robot Models (9 Total)

| Model | Type | Mass | Dimensions (m) | Max Speed | Locomotion | Attachment |
|-------|------|------|----------------|-----------|------------|------------|
| **Heavy Lifter** | Industrial | 150 kg | 0.93 x 0.73 x 0.666 | 0.8 m/s | Differential | Lifter |
| **Light Courier** | Industrial | 30 kg | 0.6 x 0.5 x 0.25 | 1.0 m/s | Differential | None |
| **Fork AMR** | Industrial | 45 kg | 0.7 x 0.6 x 0.35 | 0.9 m/s | Differential | Forklift |
| **Omni Carrier** | Industrial | 55 kg | 0.75 x 0.65 x 0.40 | 1.2 m/s | Omni (4-wheel) | Tray |
| **High-Speed** | Industrial | 60 kg | 0.8 x 0.7 x 0.45 | 1.5 m/s | Differential | None |
| **DiffDrive AMR** | Generic (instantiable) | 150 kg | 0.93 x 0.73 x 0.666 | 0.8 m/s | Differential | Configurable |
| **Uni AGV** | Generic (instantiable) | 60 kg | 0.6 x 0.5 x 0.25 | 1.0 m/s | Non-holonomic | None |
| **DiffDrive AMR (template)** | Base (abstract) | — | — | — | Differential | — |
| **Uni AGV (template)** | Base (abstract) | — | — | — | Unidirectional | — |

> **Note:** Base models are abstract SDF templates used for inheritance. Generic models are the concrete, instantiable versions with full physical properties. They share the same geometry but Base has no mass/speed — it exists only as a parent for variant creation.

### Configurable Robot Properties

All properties are loaded from YAML config files at runtime — no hardcoded values.

**Motion Parameters** (`configs/robots/*.yaml`):

| Property | Range | Default (Heavy Lifter) | Description |
|----------|-------|-------------------|-------------|
| `max_linear_velocity` | 0.1–2.0 m/s | 0.8 | Top speed |
| `max_angular_velocity` | 0.5–3.0 rad/s | 1.57 | Rotation speed |
| `linear_acceleration` | 0.5–2.0 m/s² | 1.0 | Ramp-up rate |
| `position_tolerance` | 0.05–0.5 m | 0.25 | "Close enough" to target |
| `angular_tolerance` | 0.01–0.1 rad | 0.025 | Heading precision |
| `wheel_separation` | per model | 0.5475 m | Wheelbase width |
| `wheel_radius` | per model | 0.06 m | Drive wheel radius |

**Battery Parameters:**

| Property | Range | Default | Description |
|----------|-------|---------|-------------|
| `charge_duration_s` | 300–1200 | 450 | Time to charge 0→100% |
| `discharge_duration_s` | 30000–120000 | 60000 | Time to drain 100→0% on idle |
| `motion_energy_factor` | 1.0–1.5 | 1.02 | +2% drain per meter traveled |
| `attachment_energy_factor` | 1.0–1.5 | 1.02 | +2% drain for lifter/forklift ops |
| `critical_threshold_pct` | 10–30 | 20 | Force dock at this SoC |
| `initial_charge_pct` | 0–100 | 100 | Starting charge |

**Safety / Obstacle Parameters:**

| Property | Value | Description |
|----------|-------|-------------|
| `critical_m` | 1.0 m | E-STOP if obstacle closer |
| `warning_m` | 2.0 m | Slow down, request replan |
| `planning_m` | 3.0 m | Include in A* heuristic |
| `safety_field_front` | 1.5 m | Front approach zone |
| `safety_field_rear` | 0.5 m | Rear reverse zone |
| `safety_field_side` | 0.5 m | Side clearance |

### Sensor Configuration Per Robot

**LiDAR:**
- 360 rays (1-degree resolution), 10 Hz update
- Range: 0.08m min, 5.0m max, 0.01m resolution
- Gaussian noise: mean=0, stddev=0.03m

**IMU:**
- 100 Hz update rate
- Angular velocity noise: stddev=0.0524 rad/s (±3 degrees)
- Linear acceleration noise: stddev=0.01 m/s²

**Barcode Reader (Virtual):**
- 5ms debounce, 5 missed read failure threshold
- Reads floor grid markers at 0.8m intervals

**Obstacle Sensor (2-channel front proximity):**
- FOV: -30 to +30 degrees per channel
- Range: 3.0m (planning), 1.0m (critical)

### Robot State Machine

```
IDLE → (task assigned) → MOVING_TO_PICKUP → (arrived) → ROTATING_FOR_LOAD
  → (aligned) → LOADING [action_code=14] → (complete) → MOVING_TO_DROP
  → (arrived) → ROTATING_FOR_UNLOAD → (aligned) → UNLOADING [action_code=15]
  → (complete) → MOVING_TO_CHARGE (if SoC < 20%) → (arrived) → CHARGING [action_code=3]
  → (SoC > 80%) → IDLE

Error States: ERROR_MOTOR_FAULT, ERROR_LOAD_FAULT, ERROR_SENSOR_FAULT, ERROR_NETWORK_TIMEOUT
Recovery: Exponential backoff → hard reset after 5 errors → manual intervention
```

---

## 10. Gazebo Simulation Environments

### 6 Pre-Built Worlds

| World File | Footprint | Nodes | Description |
|------------|-----------|-------|-------------|
| `simple_5x5_grid.sdf` | 5x5 grid | 25 | Basic test environment |
| `warehouse_distinct.sdf` | 40x30m | ~35 | Compact warehouse: walls, shelves (rows A-E), charging bays, barcode grid |
| `warehouse_50x60.sdf` | 50x60m | ~60 | Medium: multiple zones (charge, pick, storage), aisles |
| `warehouse_distinct_fleet.sdf` | 40x30m | ~35 | Multi-fleet variant: distinct zones for 10-robot coordination |
| `botvalley.sdf` | 150x200m | 100+ | High-fidelity BotValley reference warehouse |
| `realistic_warehouse_150x200m.sdf` | 150x200m | 100+ | Large-scale dense shelving + complex aisle network |

### Physics Configuration (All Worlds)

```xml
<physics name="1ms" type="ode">
  <max_step_size>0.001</max_step_size>        <!-- 1ms = 1,000 Hz physics -->
  <real_time_factor>1.0</real_time_factor>    <!-- Wall-clock = sim time -->
</physics>
<gravity>0 0 -9.81</gravity>
```

### Surface Friction (ODE Contact Model)

| Surface | Static (mu) | Kinetic (mu2) | Notes |
|---------|-------------|---------------|-------|
| Floor plane | 0.8 | 0.8 | Standard warehouse floor |
| Drive wheels | 1.0 | 1.0 | High friction for traction |
| Caster wheels | 0.01 | 0.01 | Low friction for free rotation |
| Shelves/walls | 0.5 | 0.5 | Moderate friction |
| Perimeter walls | 0.8 | 0.8 | 0.15m thick, 3.0m height |

### Gazebo Plugins

```xml
<plugin filename="libignition-gazebo-physics-system.so" name="Physics"/>
<plugin filename="libignition-gazebo-scene-broadcaster-system.so" name="SceneBroadcaster"/>
<plugin filename="libignition-gazebo-sensors-system.so" name="Sensors"/>
```

Per-robot DiffDrive plugin:
```xml
<plugin filename="gz-sim-diff-drive-system" name="DiffDrive">
  <wheel_separation>0.5475</wheel_separation>
  <wheel_radius>0.06</wheel_radius>
  <max_linear_acceleration>1.0</max_linear_acceleration>
  <max_angular_velocity>1.57</max_angular_velocity>
  <odom_publish_frequency>15</odom_publish_frequency>
</plugin>
```

### World Generation

Two Python generators create worlds from JSON configs:
- `warehouse_distinct_generator.py` — Input: warehouse JSON → Output: SDF with ground, walls, shelves, barcode grid, node markers
- `gen_fleet_world.py` — Input: warehouse JSON + fleet spec → Output: multi-robot scenario world with spawn positions

---

## 11. Navigation & Path Planning

### A* Algorithm

**Implementation:** C++ (`src/graph/AStar.cpp`)

**Heuristic Options:**
- **Euclidean** (default): `sqrt((dx)² + (dy)²)` — admissible, optimal
- **Manhattan**: `|dx| + |dy|` — for grid-like warehouses
- **Chebyshev**: `max(|dx|, |dy|)` — diagonal movement

**Turn Cost Model:** Penalizes sharp direction changes to produce smoother paths. Computes angle difference at each node via atan2.

**Performance:** < 10ms for 100-node graphs. Uses min-heap priority queue on f-score, unordered_set closed list for O(1) membership.

### Node Reservation (Deadlock Prevention)

**Strategy:** Greedy atomic reservation with deadlock detection

**Protocol:**
1. Scan lookahead window (5-10 nodes ahead)
2. If ANY node held by different robot → reject entire path
3. Release previous reservations for this robot
4. Commit new lookahead nodes atomically

**Deadlock Resolution:**
- Detect circular wait: robot A holds what B needs AND vice versa
- Loser = lexicographically greater robot ID backs off (deterministic, starvation-free)
- Losing robot releases all held nodes, replans

### Multi-Agent Path Finding (MAPF)

**CBS (Conflict-Based Search):**
- Optimal solver, max 200 agents
- Two-level search: high-level conflicts, low-level A* per agent

**PIBT (Priority Inheritance + Backtracking):**
- Fast real-time solver, max 500 agents, linear time complexity
- Single-tick moves for 15Hz integration

---

## 12. Behavior Trees (BTCPP v4)

### Action Nodes (11)

| Action | Code | Timeout | Description |
|--------|------|---------|-------------|
| AcceptTask | 0 | — | Accept task assignment |
| MoveToNode | 0 | 120s | Navigate to target node |
| RotateToHeading | — | 10s | Align to heading |
| ExecuteAttachment | 14/15 | 10s | Load (14) or unload (15) |
| LowerLifter | — | 5s | Lower lifter attachment |
| RaiseLifter | — | 5s | Raise lifter attachment |
| StartCharging | 3 | — | Begin charging |
| EmergencyStop | — | immediate | Emergency stop |
| ReportTaskComplete | — | — | Report task done |
| Idle | — | — | Wait state |
| HardReset | 51 | 30s | Full robot reset |

### Condition Nodes (7)

| Condition | Checks |
|-----------|--------|
| TaskAvailable | task_queue.size > 0 |
| ObstacleInCriticalZone | min_lidar_range < 1.0m |
| ObstacleInWarningZone | min_lidar_range < 2.0m |
| HasErrors | error_state != NONE |
| CargoSecured | load_weight > 0 && stable |
| HasLifterAttachment | attachment == "lifter" |
| AtTarget | distance_to_goal < tolerance |

### Tree Structure (AMR Main)

```
ReactiveSequence (root)
├── Safety Monitor: NOT ObstacleInCriticalZone → EmergencyStop
├── Error Monitor: NOT HasErrors → ErrorRecovery subtree
└── Main Loop (RepeatNode infinite)
    ├── WaitForTask (RetryNode) → TaskAvailable → AcceptTask
    ├── ExecuteTask
    │   ├── NavigateWithAvoidance → pickup_node
    │   ├── RotateToHeading
    │   ├── LowerLifter (if has attachment)
    │   ├── ExecuteAttachment (code=14, load)
    │   ├── NavigateWithAvoidance → drop_node
    │   ├── ExecuteAttachment (code=15, unload)
    │   └── ReportTaskComplete
    └── BatteryManagement (if SoC < threshold)
```

---

## 13. io-gita Zone Intelligence

### Architecture

| Component | File | Purpose |
|-----------|------|---------|
| KDTree Engine (v5) | `intelligence/iogita/zone_identifier.py` | Spatial nearest-neighbor zone/node ID |
| Hopfield ODE (v4) | Fallback binary | Neural ODE zone classifier (preserved as backup) |
| Cold Start | `intelligence/iogita/cold_start.py` | 5-phase position recovery |
| Dual Scan | `intelligence/iogita/dual_scan.py` | Corridor disambiguation |
| Safety Checker | `intelligence/iogita/safety_checker.py` | Clearance validation |
| Symmetry Breaker | `intelligence/iogita/symmetry_breaker.py` | Aisle mirror resolution |

### Performance Comparison

| Engine | Speed | Memory | Accuracy |
|--------|-------|--------|----------|
| **KDTree v5** | 0.008ms/query | Low | 97.2% |
| Hopfield ODE v4 | 4.197ms/query | 329x more | 97.2% |
| **Speedup** | **525x faster** | | Same accuracy |

### 16 Features Extracted from LiDAR

All 16 features are extracted in `zone_identifier.py` → `extract_16_features()`:

| # | Feature | Computation | Normalization |
|---|---------|-------------|---------------|
| F1 | Front clearance | median(scan[345-360, 0-15 deg]) | / 12.0 |
| F2 | Back clearance | median(scan[165-195 deg]) | / 12.0 |
| F3 | Left clearance | median(scan[255-285 deg]) | / 12.0 |
| F4 | Right clearance | median(scan[75-105 deg]) | / 12.0 |
| F5 | Front-half variance | var(scan[315-360, 0-45 deg]) | / 12.0 |
| F6 | Full scan variance | var(full_scan) | / 12.0 |
| F7 | Gap count (>1m) | sum(\|diff\| > 1.0) | / 50.0 |
| F8 | Big gap count (>2m) | sum(\|diff\| > 2.0) | / 20.0 |
| F9 | Left-right symmetry | \|left - right\| / max(left+right, 0.01) | 0-1 ratio |
| F10 | Front-back symmetry | \|front - back\| / max(front+back, 0.01) | 0-1 ratio |
| F11 | Close density | count(scan < 2.0m) / 360 | 0-1 ratio |
| F12 | Far density | count(scan > 4.0m) / 360 | 0-1 ratio |
| F13 | Heading (normalized) | heading_deg / 360.0 | 0-1 |
| F14 | Heading (binned) | int(heading_deg / 45) / 8.0 | 0-1 |
| F15 | Distance from dock | min(dist_from_dock / 30.0, 1.0) | clamped 0-1 |
| F16 | Turns since dock | min(turns_since_dock / 10.0, 1.0) | clamped 0-1 |

Code also provides `extract_24_features()` with 8 additional 3D-LiDAR height-aware features (F17-F24) for environments with multi-level shelving.

### Cold Start Recovery (5 Phases)

1. Spin in place, collect initial 360-degree scan
2. Extract zone features (16 features from LiDAR)
3. KDTree zone identification
4. Dual scan from different position (disambiguation)
5. Graph matching + AMCL fallback if confidence < threshold

### Safety Rules (S1-S7)

- S1: Never override hardware safety (critical zone always stops)
- S2: Dual sensor confirmation for obstacle detection
- S3: Zone boundaries have 0.5m buffer
- S4: Charger approach only in dedicated zone
- S5: Load operations only in designated pickup zones
- S6: Emergency stop preempts all planning
- S7: Manual override tracked for audit

---

## 14. Warehouse Execution System (WES)

### Order Flow Pipeline

```
WMS Orders → OrderGenerator → WaveEngine → TaskGenerator → FleetManager → Robot → Completion
```

### OrderGenerator

Generates orders from warehouse node types:
- **Pick order:** source → pick_node (move + load task)
- **Drop order:** destination → drop_node (move + unload task)
- **Move order:** source → destination (move task only)

### WaveEngine (Rules-Based Wave Generation)

Batching conditions (configurable via `/api/wes/wave-rules`):
- Order count threshold
- Priority threshold
- Zone affinity (batch by zone)
- Time-window rules (batch every N seconds)

### KPI Tracker

| Metric | Definition |
|--------|-----------|
| Throughput | Orders completed per hour |
| Cycle Time | Order creation → completion (seconds) |
| Pick Accuracy | Correct picks / total picks (%) |
| Fleet Utilization | Robots in motion / total (%) |
| Average Battery | Mean battery % across fleet |
| Task Completion Rate | Completed / (completed + failed) (%) |
| Avg Distance Per Task | Total distance / task count (meters) |

---

## 15. Warehouse Control System (WCS)

### Conveyor Controller
- Multiple segments with configurable speed (m/s)
- Start/stop/set_speed/maintenance per segment
- Jam simulation for resilience testing
- Package transfer between segments

### Sorter Engine
- Barcode → lane routing via regex pattern rules (max 500 rules)
- Handles misreads (empty barcode → default lane)
- Per-rule hit counts and error tracking

### Lane Manager
- 5 lane types: inbound, outbound, express, returns, staging
- Open/close/clear operations
- Package capacity tracking

### Package Tracker
- Full lifecycle: created → sorted → transferred → delivered
- Journey events with timestamps
- In-transit and at-location queries

---

## 16. Warehouse Management System (WMS)

### ERP Connectors (3 Adapters)

| Adapter | Protocol | Use Case |
|---------|----------|----------|
| WebhookAdapter | HTTP POST | Custom ERP integrations |
| SAPAdapter | RFC/REST | SAP S/4HANA integration |
| OdooAdapter | XML-RPC | Odoo ERP integration |

### Dead Letter Queue (DLQ)
- RabbitMQ-backed persistent error queue
- Failed orders can be retried individually
- DLQ count visible on dashboard

---

## 17. Inventory Management

### Core Features
- **SKU Catalog:** Product definitions from `configs/wms/sku_catalog.yaml`
- **Stock Levels:** Per-SKU quantities across all warehouse nodes
- **Putaway/Pick:** Receive (inbound) and pick (outbound) with validation
- **Transfer:** Move stock between nodes (creates two movement records)
- **Cycle Count:** Perform physical count, auto-adjust discrepancies

### Storage Optimizer
- **ABC Classification:** A = top 20% by pick frequency, B = next 30%, C = remaining 50%
- **Slotting Recommendations:** Move fast-movers closer to pick zones
- **Zone Balance:** Heatmap of inventory distribution, identifies over/under-stocked zones

### Replenishment Engine
- Scans all SKUs against reorder points
- Auto-generates replenishment orders when stock < reorder_point
- Status lifecycle: pending → in_progress → completed/cancelled

---

## 18. VDA5050 Protocol

### What Is VDA5050
Industry standard MQTT-based protocol for Automated Guided Vehicle (AGV) communication. Enables interoperability between different AGV manufacturers.

### Implementation
- **Gateway:** Translates internal orders → VDA5050 JSON
- **MQTT Broker:** Mosquitto on port 1883 (TCP), 9001 (WebSocket)
- **Topics:** `vda5050/v2.0.0/order/{manufacturer}/{serial}` etc.
- **Translator:** Converts `{source_node, dest_node}` → VDA5050 `{nodes, edges, actions}`

### Supported Messages
- **Order:** Navigation order (nodes, edges, actions)
- **InstantAction:** E-stop, pause, cancel (immediate, no queuing)
- **State:** AGV status, position, battery (from subscriptions)
- **Factsheet:** AGV capabilities declaration

### Limits
- Max 500 nodes per order
- Max 200 concurrent AGVs

---

## 19. Multi-Agent Path Finding (MAPF)

### CBS (Conflict-Based Search)
- **Type:** Optimal solver
- **Max agents:** 200
- **Algorithm:** Two-level search — high-level detects conflicts between agent paths, low-level replans individual agents via A*
- **Guarantee:** Finds shortest combined path

### PIBT (Priority Inheritance + Backtracking)
- **Type:** Real-time approximation
- **Max agents:** 500
- **Algorithm:** Priority-based, one-step-at-a-time, linear time complexity
- **Integration:** `/api/mapf/step` for 15Hz cycle integration

### Congestion Tracking
- Tracks node visit frequency after each solve/step
- Top 10 bottleneck nodes with traffic counts
- Heatmap data for traffic density visualization

---

## 20. Predictive Maintenance

### PredictiveEngine
- Component degradation modeling (wheels, motors, sensors, battery)
- Forecasts maintenance windows based on usage patterns
- MTBF (Mean Time Between Failures) tracking across fleet

### MaintenanceScheduler
- Schedule maintenance windows with start/end times
- Impact analysis: how does taking robot offline affect fleet KPIs?
- Supports complete/cancel lifecycle

### ComponentModel
- Per-component health tracking (wheels, bearings, sensors)
- Degradation curves based on distance, cycles, time
- Critical alerts when component health drops below threshold

---

## 21. Smart Charging

### 3 Charging Strategies

| Strategy | Description | Use Case |
|----------|-------------|----------|
| **Conservative** | Charge when < 50%, top up to 90% | Battery longevity |
| **Aggressive** | Charge when < 20%, full 100% charge | Maximum uptime |
| **Balanced** | Charge when < 30%, target 80% | Best trade-off |

### Battery Degradation Model
- Tracks charge cycles per robot
- Health degradation over time (capacity fade)
- Predicts replacement dates
- Temperature effects not yet implemented (see Appendix C: Known Limitations)

### Charge Queue Manager
- Queue robots at charge stations
- Priority-based: lower battery = higher priority
- Energy consumption forecasting

---

## 22. Human Dynamic Agents

### HumanAgentManager
- Track human workers in warehouse with positions
- Create/update/move/remove agents
- Movement pattern simulation

### SafetyZoneManager
- Define safety zones around humans
- Block warehouse nodes occupied by humans
- Nearby robot detection (configurable radius)

### InteractionManager
- Log all robot-human interactions
- Near-miss collision detection and statistics
- Safety audit trail

---

## 23. ROS2 Bridge

### Architecture
- Runs as separate Docker container (ros:humble)
- Connects to C++ FMS via HTTP (`FMS_URL=http://rdt:7012`)
- **Stub implementation** — no actual nav2 action client; returns simulated responses if rclpy unavailable
- No exposed ports (internal Docker network only)
- No CPU/memory resource limits configured (Docker defaults)
- No nav2 SendGoal action server integration yet — planned for future phase

### Topics

**Published (Gazebo → ROS2):**

| Topic | Type | Rate |
|-------|------|------|
| `/{robot_id}/odom` | nav_msgs/Odometry | 15 Hz |
| `/{robot_id}/lidar` | sensor_msgs/LaserScan | 10 Hz |
| `/{robot_id}/imu` | sensor_msgs/Imu | 100 Hz |

**Subscribed (ROS2 → Gazebo):**

| Topic | Type | Rate |
|-------|------|------|
| `/{robot_id}/cmd_vel` | geometry_msgs/Twist | ~15 Hz |

### TF Frames
```
/odom → /chassis → /lidar_link, /imu_link
```

---

## 24. React 3D Dashboard

### Dashboard Tabs

| Tab | Technology | Description |
|-----|-----------|-------------|
| **2D Grid** | Canvas/SVG | Top-down warehouse map with nodes (color-coded), edges, robot positions |
| **3D View** | Three.js | Interactive 3D scene with robot models, path highlighting, camera follow |
| **Designer** | Interactive editor | Drag-and-drop node placement, edge drawing, zone assignment |

### Dashboard Panels (12+)

| Panel | Location | Metrics |
|-------|----------|---------|
| Robot Status | Right panel (always visible) | ID, status, battery %, position, task, heartbeat |
| Task Queue | Right panel | Source, dest, priority, robot, status, ETA |
| Battery Levels | Row 2 | Fleet histogram, alerts for < 25% |
| Fleet Analytics | Row 2 | Tasks, throughput, avg time, avg battery, robot count |
| WES KPIs | Row 2 | Orders/hr, pick accuracy, throughput, cycle time |
| Wave Status | Row 2 | Pending/active/completed wave cards, release button |
| Heatmap Controls | Row 1 | Duration slider (1h/4h/24h), resolution control |
| Scenario Panel | Row 3 left | Create/run/compare scenarios |
| Scenario Comparison | Overlay | Full-screen side-by-side KPI charts |
| VDA5050 Panel | Row 3 right | Broker status, online/total AGV count |
| Congestion Panel | Row 4 left | MAPF hotspots, top bottleneck nodes |
| WMS Panel | Row 4 right | Connector type, DLQ count, last sync |

### 3D Features
- Robot models rendered in scene
- Camera follow mode (click robot → smooth camera interpolation)
- Path highlighting between source → destination
- Error boundary: crashes fall back to 2D with retry button

---

## 25. Analytics & Monitoring

### Real-Time KPIs

| Metric | Source | Update Rate |
|--------|--------|-------------|
| Fleet Utilization | MongoDB | 2 Hz (via WebSocket) |
| Throughput (orders/hr) | WES KPI Tracker | 1 Hz |
| Avg Cycle Time | Task timestamps | Per completion |
| Battery Distribution | Robot states | 2 Hz |
| Traffic Heatmap | MAPF Congestion | Configurable |
| A/B Strategy Comparison | Analytics service | On demand |

### Telemetry Storage (InfluxDB)

**Buckets:**
- `fleet_telemetry` — robot positions, battery, KPIs (7-day retention)
- `fms_performance` — FMS loop timing, latencies

**Measurements:**
```
robot_position,robot_id=robot_1,zone=ZONE_A x=12.5,y=8.3
battery_level,robot_id=robot_1 percent=85.2,temp=35.1
fms_cycle_time,component=pathfinding elapsed_ms=12.3
task_throughput orders_per_hour=240
```

### Grafana Dashboards (Pre-Configured)

- **Fleet Health:** Robot count, utilization, battery distribution
- **Throughput Trends:** Orders/hour over 24h
- **Performance:** FMS cycle times, path planning latency
- **Failure Analysis:** Faults, errors, DLQ
- **System Health:** MongoDB disk, Redis memory, InfluxDB retention

### Telemetry Export
- CSV export via `/api/telemetry/export?format=csv`
- Production telemetry export via `/api/telemetry/export/production`
- Scenario comparison export: JSON, CSV, or PDF

---

## 26. Warehouse Designer

### Interactive Layout Editor

**Backend endpoints:** `/api/designer/*`

**Features:**
- **Node Placement:** Drag-and-drop nodes of any type (pick, drop, shelf, charge, aisle, hub, staging)
- **Edge Drawing:** Connect nodes with directed weighted edges
- **Zone Assignment:** Group nodes into zones with type and priority
- **Validation:** Check for node uniqueness, edge validity, zone coverage, disconnected nodes
- **3D Validation:** Validates 3D layout, recommends charge station placement
- **Auto-Edge Generation:** Creates edges between nearby nodes by configurable max distance
- **Template System:** Pre-built templates in 4 categories:
  - Small (< 15 nodes)
  - Medium (15-30 nodes)
  - Large (31-60 nodes)
  - Industrial (production-specific layouts)
- **Scale Template:** Multiply node positions and add proportional nodes
- **Export:** Save as JSON config to `configs/warehouses/` or full bundle (warehouse + conveyor YAML + fleet)

---

## 27. Scenario Simulation & Fault Injection

### Scenario Management

Create simulation scenarios with configurable:
- Fleet size (number and types of robots)
- Warehouse configuration (which JSON map)
- Task allocation strategy (FIFO / nearest / priority-weighted)
- Order volume and distribution

**Workflow:**
```
Create Scenario → Run (inject orders → simulate → compute KPIs) → View Results → Compare
```

### Fault Injection (Resilience Testing)

| Fault Type | Description | Endpoint |
|------------|-------------|----------|
| `battery_drain` | Rapid battery depletion on specific robot | `POST /api/simulation/inject-fault` |
| `obstacle` | Spawn dynamic obstacle in robot path | Same |
| `network_loss` | Simulate TCP disconnect for robot | Same |
| `motor_fault` | Motor failure on specific robot | Same |

Each fault has configurable duration and target robot.

### Fault Injection Scenarios (4 Implemented)

The blueprint originally scoped 14 failure modes, but 4 are implemented as injectable faults:

| # | Scenario | Parameters | What It Tests |
|---|----------|------------|---------------|
| 1 | `battery_drain` | `robot_id`, `duration_s` | Rapid SoC depletion → auto-dock behavior |
| 2 | `obstacle` | `robot_id`, `duration_s` | Dynamic obstacle in path → replan / emergency stop |
| 3 | `network_loss` | `robot_id`, `duration_s` | TCP disconnect → heartbeat timeout → error state |
| 4 | `motor_fault` | `robot_id`, `duration_s` | Motor failure → behavior tree error recovery |

**Not yet implemented:** Sensor failure, barcode reader fault, MongoDB outage, RabbitMQ disconnect, conveyor jam cascade, multi-robot deadlock injection, charge station failure, zone boundary drift, MQTT broker loss, fleet-wide brownout. These were scoped in `blueprint/05_security.md` but not built.

---

## 28. Configuration System

### Configuration Hierarchy

```
configs/
├── warehouses/          # Warehouse graph definitions (JSON)
│   ├── simple_grid.json          # 25 nodes, 40 edges, 8 zones
│   ├── warehouse_distinct.json   # 40x30m, ~35 nodes
│   ├── production_50x60.json     # 50x60m, ~60 nodes
│   └── botvalley.json            # 150x200m, 100+ nodes
├── robots/              # Robot parameter definitions (YAML)
│   ├── differential_drive.yaml
│   ├── heavy_lifter.yaml
│   ├── light_courier.yaml
│   ├── forklift_heavy.yaml
│   ├── inspection_bot.yaml
│   ├── unidirectional.yaml
│   └── mixed_fleet_10.json       # Fleet composition
├── behavior_trees/      # BehaviorTree.CPP v4 XMLs
│   ├── default_amr.xml
│   └── default_agv.xml
├── wms/                 # WMS configuration
│   └── sku_catalog.yaml          # Product definitions
├── wcs/                 # WCS configuration
│   └── conveyor_layout.yaml      # Conveyor segment definitions
├── maintenance/         # Maintenance configuration
│   └── component_profiles.yaml   # Component degradation models
├── charging/            # Charging configuration
│   └── strategy_profiles.yaml    # Charging strategy definitions
└── fleet/               # Fleet presets
    └── default_mixed.json        # Default fleet composition
```

### Warehouse Config (JSON)

```json
{
  "name": "simple_grid",
  "grid_spacing_m": 1.0,
  "nodes": [
    {"id": "NODE_00", "x": 0, "y": 0, "type": "pick", "zone": "Z1"}
  ],
  "edges": [
    {"from": "NODE_00", "to": "NODE_01", "distance": 1.0}
  ],
  "zones": [
    {"id": "Z1", "name": "Pick Zone", "type": "pick", "nodes": ["NODE_00"]}
  ]
}
```

### Robot Config (YAML)

```yaml
model: heavy_lifter
motion:
  max_linear_velocity: 0.8
  max_angular_velocity: 1.57
  linear_acceleration: 1.0
  position_tolerance: 0.25
  angular_tolerance: 0.025
battery:
  charge_duration_s: 450
  discharge_duration_s: 60000
  critical_threshold_pct: 20
  motion_energy_factor: 1.02
  attachment_energy_factor: 1.02
sensors:
  lidar:
    range: 5.0
    fov: 360
  odometry: true
  imu: true
obstacle_thresholds:
  critical_m: 1.0
  warning_m: 2.0
  planning_m: 3.0
```

---

## 29. Database Architecture

### MongoDB Collections

| Collection | Writer | Reader | Purpose |
|------------|--------|--------|---------|
| `robots` | C++ (15Hz) | Python | Robot positions, battery, status, task |
| `tasks` | C++ + Python | Both | Task lifecycle (orders → assignments → completion) |
| `reservations` | C++ | Python | Node locks for collision avoidance |
| `telemetry` | C++ | Python | Raw sensor data |
| `commands` | Python | C++ | Queued robot actions |
| `fleet_metrics` | Python | Python | KPI snapshots |
| `wes_orders` | Python | Python | WES pipeline orders |
| `wcs_packages` | Python | Python | Package tracking |
| `wms_orders` | Python | Python | WMS synced orders |
| `scenarios` | Python | Python | Saved simulation scenarios |
| `wave_rules` | Python | Python | Wave generation rules |
| `inventory` | Python | Python | Stock levels + movements |

### Redis (Hot State Cache)

Python background task reads MongoDB agents collection, caches in Redis for sub-ms dashboard reads. Keys:
- `robot:{id}:state` — latest robot state
- `fleet:metrics` — aggregate fleet KPIs
- `telemetry:{id}:latest` — most recent telemetry point

**Redis Configuration:**
- Startup: `redis-server --requirepass ${REDIS_PASSWORD}`
- `maxmemory`: Not set (uses Redis default: unlimited)
- `eviction-policy`: Not set (uses Redis default: `noeviction`)
- Key TTL: No explicit TTL or `expire`/`setex` calls in Python code — keys persist until overwritten
- This is acceptable for simulation use; production deployment should set `maxmemory` and `allkeys-lru` eviction

### InfluxDB (Time-Series)

- **Org:** rdt
- **Bucket:** fleet_telemetry
- **Retention:** 7 days (configurable)
- **Write rate:** ~15Hz per robot (position, battery, velocity)

---

## 30. WebSocket Real-Time Streaming

### Connection

```
ws://localhost:8029/ws/fleet
```

Max 100 concurrent connections (DoS protection). Each message includes sequence number + timestamp.

### Event Types

```json
{"event": "robot_position", "data": {"robot_id": "robot_1", "x": 12.5, "y": 8.3, "node": "S_11", "battery_pct": 85.2}}
{"event": "task_update", "data": {"task_id": "task_42", "status": "in_progress", "assigned_robot": "robot_1", "progress_pct": 75}}
{"event": "fleet_metrics", "data": {"total_robots": 10, "active": 7, "idle": 2, "charging": 1, "throughput_orders_per_hr": 240}}
{"event": "collision_alert", "data": {"robot_ids": ["robot_3", "robot_5"], "collision_node": "S_22"}}
```

### Polling Fallback

If WebSocket unavailable, REST endpoints provide same data:
- `GET /api/fleet/status` — aggregate KPIs every 2s
- `GET /api/robots` — all robot positions
- `GET /api/tasks?status=in_progress` — active tasks

---

## 31. Testing & Quality

### Test Breakdown

| Category | Count | Framework | Location | Precision |
|----------|-------|-----------|----------|-----------|
| **C++ Core** | ~398 | gtest | `cpp/tests/test_*.cpp` | Approximate (from audit) |
| **Python API** | ~928 | pytest + httpx | `python/tests/test_*.py` (46 modules) | Approximate (from audit) |
| **E2E** | ~50 | Playwright | `e2e/`, `frontend/` | Approximate |
| **Gazebo Integration** | ~52 | pytest | `tests/` (9 files) | Approximate |
| **Total** | **~1,428+** | | **0 failures** | Sum of above; additional tests may exist in phase-specific outputs |

**Note:** Counts are approximate, compiled from external audit reports across 18 phases. No single `pytest` run covers all tests simultaneously since C++ (gtest) and Python (pytest) run in separate test harnesses. Some phase-specific tests may not be captured in the per-category breakdown.

### C++ Test Categories

| Area | Tests | Files |
|------|-------|-------|
| Network (TCP, REST) | 45 | `test_tcp.cpp`, `test_rest.cpp` |
| Navigation (A*, NodeRes, Graph) | 80 | `test_astar.cpp`, `test_node_reservation.cpp`, `test_graph_map.cpp` |
| Collision Detection | 60 | `test_obstacle_handler.cpp`, `test_motion_controller.cpp` |
| Behavior Trees | 40 | `test_bt_engine.cpp`, `test_action_nodes.cpp` |
| Battery Model | 50 | `test_battery.cpp`, `test_charging.cpp` |
| Fleet Management | 56 | `test_fleet_manager.cpp`, `test_task_manager.cpp` |
| QuadTree | 30 | `test_quadtree.cpp` |

### Python Test Categories

| Area | Count | Files |
|------|-------|-------|
| API Endpoints | 152 | `test_api.py`, per-router test files |
| WES/WCS/WMS | 200 | `test_wes.py`, `test_wcs.py`, `test_wms.py` |
| Intelligence (io-gita) | 150 | `test_iogita.py`, `test_zone_identifier.py` |
| VDA5050 | 100 | `test_vda5050.py`, `test_mqtt_client.py` |
| Maintenance | 80 | `test_maintenance.py`, `test_predictive_engine.py` |
| Charging | 70 | `test_charging.py`, `test_degradation.py` |
| Human Agents | 50 | `test_human_agents.py`, `test_safety_zones.py` |
| Inventory | 50+ | `test_inventory.py` |

### Quality Gates

- **85% minimum on FIRST external audit** (Kimi/Gemini/Codex)
- No MagicMock databases — real connections with graceful degradation
- No hardcoded values — all from config YAML/JSON
- No dead code — every function called AND tested
- All assertions check REAL values (not just `is not None`)
- All library APIs verified against actual docs/headers

### Running Tests

```bash
# C++
cd build && ctest --output-on-failure

# Python
cd python && pytest -v --tb=short

# E2E
npx playwright test --headed
```

---

## 32. Online Use Cases (Docker + Gazebo)

### What You Can Do With the Deployed System

#### 1. Full Fleet Simulation
- Launch fleet of robots in a Gazebo physics world (tested with 10, real-time up to ~20 within 67ms FMS budget; 50+ launches but exceeds real-time)
- Watch robots navigate, pick, place, charge in real-time 3D
- Monitor via React dashboard on `localhost:8029/dashboard`

#### 2. Warehouse Layout Design & Validation
- Design custom warehouse layouts in the Designer tab
- Validate 3D constraints and charge station placement
- Export configs and immediately simulate with robots

#### 3. Task Allocation Strategy Comparison
- Create scenarios with different strategies (FIFO vs nearest vs priority)
- Run both scenarios with same order volume
- Compare KPIs side-by-side (throughput, cycle time, utilization)
- Export comparison as CSV/PDF

#### 4. Order-to-Completion Pipeline Testing
- Inject orders via WES API
- Watch automatic wave creation → task generation → robot assignment
- Track full lifecycle: order → wave → task → robot picks up → delivers → complete
- Monitor KPIs in real-time

#### 5. VDA5050 AGV Protocol Testing
- Connect external AGV simulators via MQTT
- Send VDA5050 orders and instant actions
- Monitor AGV states through the dashboard

#### 6. Multi-Agent Path Planning Benchmarking
- Test CBS vs PIBT solvers with varying agent counts
- Measure solve times, conflict counts
- Identify congestion bottlenecks

#### 7. Fault Injection & Resilience Testing
- Inject battery drain, obstacles, network loss, motor faults
- Observe system recovery behavior
- Validate failover and error handling

#### 8. Conveyor & Sorter Simulation
- Configure conveyor layouts with sorter rules
- Run packages through barcode routing
- Test jam scenarios and emergency stops

#### 9. Inventory Management
- Manage SKU catalog, receive/pick/transfer inventory
- Run cycle counts with auto-adjustment
- Use ABC optimizer to improve slotting

#### 10. Predictive Maintenance Testing
- Simulate component degradation on robots
- Observe maintenance alert generation
- Schedule maintenance windows and assess fleet impact

#### 11. Human-Robot Interaction Testing
- Add human agents to the warehouse simulation
- Test safety zone enforcement
- Monitor near-miss collision statistics

#### 12. ERP Integration Testing
- Connect via webhook, SAP, or Odoo adapters
- Test order sync, DLQ handling, retry logic

#### 13. Energy Management
- Test charging strategies (conservative/aggressive/balanced)
- Monitor battery health degradation over time
- Forecast energy consumption for fleet planning

#### 14. Real-Time Monitoring
- Grafana dashboards for telemetry visualization
- InfluxDB time-series queries
- WebSocket live feeds for custom monitoring tools

---

## 33. Performance Benchmarks

### FMS Cycle Timing

| Fleet Size | Avg Cycle Time | Within Budget? |
|------------|---------------|----------------|
| 1 robot | 10-12ms | Yes (55ms headroom) |
| 5 robots | 20-25ms | Yes (42ms headroom) |
| 10 robots | 40-50ms | Yes (17ms headroom) |
| 20 robots | 60-65ms | Marginal (2ms headroom) |
| 50+ robots | >100ms | No (requires optimization) |

### Component Timing

| Component | Typical | Peak |
|-----------|---------|------|
| TCP Message Processing | 1-2ms | 3ms |
| State Update | 3-5ms | 8ms |
| Behavior Tree Tick | 3-5ms | 10ms |
| Task Allocation | 2-4ms | 5ms |
| A* Path Planning | 5-15ms | 20ms |
| Node Reservation | 5-15ms | 20ms |
| Command Dispatch | 2-3ms | 5ms |
| io-gita Zone ID | 0.008ms | 0.02ms |

### Scalability Limits

| Resource | Tested Limit | Bottleneck |
|----------|-------------|------------|
| Robots | 10 tested, ~20 real-time max, 50+ exceeds 67ms budget | FMS loop time |
| WebSocket Connections | 100 | Broadcast bandwidth |
| MongoDB Documents | Millions | Index on robot_id, task_id |
| InfluxDB Retention | 7 days (configurable) | Disk space |
| MAPF Agents (CBS) | 200 | Solver time exponential |
| MAPF Agents (PIBT) | 500 | Linear time, practical limit |
| Warehouse Nodes | 100+ | A* performance |
| VDA5050 AGVs | 200 | MQTT broker throughput |

---

## 34. Project File Structure

```
case-studies/project_29_full_robotics/
├── robotic_digital_twin_simulation/
│   ├── cpp/                              # C++ FMS core (12,287 LOC)
│   │   ├── include/rdt/
│   │   │   ├── fleet/FleetManager.h      # 15Hz orchestration loop
│   │   │   ├── fleet/TaskManager.h       # Task allocation
│   │   │   ├── navigation/AStar.h        # Pathfinding
│   │   │   ├── navigation/NodeReservation.h  # Deadlock prevention
│   │   │   ├── navigation/GraphMap.h     # Warehouse graph
│   │   │   ├── navigation/QuadTree.h     # Spatial index
│   │   │   ├── behavior/BTEngine.h       # Behavior tree engine
│   │   │   ├── robot/RobotState.h        # State machine
│   │   │   ├── robot/MotionController.h  # P-controller
│   │   │   ├── robot/BatteryModel.h      # Energy simulation
│   │   │   ├── robot/ObstacleHandler.h   # Safety zones
│   │   │   ├── network/TCPServer.h       # TCP:65123
│   │   │   └── network/RESTServer.h      # REST:7012
│   │   ├── src/                          # Implementation files
│   │   ├── tests/                        # 398 gtest tests
│   │   └── CMakeLists.txt
│   │
│   ├── python/                           # Python FastAPI (45,791 LOC)
│   │   ├── app/
│   │   │   ├── main.py                   # App startup, 33 service initializers
│   │   │   ├── config.py                 # Pydantic Settings
│   │   │   ├── auth.py                   # API key middleware
│   │   │   ├── websocket.py              # WebSocket manager
│   │   │   ├── routes/                   # 28 route modules (~118 endpoints)
│   │   │   └── models/                   # Pydantic schemas
│   │   ├── wes/                          # Warehouse Execution System
│   │   ├── wcs/                          # Warehouse Control System
│   │   ├── wms/                          # Warehouse Management System
│   │   ├── vda5050/                      # VDA5050 MQTT protocol
│   │   ├── intelligence/iogita/          # Zone intelligence (KDTree v5)
│   │   ├── services/
│   │   │   ├── maintenance/              # Predictive maintenance
│   │   │   ├── charging/                 # Smart charging
│   │   │   ├── human_agents/             # Human-robot safety
│   │   │   └── simulation/              # Sim control
│   │   ├── ros2_bridge/                  # ROS2 integration
│   │   ├── monitoring/                   # Telemetry export
│   │   ├── designer/                     # Layout editor backend
│   │   ├── tests/                        # 928 pytest tests (46 modules)
│   │   └── requirements.txt
│   │
│   ├── frontend/                         # React 3D Dashboard
│   │   ├── src/
│   │   │   ├── components/               # 12+ UI panels
│   │   │   │   ├── Warehouse2D.tsx
│   │   │   │   ├── Warehouse3D.tsx
│   │   │   │   ├── Designer.tsx
│   │   │   │   ├── RobotStatus.tsx
│   │   │   │   └── ...
│   │   │   ├── hooks/
│   │   │   │   ├── useFleetWebSocket.ts
│   │   │   │   └── useRestPolling.ts
│   │   │   └── types.ts
│   │   ├── dist/                         # Production bundle
│   │   └── package.json
│   │
│   ├── gazebo/
│   │   ├── worlds/                       # 6 SDF world files
│   │   ├── models/
│   │   │   ├── industrial/                  # Heavy Lifter, Light Courier, Fork AMR, Omni Carrier, High-Speed
│   │   │   └── generic/                  # DiffDrive AMR, Uni AGV
│   │   ├── scripts/generate_world.py
│   │   └── launch.py
│   │
│   ├── docker/
│   │   ├── docker-compose.yml            # 8 services
│   │   ├── Dockerfile                    # Multi-stage (C++ builder + runtime)
│   │   ├── start.sh                      # Process startup
│   │   ├── .env.docker.example           # Env template
│   │   ├── mosquitto/mosquitto.conf      # MQTT config
│   │   └── grafana/provisioning/         # Pre-configured dashboards
│   │
│   ├── configs/
│   │   ├── warehouses/                   # Warehouse JSON definitions
│   │   ├── robots/                       # Robot YAML parameters
│   │   ├── behavior_trees/               # BTCPP v4 XMLs
│   │   ├── wms/                          # SKU catalog
│   │   ├── wcs/                          # Conveyor layout
│   │   ├── maintenance/                  # Component profiles
│   │   └── charging/                     # Strategy profiles
│   │
│   └── CLAUDE.md                         # Project-specific rules
│
├── Main_robotics/
│   ├── fleet_core/                       # Production C++ FMS (200K LOC)
│   │   ├── src/
│   │   │   ├── fleet/                    # FleetManager, COPP
│   │   │   ├── task/                     # TaskManager, TaskPool
│   │   │   ├── graph/                    # A*, NodeReservation
│   │   │   ├── robot/                    # State machine, drivers
│   │   │   ├── network/                  # TCP, REST, RabbitMQ
│   │   │   └── database/                # MongoDB driver
│   │   ├── fleet_core_assets/
│   │   │   └── models/behavior/          # BehaviorTree XMLs
│   │   └── CMakeLists.txt
│   ├── docs_fleet_core-main/             # 10 deep-dive analysis docs
│   └── files/                            # Onboarding docs
│
├── docker/
│   ├── docker-compose.yml                # Alternative compose (top-level)
│   └── Dockerfile
│
├── io-gita-v2/                   # io-gita compiled binary
├── iogita_kdtree_industrial/                # KDTree zone intelligence
├── maps/                                 # Warehouse graph configs
├── behavior_trees/                       # Behavior tree XMLs
├── tests/                                # Integration tests (9 files)
│
├── blueprint/                            # Blueprint documents
│   ├── 00_manifest.md
│   ├── 01_problem_and_scope.md
│   ├── 02_architecture.md
│   ├── 03_data_contracts.md
│   ├── 05_security.md
│   ├── 07_testing.md
│   ├── 09_implementation.md
│   └── 10_benchmarks.md
│
├── FEATURE_TABLE.md                      # 146-feature reference table
├── SUMMARY.md                            # Project summary
├── PROJECT_29_COMPLETE_REFERENCE.md      # THIS DOCUMENT
└── CLAUDE.md                             # Factory project rules
```

---

## 35. Quick Start Guide

### Prerequisites
- Docker Desktop (4+ CPU, 8+ GB RAM allocated)
- 20+ GB free disk space
- Linux x86_64 recommended (Gazebo Fortress requirement)
  - macOS/Windows: run via Docker Desktop or WSL2

### Launch

```bash
# 1. Navigate to project
cd case-studies/project_29_full_robotics/robotic_digital_twin_simulation

# 2. Set up environment
cp docker/.env.docker.example docker/.env
# Edit docker/.env → change all "changeme" passwords for production

# 3. Start all 8 services
docker compose -f docker/docker-compose.yml up --build -d

# 4. Wait for health (30s for C++ compile + startup)
docker compose ps                    # All services should be "Up"
curl http://localhost:8029/health    # Should return 200 with service statuses

# 5. Access points
open http://localhost:8029/dashboard  # React 3D Dashboard
open http://localhost:8029/docs       # API Documentation (Swagger)
open http://localhost:3000            # Grafana (admin/changeme)
open http://localhost:15672           # RabbitMQ Management (fms/changeme)
```

### First Steps After Launch

```bash
# Check fleet status
curl http://localhost:8029/api/fleet/status

# View warehouse map
curl http://localhost:8029/api/map

# Inject orders into WES pipeline
curl -X POST http://localhost:8029/api/wes/inject-orders \
  -H "Content-Type: application/json" \
  -d '{"num_orders": 10, "type": "mixed"}'

# Create and release a wave
curl -X POST http://localhost:8029/api/wes/waves
curl -X POST http://localhost:8029/api/wes/waves/{wave_id}/release

# Watch robots execute tasks on the dashboard
open http://localhost:8029/dashboard

# Run a scenario comparison
curl -X POST http://localhost:8029/api/scenarios \
  -d '{"name": "fifo_test", "fleet_size": 10, "strategy": "fifo"}'
curl -X POST http://localhost:8029/api/scenarios/{id}/run
```

### Stopping

```bash
docker compose -f docker/docker-compose.yml down
# Data persists in Docker volumes (mongo_data, influx_data, grafana_data)
```

---

## Appendix A: Architectural Decision Records (ADRs)

### ADR-001: Compile Actual fleet_core C++ — No Rewrites
**Decision:** Compile and run the actual production fleet_core C++ code inside Docker. Python is ONLY for new layers.
**Reason:** Sim-to-real gap = 0% for fleet logic. Same binary, same behavior.

### ADR-002: MongoDB as IPC (No pybind11)
**Decision:** Python reads fleet state from MongoDB (same DB fleet_core C++ writes to). No pybind11, no shared memory.
**Reason:** fleet_core already writes ALL state to MongoDB at 15Hz. Zero new IPC needed.

### ADR-003: io-gita as CORE (Not Optional)
**Decision:** io-gita sg_engine compiled binary is the actual zone identifier. Not optional.
**Reason:** User requirement. Removing it must break the system.

### ADR-004: Three Processes (C++, Gazebo, Python)
**Decision:** fleet_core C++, Gazebo, and FastAPI Python run as 3 separate OS processes in Docker.
**Reason:** fleet_core is designed as a standalone process. Gazebo is a separate process. Python bridges them.

### ADR-005: Gazebo Fortress Over Webots/Isaac Sim
**Decision:** Use Gazebo Fortress (ignition-gazebo) for physics simulation.
**Reason:** Native SDF support, ODE physics at 1kHz, mature ROS2 ecosystem integration, open source, runs headless in Docker. Isaac Sim requires NVIDIA GPU; Webots lacks fleet-scale simulation support.

### ADR-006: InfluxDB Over Prometheus/TimescaleDB
**Decision:** Use InfluxDB 2 for time-series telemetry storage.
**Reason:** Purpose-built for time-series with built-in retention policies (7-day default), native Grafana integration, simple HTTP write API. Prometheus is pull-based (wrong model for push telemetry). TimescaleDB adds PostgreSQL overhead unnecessary for simulation.

### ADR-007: Mosquitto for VDA5050 MQTT
**Decision:** Use Eclipse Mosquitto 2 as MQTT broker for VDA5050 protocol.
**Reason:** Lightweight (<10MB), supports MQTT 5.0, WebSocket bridge on port 9001, password auth with SCRAM-SHA-256. VDA5050 standard requires MQTT — Mosquitto is the reference implementation.

### ADR-008: MAPF Dual Solver (CBS + PIBT)
**Decision:** Implement both CBS (optimal) and PIBT (real-time) solvers for multi-agent path finding.
**Reason:** CBS guarantees shortest combined path but is exponential beyond 200 agents. PIBT runs in linear time for 500+ agents but is suboptimal. Providing both lets users choose speed vs optimality per use case.

### ADR-009: React 18 + Vite + Three.js for Dashboard
**Decision:** React 18 with Vite bundler, Tailwind CSS, and Three.js for 3D rendering.
**Reason:** Vite provides instant HMR during development. React component model fits panel-based dashboard. Three.js enables 3D warehouse visualization without WebGL boilerplate. Tailwind eliminates CSS file proliferation.

### ADR-010: FastAPI Over Flask/Django
**Decision:** Use FastAPI as the Python API framework.
**Reason:** Native async support (essential for WebSocket + MongoDB motor driver), automatic OpenAPI docs at `/docs`, Pydantic model validation, and sub-ms request overhead. Django too heavy for a thin API wrapper; Flask lacks native async.

### ADR-011: Redis for Hot State (Not Memcached)
**Decision:** Use Redis 7 as hot state cache for robot positions and telemetry.
**Reason:** Supports structured data types (hashes, sorted sets) beyond simple key-value. Persistence option if needed. Same Redis instance can serve both cache and pub/sub if WebSocket broadcast scales. Memcached is key-value only.

---

## Appendix B: Security

### Implemented Security Measures

| Layer | Measure | Implementation | Status |
|-------|---------|---------------|--------|
| **API Authentication** | API key via `X-API-Key` header | `python/app/auth.py` — `APIKeyHeader` | Conditional (disabled when `API_KEY=disabled`) |
| **CORS** | Allowed headers: `X-API-Key`, `Content-Type` | `python/app/main.py` CORSMiddleware | Active |
| **MQTT Auth** | Password-protected broker | `docker/mosquitto/passwd` — SCRAM-SHA-256 | Active |
| **MongoDB Auth** | Username/password via env vars | `MONGO_USER`/`MONGO_PASSWORD` in docker-compose | Active |
| **Redis Auth** | Password-protected | `--requirepass ${REDIS_PASSWORD}` | Active |
| **RabbitMQ Auth** | Username/password via env vars | `RABBITMQ_DEFAULT_USER`/`RABBITMQ_DEFAULT_PASS` | Active |
| **Secrets Management** | `.env` files (gitignored) | `docker/.env.docker.example` as template | Active |
| **Network Isolation** | All ports bind to `127.0.0.1` | docker-compose port mappings | Active |

### Protected Endpoints (Require API Key)

All mutating endpoints when `API_KEY` is set:
- `POST /api/robots/{id}/command`
- `POST /api/wes/inject-orders`
- `POST /api/tasks`, `DELETE /api/tasks/{id}`, `POST /api/tasks/{id}/cancel`
- `POST /api/simulation/start`, `/stop`, `/inject-fault`
- `POST /api/vda5050/orders`, `/instant-actions`

### Not Implemented (Simulation-Grade Limitations)

| Gap | Description | Impact |
|-----|-------------|--------|
| No TLS/SSL | All traffic is HTTP/unencrypted | Acceptable for localhost simulation; requires reverse proxy (nginx) for production |
| No JWT/OAuth | Simple API key only, no token expiry | Sufficient for simulation; production needs proper auth |
| No Rate Limiting | No request throttling | DoS risk if exposed publicly |
| No Audit Logging | Auth failures not logged | No forensic trail |
| No Request Sanitization | No explicit input validation beyond Pydantic | Pydantic models provide type safety but no XSS/injection guards |

---

## Appendix C: Known Limitations & Future Work

| Area | Limitation | Current State | Future Enhancement |
|------|-----------|---------------|-------------------|
| Fleet Scale | 67ms budget exceeded at 20+ robots | 10 robots tested, ~20 real-time max | Batch task allocation, A* caching, lazy BT eval |
| Motion Control | P-controller with acceleration limiting | Jerky motion on curves | MPC + OSQP (planned Phase 7 enhancement) |
| ROS2 Integration | Stub implementation, no actual nav2 | Simulated mode only | Full nav2 SendGoal action server |
| Sensor Realism | Gaussian noise only | No occlusion, no ray casting delays | Raycast occlusion model, multi-bounce |
| Battery Model | Fixed rate, no temperature dependence | Linear charge/discharge | Temperature-dependent degradation curves |
| Fault Injection | 4 of 14 blueprint scenarios built | battery, obstacle, network, motor | Sensor fault, DB outage, multi-robot deadlock, etc. |
| Security | Simulation-grade (no TLS, no JWT) | API key + password auth | TLS termination, OAuth2, rate limiting |
| Cold Start | Synthetic zone identification | Type-based patterns, not real Gazebo raycast | Bridge real LiDAR scans to io-gita training |

---

## Appendix D: Port Reference

| Port | Protocol | Service | Access |
|------|----------|---------|--------|
| 65123 | TCP | C++ FMS (robot ProtocolV1) | localhost only |
| 7012 | HTTP | C++ REST API | localhost only |
| 8029 | HTTP/WS | Python FastAPI + Dashboard | localhost only |
| 27017 | MongoDB | State database | localhost only |
| 5672 | AMQP | RabbitMQ | localhost only |
| 15672 | HTTP | RabbitMQ Management UI | localhost only |
| 6380 | Redis | Hot state cache | localhost only |
| 8086 | HTTP | InfluxDB | localhost only |
| 1883 | MQTT | Mosquitto (VDA5050) | localhost only |
| 9001 | WebSocket | Mosquitto WS | localhost only |
| 3000 | HTTP | Grafana | localhost only |
| 5199 | HTTP | React Dashboard (dev server) | localhost only |

---

---

# P29a EVOLUTION — Agnostic Platform + Web SaaS

> Everything above describes P29 (what was built and proven). Everything below describes P29a (what we're building next).

---

## E1. The Goal

Transform P29 from a single-vendor simulation into a **web-based SaaS platform** where:
- **Any robot** plugs in via YAML config (differential, omni, ackermann, custom)
- **Any warehouse** loads via JSON graph or DXF floor plan import
- **Any ERP/WMS** connects via 10-field universal order mapping
- **Users sign up**, upload their configs, run simulations, watch 3D in their browser

## E2. What Changes (85% stays, 15% evolves)

| Dimension | P29 (Now) | P29a (Target) |
|-----------|-----------|---------------|
| Robot | 70% agnostic | 95% — MotionControllerFactory + ProtocolAdapter |
| Map | 95% agnostic | 98% — generic world generator + DXF import |
| WMS | 98% agnostic | 100% — adapter registry + 10-field standard order |
| Vendor refs | 35+ files | Zero — all vendor artifacts archived |
| Deployment | Docker localhost | Per-user isolated containers |
| Frontend | Dashboard only | Signup + onboarding wizard + dashboard |
| 3D Rendering | Primitive boxes | GLTF models loaded via Three.js |

## E3. User Journey

```
1. SIGN UP       → Email + password
2. CHOOSE WAREHOUSE → Template / Upload JSON / Draw in designer / Import DXF
3. CHOOSE ROBOTS    → Generic type (sliders) / Upload custom YAML + SDF
4. CONNECT WMS      → Manual CSV / Webhook URL / 10-field ERP mapping form
5. RUN SIMULATION   → Click Start → Docker spins up → Gazebo headless → Dashboard streams
6. RESULTS          → PDF/CSV download / Compare scenarios / Tune and re-run
```

## E4. Architecture

```
BROWSER (user's GPU)                    CLOUD (per user, zero GPU)
┌──────────────────────┐               ┌──────────────────────────────┐
│ React 19 + Three.js  │               │ Docker Container (isolated)  │
│                      │               │                              │
│ Login / Signup       │               │ C++ FMS (15Hz headless)      │
│ Onboarding Wizard    │  REST + WS    │ Python FastAPI (~118 EP)     │
│ Dashboard (12 panels)│◄────────────▶│ Gazebo Fortress (no GUI)     │
│ 3D View (GLTF, 60fps│               │ MongoDB, Redis, RabbitMQ     │
│   WebGL on user GPU) │               │ Mosquitto (VDA5050 MQTT)     │
│                      │               │                              │
│ Rendering: FREE      │               │ ~3GB RAM, ~2 CPU, ~$5-10/mo │
└──────────────────────┘               └──────────────────────────────┘
```

Physics on server (headless). Rendering in browser (Three.js). Zero server GPU.

## E5. WMS Universal Order (10 Fields)

Any ERP in the world sends the same 10 fields — just mapped differently:

| # | Field | Required | Example |
|---|-------|----------|---------|
| 1 | `order_id` | Yes | `SO-2024-00451` |
| 2 | `sku` | Yes | `WIDGET-A100` |
| 3 | `qty` | Yes | `5` |
| 4 | `from_location` | Yes | `SHELF-A3-02` |
| 5 | `to_location` | Yes | `STAGING-DOCK-1` |
| 6 | `priority` | No | `urgent` / `normal` / `low` |
| 7 | `order_type` | No | `pick` / `putaway` / `replenish` / `move` |
| 8 | `due_by` | No | `2026-04-02T18:00:00Z` |
| 9 | `weight_kg` | No | `12.5` |
| 10 | `reference` | No | `CUST-AMAZON-B42` |

Each ERP gets a YAML mapping file (`configs/wms/translation_rules/sap.yaml`) that translates their field names to ours. Dashboard has a 10-field form for non-devs.

## E6. Phase Plan Summary (9 Phases, 68 Tasks, 23 Days)

| Phase | Name | Days | Key Deliverable |
|-------|------|------|-----------------|
| 0 | Foundation + Vendor Cleanup | 2 | Zero vendor refs, ProtocolAdapter, standard order schema |
| 1 | Robot Agnostic | 3 | MotionControllerFactory, LocalizationEngine, ChargeStrategy |
| 2 | Map Agnostic | 2 | Generic world generator, DXF import, zone templates |
| 3 | WMS Agnostic | 2 | YAML translation rules, RoutingStrategy, multi-ERP |
| 4 | Auth + User Accounts | 3 | JWT auth, file upload API, per-user storage |
| 5 | Container Orchestration | 3 | Per-user Docker, port allocation, nginx routing |
| 6 | Onboarding Wizard | 3 | 4-step React wizard (warehouse → robots → WMS → launch) |
| 7 | 3D Visual Upgrade | 2 | GLTF robot models, warehouse furniture |
| 8 | Polish + E2E Testing | 3 | Multi-user load test, reports, error recovery |
| **Total** | | **23 days** | **Web-based SaaS simulation platform** |

## E7. SaaS Resource Estimates

| Metric | Per User | 10 Users | 100 Users |
|--------|----------|----------|-----------|
| RAM | ~3 GB | 30 GB | 300 GB |
| CPU | ~2 cores | 20 cores | 200 cores |
| GPU | 0 | 0 | 0 |
| Cost/month | ~$5-10 | ~$50-100 | ~$500-1000 |
| Startup | ~60s | ~60s | ~60s |

---

*Full annotated project tree and detailed task breakdown: see `P29a_DELTA_BLUEPRINT_02-04-2026.md`*

*Project 29a WRIE — Warehouse Robotics Intelligence Engine — Agnostic Platform Edition*
*Built by the Autonomous Factory | Updated: 02-04-2026*

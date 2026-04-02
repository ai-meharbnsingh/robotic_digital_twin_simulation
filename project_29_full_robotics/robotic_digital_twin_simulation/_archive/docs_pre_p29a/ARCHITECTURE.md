# P29 WRIE — Final Architecture

**Warehouse Robotics Intelligence Engine**
10-robot fleet | 118 REST endpoints | C++ FMS at 15Hz | io-gita zone intelligence | VDA5050

```
Tests: 1567 passed | 0 failed | 0 skipped
Stack: C++17 + Python 3.11 + React 18 + Docker (8 services)
Ports: 65123 (TCP) | 7012 (C++ REST) | 8029 (FastAPI) | 3000 (Grafana)
```

---

## System Layers

```
                    +---------------------------+
                    |   React Dashboard (:3000)  |   <- frontend/
                    |   WebSocket + REST polls   |
                    +------------+--------------+
                                 |
                    +------------+--------------+
                    |  Python FastAPI (:8029)    |   <- robotic_digital_twin_simulation/python/
                    |  118 endpoints, 32 routers |
                    +--+------+------+------+---+
                       |      |      |      |
              +--------+  +---+--+ +-+----+ +------+
              | WES    |  | WCS  | | WMS  | | VDA  |
              | orders |  | conv | | inv  | | 5050 |
              +--------+  +------+ +------+ +------+
                       |
                    +--+------------------------+
                    | io-gita Zone Intelligence  |   <- io-gita-addverb-v2/fleet/
                    | <1ms zone ID, 16 features  |
                    +--+------------------------+
                       |
              +--------+--------+     +---------+
              | MongoDB (IPC)   |     | Redis   |
              | C++ writes,     |     | hot     |
              | Python reads    |     | state   |
              +---------+-------+     +---------+
                        |
                    +---+-------------------+
                    | C++ fleet_core (:7012) |   <- Main_robotics/fleet_core/
                    | 15Hz loop, A*, BTCPP   |
                    | TCP :65123 (ProtocolV1) |
                    +---+-------------------+
                        |
              +---------+---------+
              | Gazebo Fortress   |   <- robotic_digital_twin_simulation/gazebo/
              | Physics, sensors  |
              +---------+---------+
                        |
              +---------+---------+
              | InfluxDB + Grafana|   <- time-series telemetry
              +-------------------+
```

---

## Directory Tree

```
project_29_full_robotics/
```

### Root Config & Tests

```
conftest.py                              — Root pytest config: sys.path injection, infra detection
pyproject.toml                           — Unified pytest settings: 5 testpaths, markers, importlib mode
requirements.txt                         — Python dependencies (FastAPI, motor, redis, influxdb-client, etc.)
ARCHITECTURE.md                          — This file
FEATURE_TABLE.md                         — 118 endpoint feature checklist with status
SUMMARY.md                               — Quick reference card
SYNTHETIC_DATA_AUDIT_REPORT.md           — Kimi forensic audit findings (Mar 31)
```

### Docker (8 services)

```
docker/
  docker-compose.yml                     — MongoDB + RabbitMQ + Redis + InfluxDB + Grafana + WRIE app
  Dockerfile                             — Multi-stage: C++ fleet_core build (Ubuntu 22.04) + Python + Gazebo
  start.sh                               — Container entrypoint: starts fmsApp C++ then uvicorn Python
  .env.example                           — Environment variable template (passwords, tokens)
```

### C++ Fleet Core (Production Engine)

```
Main_robotics/fleet_core/
  CMakeLists.txt                         — CMake build: vcpkg deps, fmsApp + fmsSimulatorApp targets
  src/
    apps/fmsApp/                         — Main executable: fleet management server entry point
    core/application/Application.cpp     — 15Hz main loop: tick fleet, dispatch tasks, update telemetry
    graph/
      nodeReservation/
        CoupledNodeReservation.cpp       — ILP-based multi-robot node reservation (<15ms)
        CoupledEdgeReservation.cpp       — Edge-level collision avoidance
    task/                                — Task lifecycle: create, assign, execute, complete, cancel
    network/                             — TCP ProtocolV1 (33 fields, CRC32) + REST API server
    path/                                — A* pathfinding on warehouse graph
    robot/                               — Robot state machine, kinematics, battery model
    simulation/                          — Simulation mode: virtual robots, accelerated time
    wcs/elements/conveyor/Conveyor.cpp   — Conveyor belt control logic
    drivers/barcode/BarcodeDriver.cpp    — Barcode scanner driver (PGV, Irayple)
    plot/entitiesBase/obstacle/          — Obstacle detection and footprint management
    database/                            — MongoDB persistence layer
  fleet_core_assets/
    models/behavior/
      agentBehaviorAmr.xml               — BehaviorTree.CPP v4 XML for AMR robots
      agentBehaviorZippyX.xml            — BehaviorTree.CPP v4 XML for Zippy robots
    config/                              — Robot parameter YAML files (ActionCodes, params)
```

### Python FastAPI (118 Endpoints)

```
robotic_digital_twin_simulation/python/
  app/
    main.py                              — FastAPI boot: loads configs, connects MongoDB/Redis/InfluxDB, mounts 32 routers
    config.py                            — Settings from env vars; loads warehouse JSON + robot YAML at import time
    auth.py                              — API key / JWT authentication middleware
    websocket.py                         — WebSocket server: real-time fleet metrics broadcast
    routes/
      __init__.py                        — Router aggregator: mounts all 32 sub-routers
      fleet.py                           — GET /api/fleet/status — fleet summary (total, active, charging)
      robots.py                          — CRUD /api/robots — individual robot telemetry + commands
      tasks.py                           — CRUD /api/tasks — task queue, dispatch, cancel
      maps.py                            — GET /api/map — warehouse graph, nodes, zones, pathfinding
      simulation.py                      — POST /api/sim/start|stop — simulation control
      iogita.py                          — GET /api/iogita/zones — io-gita zone classification results
      vda5050.py                         — VDA5050 order/state management via MQTT gateway
      wcs.py                             — GET /api/wcs — conveyor status, lanes, packages
      wes.py                             — POST /api/wes/orders — order injection, KPIs, wave planning
      wms.py                             — GET /api/wms — WMS connector status, DLQ, webhook
      inventory.py                       — CRUD /api/inventory — SKU catalog, stock levels, cycle count
      charging.py                        — GET /api/charging — battery status, charge queue, strategy
      maintenance.py                     — GET /api/maintenance — component health, RUL predictions
      human_agents.py                    — GET /api/human-agents — worker simulation status
      analytics.py                       — GET /api/analytics — KPI dashboards, throughput metrics
      heatmap.py                         — GET /api/heatmap — congestion/utilization visualization
      mapf.py                            — POST /api/mapf — multi-agent pathfinding solver
      telemetry.py                       — GET /api/telemetry — raw sensor data stream
      telemetry_export.py                — POST /api/telemetry/export — InfluxDB metrics export
      events.py                          — GET /api/events — event log queries
      reservations.py                    — GET /api/reservations — node/resource reservations
      stats.py                           — GET /api/stats — aggregate throughput statistics
      scenarios.py                       — POST /api/scenarios — scenario builder
      waves.py                           — POST /api/waves — wave planning and execution
      config_routes.py                   — GET /api/config — warehouse/robot config loader
      designer.py                        — POST /api/designer — layout designer backend
      ros2.py                            — GET /api/ros2 — ROS2 bridge status
      order_import.py                    — POST /api/orders/import — ERP order ingestion
```

### Services (Business Logic)

```
  services/
    simulation/
      fms_bridge.py                      — ProtocolV1 TCP bridge to C++ FMS + virtual robot fleet manager
      warehouse_generator.py             — Creates warehouse graph from JSON config files
      task_dispatcher.py                 — Assigns tasks to robots via A* pathfinding
      fleet_config_loader.py             — Loads robot specs from YAML configs
      gazebo_bridge.py                   — Python-Gazebo communication (topic pub/sub)
      real_gazebo_bridge.py              — Real Gazebo physics integration with sensor data
      production_scenario.py             — Production stress test scenario runner
      fault_scheduler.py                 — Injects faults (battery, motor, sensor) on timeline
      fault_schedule_validator.py        — Validates fault schedule JSON against schema
      validator.py                       — Config file validation
      subsystem_activator.py             — Enables/disables WCS, WES, WMS, charging subsystems
    charging/
      strategy_engine.py                 — Charging decision: when to charge, which station, priority
      degradation_model.py               — Battery aging: cycle count, temperature, capacity fade
      queue_manager.py                   — Charger queue: FIFO with priority override
    maintenance/
      predictive_engine.py               — Remaining Useful Life (RUL) estimation
      component_model.py                 — Component wear curves (motor, wheel, sensor)
      scheduler.py                       — Maintenance window scheduling
    human_agents/
      worker_model.py                    — Human worker behavior simulation
      safety_zone.py                     — Human-robot collision avoidance zones
      interaction_manager.py             — Human-robot interaction events
```

### Warehouse Systems

```
  wcs/                                   — Warehouse Control System
    conveyor_controller.py               — Conveyor belt start/stop/speed control
    lane_manager.py                      — Lane allocation and flow control
    package_tracker.py                   — Package tracking on conveyor network
    sorter_engine.py                     — Sorting/diverting logic at junctions

  wes/                                   — Warehouse Execution System
    order_generator.py                   — Creates pick/place orders from demand
    task_generator.py                    — Converts orders into robot tasks
    mapf_solver.py                       — Multi-Agent Path Finding (CBS algorithm)
    pibt_solver.py                       — Priority Inheritance with Backtracking solver
    wave_engine.py                       — Wave batching: group orders by zone/priority
    kpi_tracker.py                       — Throughput, latency, utilization metrics
    congestion_tracker.py                — Bottleneck detection by zone
    report_generator.py                  — Post-simulation reports (CSV, JSON)
    scenario_manager.py                  — Test scenario configuration
    scenario_runner.py                   — Executes scenario step-by-step
    warehouse_validator.py               — Validates warehouse JSON (graph connectivity, zones)

  wms/                                   — Warehouse Management System
    connector.py                         — External system webhook/REST client
    inventory_manager.py                 — Bin/location/SKU tracking
    order_translator.py                  — ERP order format to internal task format
    storage_optimizer.py                 — Optimal bin assignment (ABC analysis)
    replenishment.py                     — Backstock replenishment triggers
    sap_adapter.py                       — SAP ERP integration adapter
    odoo_adapter.py                      — Odoo ERP integration adapter
    webhook_adapter.py                   — Generic webhook handler
    dlq.py                               — Dead-letter queue for failed order processing
```

### Intelligence & Protocol

```
  intelligence/iogita/
    zone_identifier.py                   — Zone classification via 16-feature geometry (39KB, <1ms)
    cold_start.py                        — Boot recovery without prior map data (<5s)
    kdtree_adapter.py                    — KD-tree spatial indexing for node lookup
    dual_scan.py                         — Two-pass zone fingerprinting (56 features)
    symmetry_breaker.py                  — Handles symmetric grid ambiguity
    safety_checker.py                    — Validates zone transitions (7 safety rules)

  vda5050/
    models.py                            — Pydantic models: Order, State, Action, Factsheet (VDA5050 v2.0)
    gateway.py                           — Message validation and routing
    translator.py                        — Internal order format to VDA5050 format
    mqtt_client.py                       — MQTT transport layer (Mosquitto broker)

  ros2_bridge/
    bridge.py                            — ROS2 topic subscription and publishing
    hal.py                               — Hardware abstraction layer (sensors, actuators)
    topic_mapper.py                      — ROS2 topic names to internal event routing

  monitoring/
    influx_writer.py                     — Writes time-series metrics to InfluxDB
    redis_cache.py                       — Redis hot-state cache for robot positions
```

### io-gita Integration

```
io-gita-addverb-v2/fleet/
  fleet_integration/
    iogita_zone_node.py                  — ZoneIdentifier: 16-feature extraction + ODE classification
    fms_adapter.py                       — Sync REST adapter: Python to C++ FMS bridge
    fms_adapter_async.py                 — Async version of FMS adapter (httpx)
    barcode_fallback_hook.py             — Fallback location via barcode grid when io-gita uncertain
    shared_config.py                     — Shared warehouse/robot config for io-gita
    structured_logger.py                 — Structured JSON logging with context
    warehouse_config.yaml                — io-gita warehouse zone definitions
  sg_engine/                             — Compiled SG engine (requires Python 3.11)
  tests/
    test_zone_identifier.py              — 19 tests: zone accuracy, feature extraction, fallback
    test_barcode_fallback.py             — Barcode grid tracking tests
    test_protocol_v1.py                  — ProtocolV1 serialization/CRC32 tests
    test_structured_logger.py            — Logger format and context tests

iogita_coldstart_addverb/
  engine/                                — Core io-gita cold start engine
  simulation_results/
    test_cold_start_v4.py                — 24 tests: >90% accuracy, <5s recovery, safety, honesty
    intelligence/iogita/
      zone_identifier.py                 — Hierarchical zone identifier (cold start variant)
      cold_start.py                      — Boot recovery simulation
      safety_checker.py                  — Safety rule validation (7 checks)
      dual_scan.py                       — Dual-scan fingerprint combiner
```

### Frontend (React Dashboard)

```
frontend/
  package.json                           — React 18, TypeScript, Tailwind CSS, Vite
  vite.config.ts                         — Vite bundler config with API proxy to :8029
  src/
    App.tsx                              — Main app: fleet status polling + WebSocket connection
    types.ts                             — TypeScript interfaces: Robot, Task, FleetStatus
    hooks/
      useApi.ts                          — REST API polling hook (configurable interval)
      useFleetWebSocket.ts               — WebSocket hook: real-time fleet updates
    components/
      WarehouseGrid.tsx                  — 2D warehouse map with robot positions + paths
      RobotStatusPanel.tsx               — Individual robot: battery, state, current task
      TaskQueue.tsx                       — Pending/active task list with priority
      BatteryLevels.tsx                  — Fleet battery level visualization
      IoGitaZones.tsx                    — io-gita zone overlay on warehouse map
      SGPredictions.tsx                  — SG engine bottleneck predictions
```

### Gazebo Simulation

```
robotic_digital_twin_simulation/gazebo/
  launch.py                              — Gazebo world launch wrapper
  tests/
    test_world_gen.py                    — 29 tests: SDF generation, wall placement, zone markers
    test_robot_gen.py                    — 23 tests: differential/unidirectional model generation
  stress_test_15robots.py                — 15-robot concurrent stress test
  scale_100_robots.py                    — 100+ robot scalability test
  fleet_intelligence_40.py               — 40-robot io-gita intelligence test
  worlds/                                — Gazebo SDF world files
  models/                                — Robot URDF/SDF models
  plugins/                               — Gazebo physics plugins (barcode, obstacle, conveyor)
```

### Configuration (Source of Truth)

```
robotic_digital_twin_simulation/configs/
  robots/
    differential_drive.yaml              — 2-wheel robot: 1.5m/s, 270deg LiDAR, 100kg payload
    unidirectional.yaml                  — 4-wheel AGV: 1.4m/s, conveyor-top, forward-only
    zippy10.yaml                         — Zippy10: unidirectional, 1.4m/s, +/-15deg sensor
    amr500.yaml                          — AMR500: differential, 2.0m/s, 500kg payload
    addverb_dynamo.yaml                  — Addverb Dynamo: AMR specs from production
    addverb_quadron.yaml                 — Addverb Quadron: heavy-lift specs
    addverb_veloce.yaml                  — Addverb Veloce: high-speed specs
    forklift_heavy.yaml                  — Forklift: 2000kg, mast height 4.5m
    inspection_bot.yaml                  — Inspection: camera array, slow speed, high sensor
    mixed_fleet_10.json                  — Fleet composition: 4 AMR + 4 AGV + 1 fork + 1 inspect
  warehouses/
    simple_grid.json                     — 5x5 grid, 25 nodes (unit testing)
    production_50x60.json                — 50x60m, 70 nodes, 5 zones, 130 edges (production)
    botvalley.json                       — Botvalley reference: 63 nodes, real layout
    addverb_noida.json                   — Addverb Noida facility layout
    warehouse_pharma.json                — Pharmaceutical cold-chain warehouse
    realistic.json                       — 100+ zone realistic warehouse
  faults/
    production_stress_10faults.json      — 10-fault schedule: motor, battery, sensor, network
```

### Tests (1567 total)

```
tests/                                   — Root integration tests (51 tests)
  test_infra.py                          — 15 tests: Docker service probes (MongoDB, Redis, RabbitMQ, fleet_core, FastAPI)
  test_fleet_core_capabilities.py        — 14 tests: C++ source contracts (COPP, BT XML, barcode, conveyor)
  test_iogita.py                         — 5 tests: io-gita module importability + sg_engine
  test_monitoring.py                     — 8 tests: InfluxDB writer, MongoDB poller, Redis cache
  test_sg_prediction.py                  — 3 tests: state encoder, bottleneck predictor, timing
  test_wes_wcs.py                        — 6 tests: order/task generator, KPI, conveyor, sorter

robotic_digital_twin_simulation/python/tests/  — Main test suite (1394 tests)
  conftest.py                            — Async test client, MongoDB detection, env vars
  test_api.py                            — API endpoint tests (async httpx client)
  test_production_validator.py           — 21 tests: throughput, inventory, deadlock, fault, DLQ
  test_production_cli.py                 — 14 tests: CLI args, health, scenario, CSV export
  test_wrie_cli.py                       — 9 tests: simulate/validate/export commands
  test_cold_start_v4.py                  — 24 tests: zone accuracy, recovery, safety, honesty
  test_fms_bridge.py                     — ProtocolV1 serialization, CRC32, virtual robot
  test_vda5050.py                        — VDA5050 model validation, translator
  test_health.py                         — Real health checks (proves not hardcoded)
  test_charging.py                       — 45+ tests: battery math, queue priority, strategy
  test_inventory.py                      — Inventory CRUD, ABC analysis
  test_wcs.py                            — Conveyor, sorter, lane logic
  test_wes.py                            — Order generation, wave batching
  test_wms.py                            — WMS connector, DLQ, webhook
  test_mapf.py                           — CBS/PIBT solver correctness
  test_designer.py                       — Layout generator output
  test_gazebo_bridge.py                  — Gazebo communication layer
  test_ros2_bridge.py                    — ROS2 topic mapping
  ... (40+ test files total)

io-gita-addverb-v2/fleet/tests/         — io-gita unit tests (46 tests)
iogita_coldstart_addverb/simulation_results/ — Cold start tests (24 tests)
robotic_digital_twin_simulation/gazebo/tests/ — Gazebo gen tests (52 tests)
```

---

## Docker Stack (Merged — Single Compose)

**Canonical compose:** `robotic_digital_twin_simulation/docker/docker-compose.yml`
**Canonical Dockerfile:** `docker/Dockerfile` (199 lines, multi-stage)

### What's in the container

```
rdt-app container (docker/Dockerfile):
  Stage 1: C++ Builder (ubuntu:22.04)
    - fleet_core from Main_robotics/fleet_core/
    - cmake + vcpkg → fmsApp + fmsSimulatorApp binaries
    - Shared libs → /fleet_core/lib/

  Stage 2: Runtime (ubuntu:22.04)
    - Gazebo Fortress (100 ignition packages, ign gazebo)
    - Python 3.11 + all deps (fastapi, motor, redis, scipy, pika, etc.)
    - fleet_core binaries + Addverb assets (BT XMLs, maps, configs)
    - io-gita-addverb-v2 (fleet_integration + sg_engine .so)
    - Warehouse SDF worlds + robot SDF models
    - Gazebo plugins source (barcode, lidar, conveyor)
    - FastAPI app (118 endpoints)
```

### 9 Services

| Service | Image | Port | Purpose |
|:--------|:------|:-----|:--------|
| `rdt-app` | docker/Dockerfile | 65123, 7012, 8029 | C++ FMS + Python FastAPI + Gazebo |
| `rdt-mongodb` | mongo:7 | 27017 | State IPC (C++ writes, Python reads) |
| `rdt-rabbitmq` | rabbitmq:3-management | 5672, 15672 | Task queue + event bus |
| `rdt-redis` | redis:7-alpine | 6380→6379 | Hot-state cache |
| `rdt-influxdb` | influxdb:2 | 8086 | Time-series telemetry |
| `rdt-mosquitto` | eclipse-mosquitto:2 | 1883, 9001 | MQTT broker (VDA5050) |
| `rdt-ros2-bridge` | ros:humble | — | ROS2 nav2 integration |
| `rdt-grafana` | grafana/grafana | 3000 | Telemetry dashboards |

### Legacy container (archived)

`docker/docker-compose.yml` — the old simplified stack without Gazebo. Still works for Python-only mode. Not the canonical one.

---

## Run Commands

```bash
# ── Full stack (build + start all 9 services) ──
docker compose -f robotic_digital_twin_simulation/docker/docker-compose.yml up -d --build

# ── Infrastructure only (no app rebuild) ──
docker compose -f robotic_digital_twin_simulation/docker/docker-compose.yml up -d mongodb rabbitmq redis influxdb mosquitto grafana

# ── Start app after infra is healthy ──
docker compose -f robotic_digital_twin_simulation/docker/docker-compose.yml up -d rdt

# ── Full test suite (1567 tests, ~90s) ──
pytest

# ── Just infra probes (Docker must be running) ──
pytest -m infra -v

# ── Just C++ contract tests (no Docker needed) ──
pytest -m contract -v

# ── API docs ──
open http://localhost:8029/docs

# ── Grafana dashboard ──
open http://localhost:3000

# ── RabbitMQ management ──
open http://localhost:15672   # user: fms, pass: changeme

# ── Gazebo headless inside container ──
docker exec rdt-app ign gazebo --headless-rendering -s <world.sdf>
```

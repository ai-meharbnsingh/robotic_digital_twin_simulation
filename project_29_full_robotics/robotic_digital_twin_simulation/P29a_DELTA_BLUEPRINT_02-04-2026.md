# P29a Delta Blueprint — Robot / Map / WMS Agnostic Platform

**Date:** 02-04-2026
**Base:** P29 WRIE (18 phases, ~1,428+ tests, ~118 endpoints, 86+ audit)
**Goal:** Evolve P29 into a platform where ANY robot, ANY warehouse, ANY ERP plugs in and runs
**Strategy:** EVOLVE in place (85% codebase already agnostic) — NOT rebuild

---

## Table of Contents

1. [Current State Summary](#1-current-state-summary)
2. [Agnosticism Scorecard](#2-agnosticism-scorecard)
3. [Complete Annotated Project Tree](#3-complete-annotated-project-tree)
4. [Phase Plan (9 Phases, 48 Tasks, 23 Days)](#4-phase-plan)
5. [System Architecture Flowcharts](#5-system-architecture-flowcharts)
6. [Resource Estimates (SaaS)](#6-resource-estimates)

---

## 1. Current State Summary

P29 is a **working warehouse robotics digital twin** inside Docker:
- C++ Fleet Manager running at 15Hz (67ms budget)
- Python FastAPI with ~118 REST endpoints + WebSocket
- 9 robot models in Gazebo Fortress (ODE physics, 1kHz)
- 6 warehouse world files
- 8 Docker services (MongoDB, Redis, RabbitMQ, InfluxDB, Grafana, Mosquitto, ROS2 Bridge, main app)
- WES/WCS/WMS pipeline with order-to-completion flow
- VDA5050 MQTT protocol for AGV communication
- io-gita zone intelligence (KDTree v5, 0.008ms)
- React 3D dashboard with 12+ panels

**What's NOT agnostic (the 15%):**
- C++ ActionNodes hardcode action codes 14/15
- C++ ProtocolV1 hardcodes 33-field wire format
- C++ MotionController only does differential drive
- WCS lane types are hardcoded enum
- Sorter uses prefix matching, doc says regex
- io-gita is coupled — no localization abstraction
- Charging strategies hardcoded in engine logic
- Maintenance uses linear degradation only
- Gazebo world generator hardcoded to one warehouse
- No standard inbound order schema
- No adapter registry for WMS plugins

---

## 2. Agnosticism Scorecard

| Dimension | P29 (Now) | P29a (Target) | Key Blocker |
|-----------|-----------|---------------|-------------|
| **Robot** | 70% | 95% | MotionController + ProtocolAdapter + action code config |
| **Map** | 95% | 98% | Gazebo world generator hardcoded to one layout |
| **WMS** | 98% | 100% | Adapter registry + standard order schema |
| **Overall** | **78%** | **97%** | |

---

## 3. Complete Annotated Project Tree

Legend: `(existing)` = no changes | `[M]` = modify | `★ NEW` = create

```
project_29a_robotic_digital_twin/
│
├── CLAUDE.md                                       (existing)
├── P29a_DELTA_BLUEPRINT_02-04-2026.md              (existing)
├── CMakeLists.txt                                  (existing)
├── vcpkg.json                                      (existing)
├── .env.example                                    (existing)
│
├── cpp/
│   ├── CMakeLists.txt                              [M] add new source files to build
│   ├── include/rdt/
│   │   ├── behavior/
│   │   │   ├── ActionNodes.h                       (existing)
│   │   │   ├── BTEngine.h                          (existing)
│   │   │   └── ConditionNodes.h                    (existing)
│   │   ├── core/
│   │   │   ├── Config.h                            (existing)
│   │   │   ├── Logger.h                            (existing)
│   │   │   ├── Timer.h                             (existing)
│   │   │   └── Types.h                             (existing)
│   │   ├── fleet/
│   │   │   ├── AgentInterface.h                    (existing)
│   │   │   ├── COPPController.h                    (existing)
│   │   │   ├── FleetManager.h                      (existing)
│   │   │   └── TaskManager.h                       (existing)
│   │   ├── navigation/
│   │   │   ├── AStar.h                             (existing)
│   │   │   ├── GraphMap.h                          (existing)
│   │   │   ├── NodeReservation.h                   (existing)
│   │   │   └── QuadTree.h                          (existing)
│   │   ├── network/
│   │   │   ├── ProtocolAdapter.h                   ★ NEW — abstract interface: any robot protocol
│   │   │   ├── ProtocolV1.h                        [M] implement ProtocolAdapter interface
│   │   │   ├── RESTServer.h                        (existing)
│   │   │   └── TCPServer.h                         (existing)
│   │   └── robot/
│   │       ├── BatteryModel.h                      (existing)
│   │       ├── MotionController.h                  [M] add factory method for multi-drive support
│   │       ├── MotionControllerFactory.h           ★ NEW — diff/omni/ackermann per robot type
│   │       ├── ObstacleHandler.h                   (existing)
│   │       ├── RobotState.h                        (existing)
│   │       └── RobotTelemetry.h                    ★ NEW — generic telemetry replacing V1 fields
│   │
│   ├── src/
│   │   ├── apps/fms_server.cpp                     (existing)
│   │   ├── behavior/
│   │   │   ├── ActionNodes.cpp                     [M] config map lookup instead of hardcoded 14/15
│   │   │   ├── BTEngine.cpp                        (existing)
│   │   │   └── ConditionNodes.cpp                  (existing)
│   │   ├── core/
│   │   │   ├── Config.cpp                          (existing)
│   │   │   ├── Logger.cpp                          (existing)
│   │   │   └── Timer.cpp                           (existing)
│   │   ├── fleet/
│   │   │   ├── AgentInterface.cpp                  (existing)
│   │   │   ├── COPPController.cpp                  (existing)
│   │   │   ├── FleetManager.cpp                    (existing)
│   │   │   └── TaskManager.cpp                     (existing)
│   │   ├── navigation/
│   │   │   ├── AStar.cpp                           (existing)
│   │   │   ├── GraphMap.cpp                        (existing)
│   │   │   ├── NodeReservation.cpp                 (existing)
│   │   │   └── QuadTree.cpp                        (existing)
│   │   ├── network/
│   │   │   ├── ProtocolAdapter.cpp                 ★ NEW — factory + V1Adapter wrapping ProtocolV1
│   │   │   ├── ProtocolV1.cpp                      [M] refactor into adapter pattern
│   │   │   ├── RESTServer.cpp                      (existing)
│   │   │   └── TCPServer.cpp                       (existing)
│   │   └── robot/
│   │       ├── BatteryModel.cpp                    (existing)
│   │       ├── MotionController.cpp                [M] extract diff-drive, called by factory
│   │       ├── MotionControllerFactory.cpp         ★ NEW — creates controller from RobotType
│   │       ├── ObstacleHandler.cpp                 (existing)
│   │       └── RobotState.cpp                      (existing)
│   │
│   └── tests/
│       ├── CMakeLists.txt                          [M] register new test files
│       ├── test_astar.cpp                          (existing)
│       ├── test_battery.cpp                        (existing)
│       ├── test_bt.cpp                             (existing)
│       ├── test_config.cpp                         (existing)
│       ├── test_fleet.cpp                          (existing)
│       ├── test_graph.cpp                          (existing)
│       ├── test_hello.cpp                          (existing)
│       ├── test_logger.cpp                         (existing)
│       ├── test_motion.cpp                         [M] add factory + omni controller tests
│       ├── test_obstacle.cpp                       (existing)
│       ├── test_protocol.cpp                       [M] test adapter pattern
│       ├── test_protocol_adapter.cpp               ★ NEW — verify V1Adapter + factory dispatch
│       ├── test_quadtree.cpp                       (existing)
│       ├── test_reservation.cpp                    (existing)
│       ├── test_rest.cpp                           (existing)
│       ├── test_robot_state.cpp                    (existing)
│       ├── test_tcp.cpp                            (existing)
│       ├── test_timer.cpp                          (existing)
│       └── test_types.cpp                          (existing)
│
├── python/
│   ├── wrie_cli.py                                 [M] scrub vendor defaults
│   ├── run_e2e.py                                  [M] scrub vendor defaults
│   ├── run_production.py                           [M] scrub vendor defaults
│   ├── generate_dashboard.py                       (existing)
│   ├── requirements.txt                            (existing)
│   │
│   ├── app/
│   │   ├── main.py                                 [M] scrub vendor presets, wire adapter registry
│   │   ├── config.py                               (existing)
│   │   ├── auth.py                                 (existing)
│   │   ├── websocket.py                            (existing)
│   │   └── routes/
│   │       ├── analytics.py                        (existing)
│   │       ├── charging.py                         [M] wire ChargeStrategy ABC
│   │       ├── config_routes.py                    (existing)
│   │       ├── designer.py                         [M] remove vendor template category
│   │       ├── events.py                           (existing)
│   │       ├── fleet.py                            (existing)
│   │       ├── heatmap.py                          (existing)
│   │       ├── human_agents.py                     (existing)
│   │       ├── inventory.py                        (existing)
│   │       ├── iogita.py                           [M] wire LocalizationEngine ABC
│   │       ├── maintenance.py                      [M] parametric degradation from config
│   │       ├── mapf.py                             (existing)
│   │       ├── maps.py                             (existing)
│   │       ├── order_import.py                     (existing)
│   │       ├── reservations.py                     (existing)
│   │       ├── robots.py                           (existing)
│   │       ├── ros2.py                             (existing)
│   │       ├── scenarios.py                        (existing)
│   │       ├── simulation.py                       (existing)
│   │       ├── stats.py                            (existing)
│   │       ├── tasks.py                            (existing)
│   │       ├── telemetry_export.py                 (existing)
│   │       ├── telemetry.py                        (existing)
│   │       ├── vda5050.py                          (existing)
│   │       ├── waves.py                            (existing)
│   │       ├── wcs.py                              [M] load lane types from YAML
│   │       ├── wes.py                              (existing)
│   │       └── wms.py                              (existing)
│   │
│   ├── wes/                                        (all 12 files existing — fully generic)
│   │
│   ├── wcs/
│   │   ├── conveyor_controller.py                  (existing)
│   │   ├── lane_manager.py                         [M] load lane types from YAML
│   │   ├── package_tracker.py                      (existing)
│   │   ├── sorter_engine.py                        [M] use RoutingStrategy interface
│   │   └── routing_strategy.py                     ★ NEW — ABC for barcode/RFID/weight sorting
│   │
│   ├── wms/
│   │   ├── connector.py                            (existing — adapter ABC)
│   │   ├── dlq.py                                  (existing)
│   │   ├── inventory_manager.py                    (existing)
│   │   ├── odoo_adapter.py                         (existing)
│   │   ├── order_translator.py                     [M] use declarative YAML translation rules
│   │   ├── replenishment.py                        (existing)
│   │   ├── sap_adapter.py                          (existing)
│   │   ├── storage_optimizer.py                    (existing)
│   │   ├── webhook_adapter.py                      (existing)
│   │   ├── adapter_registry.py                     ★ NEW — register ERP adapters at runtime
│   │   └── standard_order.py                       ★ NEW — 10-field universal order schema
│   │
│   ├── vda5050/                                    (all 5 files existing — standard protocol)
│   │
│   ├── intelligence/
│   │   ├── localization_engine.py                  ★ NEW — ABC: io-gita/barcode/RFID backends
│   │   └── iogita/                                 (all 7 files existing — becomes one impl)
│   │
│   ├── services/
│   │   ├── charging/
│   │   │   ├── charge_strategy.py                  ★ NEW — ABC for depot/in-situ/grid charging
│   │   │   ├── degradation_model.py                (existing)
│   │   │   ├── queue_manager.py                    (existing)
│   │   │   └── strategy_engine.py                  [M] use ChargeStrategy ABC
│   │   ├── human_agents/                           (all 4 files existing — generic)
│   │   ├── maintenance/
│   │   │   ├── component_model.py                  (existing)
│   │   │   ├── predictive_engine.py                [M] load curve type from config
│   │   │   └── scheduler.py                        (existing)
│   │   └── simulation/
│   │       ├── real_gazebo_bridge.py               [M] scrub vendor model paths
│   │       └── (11 other files existing)
│   │
│   ├── ros2_bridge/                                (all 4 files existing)
│   ├── monitoring/                                 (all 3 files existing)
│   ├── designer/                                   (all 3 files existing)
│   ├── scripts/                                    (all 3 files existing)
│   │
│   ├── map_importer/                               ★ NEW DIRECTORY
│   │   ├── __init__.py                             ★ NEW — package init
│   │   ├── dxf_converter.py                        ★ NEW — AutoCAD DXF → warehouse JSON
│   │   └── node_generator.py                       ★ NEW — auto-gen nodes from floor plan
│   │
│   └── tests/
│       ├── conftest.py                             (existing)
│       ├── (41 existing test files)
│       ├── test_designer_v2_api.py                 [M] scrub vendor template refs
│       ├── test_fleet_config.py                    [M] scrub vendor refs
│       ├── test_mapf.py                            [M] scrub vendor refs
│       ├── test_scenario_overrides.py              [M] scrub vendor refs
│       ├── test_wrie_cli.py                        [M] scrub vendor refs
│       ├── test_adapter_registry.py                ★ NEW — test ERP adapter plugin registry
│       ├── test_charge_strategy.py                 ★ NEW — test charging strategy ABC
│       ├── test_localization_engine.py             ★ NEW — test localization ABC + io-gita
│       ├── test_protocol_adapter.py                ★ NEW — test Python-side protocol adapter
│       └── test_routing_strategy.py                ★ NEW — test sorter routing strategy ABC
│
├── configs/
│   ├── behavior_trees/
│   │   ├── default_agv.xml                         [M] template action codes via config injection
│   │   ├── default_amr.xml                         [M] template action codes via config injection
│   │   └── default_omni.xml                        ★ NEW — behavior tree for omni robots
│   ├── charging/
│   │   └── strategy_profiles.yaml                  (existing)
│   ├── faults/                                     (existing — 2 files)
│   ├── fleets/
│   │   └── default_mixed.json                      [M] use generic type names only
│   ├── human_agents/
│   │   └── worker_profiles.yaml                    (existing)
│   ├── maintenance/
│   │   └── component_profiles.yaml                 (existing)
│   ├── robots/
│   │   ├── differential_drive.yaml                 [M] add gazebo_model field
│   │   ├── forklift_heavy.yaml                     [M] add gazebo_model field
│   │   ├── inspection_bot.yaml                     [M] add gazebo_model field
│   │   ├── omnidirectional.yaml                    ★ NEW — generic omni robot config
│   │   └── unidirectional.yaml                     [M] add gazebo_model field
│   ├── warehouses/                                 (all 5 JSON files existing)
│   ├── wcs/
│   │   └── conveyor_layout.yaml                    [M] templateable sort rules
│   └── wms/
│       ├── sku_catalog.yaml                        (existing)
│       └── translation_rules/                      ★ NEW DIRECTORY
│           ├── sap.yaml                            ★ NEW — SAP field mapping
│           ├── oracle.yaml                         ★ NEW — Oracle ERP mapping
│           └── generic_webhook.yaml                ★ NEW — template for custom ERP
│
├── docker/
│   ├── Dockerfile                                  (existing)
│   ├── docker-compose.yml                          [M] remove hardcoded defaults, add env vars
│   ├── start.sh                                    [M] fail-fast on missing config
│   ├── .env.example                                [M] add BT/fleet/WCS env vars
│   ├── .env.docker.example                         [M] same
│   ├── mosquitto/                                  (existing — 2 files)
│   └── sros2/                                      (existing — 2 files)
│
├── gazebo/
│   ├── models/
│   │   ├── generic/
│   │   │   ├── diffdrive_amr/                      (existing — 2 files)
│   │   │   ├── uni_agv/                            (existing — 2 files)
│   │   │   └── omnidirectional/                    ★ NEW DIRECTORY
│   │   │       ├── model.config                    ★ NEW — Gazebo model metadata
│   │   │       └── model.sdf                       ★ NEW — 4-mecanum-wheel physics
│   │   └── vendors/                                ★ NEW DIRECTORY
│   │       └── README.md                           ★ NEW — customer model placement guide
│   │
│   ├── templates/                                  ★ NEW DIRECTORY
│   │   └── zone_templates/
│   │       ├── shelf_row.sdf                       ★ NEW — reusable shelf for world gen
│   │       ├── charging_bay.sdf                    ★ NEW — reusable charger geometry
│   │       └── conveyor_segment.sdf                ★ NEW — reusable conveyor geometry
│   │
│   ├── worlds/
│   │   ├── (6 existing .sdf files)
│   │   ├── warehouse_distinct_generator.py         [M] generalize for ANY warehouse JSON
│   │   └── gen_fleet_world.py                      [M] add --world-file CLI arg
│   │
│   ├── plugins/                                    (existing — 4 files)
│   ├── scripts/
│   │   └── generate_robot_sdf.py                   [M] scrub vendor model references
│   ├── spawn_fleet.py                              [M] read gazebo_model from robot YAML
│   ├── launch.py                                   (existing)
│   └── (12 other sim/benchmark scripts existing)
│
├── frontend/                                       (ALL EXISTING — data-driven, no changes)
│   ├── package.json, vite.config.ts, etc.
│   └── src/
│       ├── App.tsx, main.tsx, types.ts
│       ├── components/ (19 .tsx)
│       └── hooks/ (8 .ts)
│
├── iogita_kdtree/                                  (renamed from iogita_kdtree_addverb)
│   └── engine/io_gita_engine.py                    (existing)
│
├── docs/                                           (existing — 6 files)
│   └── USER_EXPERIENCE.md                          [M] scrub vendor refs
├── audit/                                          (existing — 5 files)
│   ├── ALL_82_FINDINGS.md                          [M] scrub vendor refs
│   └── KIMI_VERIFICATION_PROMPT.md                 [M] scrub vendor refs
├── scenarios/                                      (existing — 4 files)
│   ├── test_dynamic_obstacles.py                   [M] scrub vendor refs
│   └── test_real_amcl_benchmark.py                 [M] scrub vendor refs
└── e2e/                                            (existing — 6 files)
```

### File Count Summary

| Action | Files | What |
|--------|-------|------|
| **(existing)** | ~155 | Working code — no changes needed |
| **[M] MODIFY** | ~35 | Scrub vendors (~15) + add abstractions (~12) + config fields (~8) |
| **★ NEW** | ~30 | Abstraction layers + configs + tests + Gazebo models + map importer |
| **Total** | **~220** | |

---

## 4. Phase Plan (9 Phases, 48 Tasks, 23 Days)

### Phase 0 — Foundation + Vendor Cleanup (2 days)
**Goal:** Zero vendor refs, remove all hardcoded assumptions

| # | Task | Files |
|---|------|-------|
| 1 | Scrub all vendor references from ~15 code files | main.py, designer.py, spawn_fleet.py, tests, scenarios, docs |
| 2 | Fix ActionNodes.cpp — config map lookup for codes 14/15/31/51 | cpp/src/behavior/ActionNodes.cpp |
| 3 | Create ProtocolAdapter.h + RobotTelemetry.h | cpp/include/rdt/network/, cpp/include/rdt/robot/ |
| 4 | Create ProtocolAdapter.cpp (factory + V1Adapter) | cpp/src/network/ProtocolAdapter.cpp |
| 5 | Refactor ProtocolV1.h/cpp to implement adapter interface | cpp/include/rdt/network/ProtocolV1.h, cpp/src/network/ProtocolV1.cpp |
| 6 | Create adapter_registry.py (ERP plugin system) | python/wms/adapter_registry.py |
| 7 | Create standard_order.py (10-field Pydantic schema) | python/wms/standard_order.py |
| 8 | Fix docker-compose.yml — remove hardcoded defaults, add env vars | docker/docker-compose.yml, docker/.env.example |
| 9 | Fix start.sh — fail-fast on missing config, add BT handling | docker/start.sh |
| 10 | Add `gazebo_model` field to all robot YAML configs | configs/robots/*.yaml |
| 11 | Create gazebo/models/vendors/README.md | gazebo/models/vendors/ |
| 12 | Write tests for ProtocolAdapter | cpp/tests/test_protocol_adapter.cpp, python/tests/test_protocol_adapter.py |
| 13 | Write tests for adapter_registry + standard_order | python/tests/test_adapter_registry.py |

### Phase 1 — Robot Agnostic (3 days)
**Goal:** Any robot plugs in with a YAML config file

| # | Task | Files |
|---|------|-------|
| 14 | Create MotionControllerFactory.h/.cpp (diff, omni, ackermann) | cpp/include/rdt/robot/, cpp/src/robot/ |
| 15 | Refactor MotionController to work through factory | cpp/src/robot/MotionController.cpp |
| 16 | Create LocalizationEngine ABC (io-gita becomes one impl) | python/intelligence/localization_engine.py |
| 17 | Wire iogita.py route to use LocalizationEngine | python/app/routes/iogita.py |
| 18 | Create ChargeStrategy ABC (depot, in-situ, grid) | python/services/charging/charge_strategy.py |
| 19 | Wire strategy_engine.py to use ChargeStrategy | python/services/charging/strategy_engine.py |
| 20 | Create omnidirectional.yaml + default_omni.xml | configs/robots/, configs/behavior_trees/ |
| 21 | Create Gazebo omnidirectional model (4-mecanum SDF) | gazebo/models/generic/omnidirectional/ |
| 22 | Parametrize maintenance degradation curves from config | python/services/maintenance/predictive_engine.py |
| 23 | Update spawn_fleet.py for registry-based model loading | gazebo/spawn_fleet.py |
| 24 | Template action codes in BT XMLs via config injection | configs/behavior_trees/default_amr.xml, default_agv.xml |
| 25 | Write tests | python/tests/test_localization_engine.py, test_charge_strategy.py, cpp/tests/test_motion.cpp |

### Phase 2 — Map Agnostic (2 days)
**Goal:** Any warehouse layout generates a working simulation

| # | Task | Files |
|---|------|-------|
| 26 | Generalize warehouse_distinct_generator.py for ANY JSON | gazebo/worlds/warehouse_distinct_generator.py |
| 27 | Create zone geometry templates (shelf, charger, conveyor SDF) | gazebo/templates/zone_templates/*.sdf |
| 28 | Create DXF importer (AutoCAD floor plan → warehouse JSON) | python/map_importer/dxf_converter.py |
| 29 | Create auto-node-generator (floor plan geometry → node graph) | python/map_importer/node_generator.py |
| 30 | Add --world-file and --model-type CLI args to gen_fleet_world.py | gazebo/worlds/gen_fleet_world.py |
| 31 | Write tests for map_importer | python/tests/ (new test files) |

### Phase 3 — WMS Agnostic (2 days)
**Goal:** Any ERP sends orders via 10-field mapping

| # | Task | Files |
|---|------|-------|
| 32 | Create declarative translation rules (YAML field mapping) | configs/wms/translation_rules/sap.yaml, oracle.yaml, generic_webhook.yaml |
| 33 | Update order_translator.py to use YAML rules | python/wms/order_translator.py |
| 34 | Enable multi-ERP routing (not singleton connector) | python/app/main.py |
| 35 | Fix WCS: load lane types from YAML | python/wcs/lane_manager.py, python/app/routes/wcs.py |
| 36 | Create RoutingStrategy ABC (barcode/RFID/weight) | python/wcs/routing_strategy.py |
| 37 | Wire sorter_engine.py to use RoutingStrategy | python/wcs/sorter_engine.py |
| 38 | Implement 10-field standard order validation on webhook | python/app/routes/wms.py |
| 39 | Write tests | python/tests/test_routing_strategy.py |

### Phase 4 — Auth + User Accounts (3 days)
**Goal:** Users sign up, upload configs, own their data

| # | Task | Files |
|---|------|-------|
| 40 | Add auth service (JWT signup/login/verify/refresh) | python/app/auth.py (extend), new auth routes |
| 41 | Add user database (PostgreSQL — accounts, configs, sessions) | docker/docker-compose.yml (add postgres), new models |
| 42 | Add file upload API (warehouse JSON, robot YAML, SDF models) | new route: python/app/routes/uploads.py |
| 43 | Per-user config storage (S3 or local volume) | python/app/config.py (extend) |
| 44 | Protect all API routes with JWT middleware | python/app/auth.py, all routes |

### Phase 5 — Container Orchestration (3 days)
**Goal:** Each user gets isolated Docker simulation instance

| # | Task | Files |
|---|------|-------|
| 45 | Per-user docker-compose template generation | new: platform/container_manager.py |
| 46 | Port allocation manager (no conflicts across users) | new: platform/port_allocator.py |
| 47 | Container lifecycle API: create/start/stop/status/destroy | new: platform/lifecycle_api.py |
| 48 | Volume isolation per user (mongo, redis, influx per session) | docker-compose template |
| 49 | Health check + readiness polling (wait for /health) | platform/container_manager.py |
| 50 | Reverse proxy routing (nginx: /user123/* → user's container) | new: platform/nginx_config_gen.py |

### Phase 6 — Onboarding Wizard (3 days)
**Goal:** 4-step browser setup: warehouse → robots → WMS → launch

| # | Task | Files |
|---|------|-------|
| 51 | Add React Router (page routing system) | frontend/package.json, frontend/src/App.tsx |
| 52 | Login/Signup pages | frontend/src/pages/Login.tsx, Signup.tsx |
| 53 | Step 1: Choose/upload warehouse (template picker + upload + designer) | frontend/src/pages/onboarding/WarehouseStep.tsx |
| 54 | Step 2: Choose/upload robots (generic sliders + custom YAML) | frontend/src/pages/onboarding/RobotStep.tsx |
| 55 | Step 3: Connect WMS (10-field mapping form + webhook URL) | frontend/src/pages/onboarding/WMSStep.tsx |
| 56 | Step 4: Review + launch simulation | frontend/src/pages/onboarding/ReviewStep.tsx |
| 57 | Save onboarding state to user DB | frontend hooks + platform API |

### Phase 7 — 3D Visual Upgrade (2 days)
**Goal:** GLTF robot models replace primitive boxes

| # | Task | Files |
|---|------|-------|
| 58 | Source/create GLTF models (AMR, AGV, Forklift, Omni) | frontend/public/models/*.glb |
| 59 | Load GLTF via useGLTF() in Warehouse3D.tsx | frontend/src/components/Warehouse3D.tsx |
| 60 | Add `web_model` field to robot YAML → Three.js loads matching .glb | configs/robots/*.yaml, frontend/src/components/Robot3DModel.tsx |
| 61 | Warehouse furniture GLTF (shelves, conveyors, chargers) | frontend/public/models/furniture/*.glb |
| 62 | Optional: LiDAR ray visualization, path trails | frontend/src/components/Warehouse3D.tsx |

### Phase 8 — Polish + End-to-End Testing (3 days)
**Goal:** Production-ready SaaS with tested multi-user flow

| # | Task | Files |
|---|------|-------|
| 63 | E2E test: signup → onboard → simulate → results | e2e/tests/ |
| 64 | Load testing: 10 concurrent user containers | e2e/, platform/ |
| 65 | WebSocket stability under multi-user load | python/app/websocket.py, platform/ |
| 66 | PDF/CSV report generation + download | python/wes/report_generator.py |
| 67 | Scenario comparison export | python/app/routes/scenarios.py |
| 68 | Error handling: container crash recovery, stale session cleanup | platform/lifecycle_api.py |

### Phase Summary

| Phase | Name | Days | Tasks | Key Deliverable |
|-------|------|------|-------|-----------------|
| 0 | Foundation + Vendor Cleanup | 2 | 13 | Zero vendor refs, protocol adapter, standard order |
| 1 | Robot Agnostic | 3 | 12 | MotionControllerFactory, LocalizationEngine, ChargeStrategy |
| 2 | Map Agnostic | 2 | 6 | Generic world generator, DXF import, zone templates |
| 3 | WMS Agnostic | 2 | 8 | YAML translation rules, RoutingStrategy, multi-ERP |
| 4 | Auth + User Accounts | 3 | 5 | JWT auth, file upload, per-user storage |
| 5 | Container Orchestration | 3 | 6 | Per-user Docker, port alloc, nginx routing |
| 6 | Onboarding Wizard | 3 | 7 | 4-step React wizard, React Router |
| 7 | 3D Visual Upgrade | 2 | 5 | GLTF robot models, warehouse furniture |
| 8 | Polish + E2E Testing | 3 | 6 | Multi-user load test, reports, error recovery |
| **Total** | | **23 days** | **68 tasks** | **Web-based SaaS simulation platform** |

---

## 5. System Architecture Flowcharts

### User Journey

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER JOURNEY                              │
│                                                                  │
│  ┌──────────┐   ┌──────────────┐   ┌──────────────┐            │
│  │ 1. SIGN  │──▶│ 2. CHOOSE    │──▶│ 3. CHOOSE    │            │
│  │    UP    │   │    WAREHOUSE │   │    ROBOTS    │            │
│  │          │   │              │   │              │            │
│  │ Email +  │   │ A) Template  │   │ A) Generic   │            │
│  │ Password │   │ B) Upload    │   │    (sliders) │            │
│  └──────────┘   │ C) Designer  │   │ B) Custom    │            │
│                 └──────────────┘   │    (YAML+SDF)│            │
│                                    └──────┬───────┘            │
│                                           │                     │
│  ┌──────────────┐   ┌──────────────┐      │                    │
│  │ 6. RESULTS   │◀──│ 5. RUN       │◀─────┤                    │
│  │              │   │    SIMULATION│      │                    │
│  │ PDF/CSV     │   │              │   ┌──┴───────────┐        │
│  │ Compare     │   │ Click Start  │   │ 4. CONNECT   │        │
│  │ Tune+Rerun  │   │ Watch live   │   │    WMS       │        │
│  └──────────────┘   └──────────────┘   │              │        │
│                                        │ A) Manual CSV│        │
│                                        │ B) Webhook   │        │
│                                        │ C) 10-field  │        │
│                                        │    mapping   │        │
│                                        └──────────────┘        │
└─────────────────────────────────────────────────────────────────┘
```

### Complete System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           BROWSER (User's Machine)                       │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                      React 19 + Vite + Tailwind                    │  │
│  │                                                                    │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌────────────┐ │  │
│  │  │ Login/      │ │ Onboarding  │ │ Dashboard   │ │ 3D View    │ │  │
│  │  │ Signup      │ │ Wizard      │ │ (12 panels) │ │ (Three.js) │ │  │
│  │  │             │ │             │ │             │ │            │ │  │
│  │  │ JWT auth    │ │ 1.Warehouse │ │ Robot panel │ │ WebGL      │ │  │
│  │  │             │ │ 2.Robots    │ │ Task queue  │ │ 60fps      │ │  │
│  │  │             │ │ 3.WMS setup │ │ KPIs        │ │ GLTF models│ │  │
│  │  │             │ │ 4.Test run  │ │ Heatmap     │ │ User's GPU │ │  │
│  │  └─────────────┘ └─────────────┘ └──────┬──────┘ └─────┬──────┘ │  │
│  │                                          │              │         │  │
│  │                    REST (3s poll) ────────┘   WebSocket ─┘         │  │
│  │                    /api/*                     /ws/fleet            │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  Rendering: Three.js (user's GPU) | Zero GPU needed on server            │
└─────────────────────────┬────────────────────┬───────────────────────────┘
                          │ HTTPS              │ WSS
                          ▼                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        CLOUD SERVER                                      │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    PLATFORM LAYER (shared)                       │    │
│  │                                                                  │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐ │    │
│  │  │ Auth Service  │  │ User DB      │  │ Container Orchestrator│ │    │
│  │  │ (JWT/OAuth2)  │  │ (PostgreSQL) │  │ (Docker API)          │ │    │
│  │  │              │  │              │  │                       │ │    │
│  │  │ signup       │  │ accounts     │  │ create(user_id)      │ │    │
│  │  │ login        │  │ configs      │  │ start(user_id)       │ │    │
│  │  │ verify       │  │ uploads      │  │ stop(user_id)        │ │    │
│  │  │ refresh      │  │ sessions     │  │ status(user_id)      │ │    │
│  │  └──────────────┘  └──────────────┘  └──────────┬────────────┘ │    │
│  └──────────────────────────────────────────────────┼──────────────┘    │
│                                                     │                    │
│                              spawns per user         │                    │
│                                                     ▼                    │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │              USER CONTAINER (isolated per user)                   │    │
│  │              ~3GB RAM, ~2 CPU, ~60s startup                      │    │
│  │                                                                  │    │
│  │  ┌────────────────────────────────────────────────────────────┐ │    │
│  │  │ C++ FMS Server (15Hz loop)                    Port: 65123  │ │    │
│  │  │                                                            │ │    │
│  │  │ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │ │    │
│  │  │ │FleetMgr  │ │TaskMgr   │ │A* Path   │ │NodeReserv    │  │ │    │
│  │  │ │(15Hz)    │ │(allocate)│ │(3 heur.) │ │(deadlock)    │  │ │    │
│  │  │ └──────────┘ └──────────┘ └──────────┘ └──────────────┘  │ │    │
│  │  │ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │ │    │
│  │  │ │BT Engine │ │Motion    │ │Battery   │ │Obstacle      │  │ │    │
│  │  │ │(BTCPP v4)│ │Controller│ │Model     │ │Handler       │  │ │    │
│  │  │ └──────────┘ │Factory   │ └──────────┘ └──────────────┘  │ │    │
│  │  │              │diff/omni │                                  │ │    │
│  │  │              │ackermann │         ┌──────────────────┐     │ │    │
│  │  │              └──────────┘         │ProtocolAdapter   │     │ │    │
│  │  │                                   │ V1 / V2 / Custom│     │ │    │
│  │  │     Writes fleet_state.json ──────┤                  │     │ │    │
│  │  │     at 15Hz (66ms cycle)          └──────────────────┘     │ │    │
│  │  └──────────────────────────┬─────────────────────────────────┘ │    │
│  │                             │ JSON file (IPC)                    │    │
│  │  ┌──────────────────────────▼─────────────────────────────────┐ │    │
│  │  │ Python FastAPI                                Port: 8029   │ │    │
│  │  │                                                            │ │    │
│  │  │ ┌──────────────────────────────────────────────────────┐  │ │    │
│  │  │ │ ~118 REST Endpoints + WebSocket /ws/fleet             │  │ │    │
│  │  │ │                                                       │  │ │    │
│  │  │ │ Fleet│Tasks│Map│WES│WCS│WMS│Inventory│VDA5050│MAPF   │  │ │    │
│  │  │ │ Scenarios│io-gita│Maintenance│Charging│HumanAgents   │  │ │    │
│  │  │ │ Designer│Analytics│Heatmap│Telemetry│ROS2│Health     │  │ │    │
│  │  │ └──────────────────────────────────────────────────────┘  │ │    │
│  │  │                                                            │ │    │
│  │  │ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │ │    │
│  │  │ │WES       │ │WMS       │ │io-gita   │ │WebSocket     │  │ │    │
│  │  │ │OrderGen  │ │Adapter   │ │KDTree v5 │ │Manager       │  │ │    │
│  │  │ │WaveEngine│ │Registry  │ │Localiz.  │ │100 max conn  │  │ │    │
│  │  │ │KPITracker│ │10-field  │ │Engine ABC│ │7 event types │  │ │    │
│  │  │ └──────────┘ │mapping   │ └──────────┘ └──────────────┘  │ │    │
│  │  │              └──────────┘                                  │ │    │
│  │  └────────────────────────────────────────────────────────────┘ │    │
│  │                                                                  │    │
│  │  ┌──────────────────────────────────────────────────────────────┐│    │
│  │  │ Gazebo Fortress (HEADLESS — no GUI, no GPU)                  ││    │
│  │  │                                                              ││    │
│  │  │ ODE Physics @ 1kHz │ Robot models │ Sensor simulation       ││    │
│  │  │ LiDAR (10Hz)       │ IMU (100Hz) │ Barcode reader           ││    │
│  │  │                                                              ││    │
│  │  │ Connects to C++ FMS via TCP:65123 (same as real hardware)   ││    │
│  │  └──────────────────────────────────────────────────────────────┘│    │
│  │                                                                  │    │
│  │  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │    │
│  │  │MongoDB 7│ │Redis 7   │ │RabbitMQ 3│ │Mosquitto │           │    │
│  │  │:27017   │ │:6379     │ │:5672     │ │:1883     │           │    │
│  │  │State IPC│ │Hot cache │ │Task queue│ │VDA5050   │           │    │
│  │  └─────────┘ └──────────┘ └──────────┘ └──────────┘           │    │
│  │                                                                  │    │
│  │  Resources: ~3GB RAM, ~2 CPU, zero GPU                          │    │
│  │  Startup: ~60s | Per-user cost: ~$5-10/month                    │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  One container per user session. Isolated volumes. No cross-contamination│
└──────────────────────────────────────────────────────────────────────────┘
```

### 3D Rendering Flow (Three.js in Browser)

```
SERVER (headless, zero GPU)              BROWSER (user's GPU)
┌──────────────────────────┐            ┌──────────────────────────┐
│                          │            │                          │
│ Gazebo (physics only)    │            │ Three.js / WebGL         │
│   └─ ODE 1kHz            │            │   └─ 60fps render        │
│   └─ robot collisions    │            │   └─ GLTF robot models   │
│   └─ sensor sim          │            │   └─ warehouse geometry  │
│                          │            │   └─ path highlighting   │
│ C++ FMS (15Hz)           │            │   └─ camera follow       │
│   └─ robot positions     │            │   └─ heatmap overlay     │
│   └─ battery levels      │  WebSocket │                          │
│   └─ task assignments    │──────────▶ │ Receives every 66ms:     │
│   └─ fleet status        │  /ws/fleet │   robot_id, x, y, theta  │
│                          │            │   battery_pct, status     │
│ Python FastAPI           │            │   task_id, path[]         │
│   └─ broadcasts state    │            │                          │
│   └─ 7 event types       │            │ Interpolates between     │
│                          │            │ updates for smooth motion │
│ Total: 0 GPU, ~3GB RAM  │            │ Total: user's GPU (free) │
└──────────────────────────┘            └──────────────────────────┘
```

### WMS Integration Flow (10-Field Universal Order)

```
ANY ERP (SAP / Oracle / Odoo / Custom)
│
│  POST /api/wms/webhook/receive
│  Body: { "AUFNR": "123", "MATNR": "WIDGET", "BMENG": 5, ... }
│
▼
┌─────────────────────────────────────────────────┐
│ ADAPTER REGISTRY                                 │
│                                                  │
│ Reads: configs/wms/translation_rules/sap.yaml   │
│                                                  │
│ Maps:  AUFNR → order_id                         │
│        MATNR → sku                              │
│        BMENG → qty                              │
│        LGORT → from_location                    │
│        UMLGO → to_location                      │
│        PRIOK → priority                         │
│        BWART → order_type                       │
│        LFDAT → due_by                           │
│        BRGEW → weight_kg                        │
│        BSTNR → reference                        │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────┐
│ STANDARD ORDER (10 fields)                        │
│                                                   │
│ { order_id, sku, qty, from_location,             │
│   to_location, priority, order_type,              │
│   due_by, weight_kg, reference }                  │
└──────────────────────┬───────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────┐
│ WES PIPELINE                                      │
│                                                   │
│ OrderGenerator → WaveEngine → TaskGenerator       │
│      │              │              │               │
│      ▼              ▼              ▼               │
│  Orders batched  Waves released  Tasks assigned    │
│  by rules        to robots       via FleetManager  │
└──────────────────────┬───────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────┐
│ C++ FLEET MANAGER (15Hz)                          │
│                                                   │
│ TaskManager → A* Path → NodeReservation →         │
│ BehaviorTree → MotionController → Robot moves     │
└──────────────────────────────────────────────────┘
```

### Container Lifecycle (Per User)

```
User clicks "Start Simulation"
    │
    ▼
Platform allocates:
    ├─ Unique port range (API: 8030, TCP: 65124, REST: 7013)
    ├─ Isolated Docker volumes (mongo_data_user123, etc.)
    └─ User's uploaded configs mounted
    │
    ▼
docker compose up -d (per-user compose file)
    │
    ├─ MongoDB starts         (5s)
    ├─ Redis starts           (1s)
    ├─ RabbitMQ starts        (5s)
    ├─ Mosquitto starts       (2s)
    │
    ├─ C++ FMS starts         (loads user's warehouse + robot YAML)
    ├─ Gazebo starts headless (loads user's world SDF)
    ├─ Python FastAPI starts  (connects to all services)
    │
    └─ Health check passes    (~60s total)
    │
    ▼
Platform returns: "Simulation running"
    │
    ▼
Browser connects:
    ├─ WebSocket: wss://platform/user123/ws/fleet
    ├─ REST poll: https://platform/user123/api/robots
    └─ Three.js renders 3D in real-time
    │
    ▼
User interacts: inject orders, watch robots, compare scenarios
    │
    ▼
User clicks "Stop Simulation"
    │
    ▼
docker compose down (volumes preserved for next session)
    │
    ▼
Platform returns: "Simulation stopped. Data saved."
```

---

---

## 6. Resource Estimates (SaaS)

| Metric | Per User | 10 Users | 100 Users |
|--------|----------|----------|-----------|
| **RAM** | ~3 GB | 30 GB | 300 GB (need autoscale) |
| **CPU** | ~2 cores | 20 cores | 200 cores |
| **GPU** | 0 (Three.js in browser) | 0 | 0 |
| **Startup** | ~60s | ~60s (parallel) | ~60s (parallel) |
| **Cost/month** | ~$5-10 | ~$50-100 | ~$500-1000 |
| **Disk** | ~2 GB volumes | 20 GB | 200 GB |

---

*This document is the single source of truth for P29a evolution.*
*Zero vendor references. Web-based SaaS. Three.js rendering. 10-field universal WMS.*

*Updated: 02-04-2026 | Method: 7-agent AFM parallel analysis (architecture + frontend + docker)*

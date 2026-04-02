# P29a Delta Blueprint — Robot / Map / WMS Agnostic Platform

**Date:** 02-04-2026
**Base:** P29 WRIE (18 phases, ~1,428+ tests, ~118 endpoints, 86+ audit)
**Goal:** Evolve P29 into a platform where ANY robot, ANY warehouse, ANY ERP plugs in and runs
**Strategy:** EVOLVE in place (85% codebase already agnostic) — NOT rebuild

---

## Table of Contents

1. [Current State Summary](#1-current-state-summary)
2. [Agnosticism Scorecard (Before/After)](#2-agnosticism-scorecard)
3. [File Fate Map — KEEP / MODIFY / CREATE](#3-file-fate-map)
4. [C++ Core (21 files)](#4-c-core)
5. [Python Routes (28 files)](#5-python-routes)
6. [Python Services](#6-python-services)
7. [Configs](#7-configs)
8. [Docker](#8-docker)
9. [Gazebo](#9-gazebo)
10. [Frontend](#10-frontend)
11. [New Files to Create](#11-new-files-to-create)
12. [Phase Plan](#12-phase-plan)
13. [Archived Documents](#13-archived-documents)

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

## 3. File Fate Map

```
KEEP:     ~85 files  (85%)
MODIFY:   ~15 files  (15%)
CREATE:   ~13 files  (new)
DELETE:    0 files
```

---

## 4. C++ Core

### KEEP (17 files — no changes needed)

| File | Why It's Already Agnostic |
|------|--------------------------|
| GraphMap.h/cpp | Loads ANY node/edge graph from config |
| AStar.h/cpp | Generic A*, 3 heuristics, any graph |
| NodeReservation.h/cpp | Generic mutex-based deadlock prevention |
| QuadTree.h/cpp | Pure spatial index, any coordinates |
| FleetManager.h/cpp | Orchestrates any robot type via RobotConfig |
| TaskManager.h/cpp | Generic allocation with `isTypeCompatible()` |
| COPPController.h/cpp | Generic cooperative path planning |
| RobotState.h/cpp | Generic state machine (IDLE/MOVING/CHARGING/etc.) |
| BatteryModel.h/cpp | All params from BatteryConfig YAML |
| ObstacleHandler.h/cpp | Thresholds from ObstacleThresholdsConfig |
| BTEngine.h/cpp | Loads ANY BTCPP v4 XML dynamically |
| ConditionNodes.h/cpp | Generic conditions (batteryLow, atTarget, etc.) |
| TCPServer.h/cpp | Generic TCP, callback-driven |
| RESTServer.h/cpp | Generic HTTP GET server |
| Config.h/cpp | Loads any YAML/JSON at runtime, action_codes from map |
| Types.h/cpp | RobotType: DIFFERENTIAL/UNI/OMNI, TaskType: MOVE/PICK/PLACE/CHARGE/PARK |
| Timer.h, Logger.h | Utility |

### MODIFY (3 files)

| File | Problem | Fix |
|------|---------|-----|
| **ActionNodes.cpp** | Lines 122-154: `action_code == 14` (load), `== 15` (unload) hardcoded | Read from `ctx.robot_config->action_codes["start_loading"]` map instead of literals |
| **ProtocolV1.h/cpp** | 33-field pipe-delimited format assumes all robots send same fields (motor_left_rpm, barcode_row, etc.) | Extract to ProtocolV1Adapter implementing new ProtocolAdapter interface |
| **MotionController.h/cpp** | P-controller assumes differential drive only (linear + angular) | Add MotionControllerFactory — instantiate per robot type (diff, omni, ackermann) |

### CREATE (3 new files)

| File | Purpose |
|------|---------|
| `include/rdt/network/ProtocolAdapter.h` + `src/network/ProtocolAdapter.cpp` | Abstract interface: `encode(RobotTelemetry)` / `decode(raw) -> RobotTelemetry`. Factory reads `robot_config.protocol_version`. ProtocolV1 becomes ProtocolV1Adapter. |
| `include/rdt/robot/RobotTelemetry.h` | Generic telemetry: pose, velocity, battery + `map<string,double> sensor_data` for protocol-specific extras |
| `include/rdt/robot/MotionControllerFactory.h` | Factory returns DiffDriveController / OmniController / AckermannController based on RobotType |

---

## 5. Python Routes

### KEEP (24 of 28 — no changes)

| Files | Why |
|-------|-----|
| fleet.py, robots.py, tasks.py | Generic CRUD, no robot assumptions |
| maps.py | Pure graph pathfinding |
| wes.py, waves.py | Generic order/wave pipeline |
| wms.py | Adapter pattern already works — adding SAP/Oracle = new adapter only |
| vda5050.py | VDA5050 IS the robot-agnostic standard |
| mapf.py | CBS/PIBT graph-agnostic solvers |
| inventory.py | Generic SKU/stock tracking |
| designer.py | Produces generic warehouse JSON |
| human_agents.py | Data-driven |
| ros2.py | HAL pattern extensible |
| scenarios.py, simulation.py | Config-driven |
| analytics.py, heatmap.py, stats.py, events.py | Pure data aggregation |
| telemetry.py, telemetry_export.py | Format-agnostic |
| reservations.py, config_routes.py, order_import.py | Generic |

### MODIFY (4 of 28)

| File | Problem | Fix |
|------|---------|-----|
| **wcs.py** | Lane types hardcoded enum (inbound/outbound/express/returns/staging) | Load lane types from YAML config instead |
| **iogita.py** | Coupled to io-gita KDTree/Hopfield backend — breaks if robot has no LiDAR | Create LocalizationEngine ABC, io-gita becomes one implementation |
| **charging.py** | Strategy logic hardcoded in engine | Create ChargeStrategy ABC (depot, in-situ, grid, custom) |
| **maintenance.py** | Linear degradation model only | Parametrize curve type (linear/Weibull/exponential) from config |

---

## 6. Python Services

### KEEP (fully generic)

| Directory | Files | Why |
|-----------|-------|-----|
| python/wes/ | 11 files | Order gen, task gen, wave engine, KPI, MAPF, scenarios — all generic |
| python/wms/ | 9 files | Adapter pattern excellent — webhook/SAP/Odoo all pluggable, DLQ generic |
| python/vda5050/ | 4 files | Standard protocol gateway, translator, MQTT client |
| python/services/human_agents/ | 3 files | Worker model, interaction manager, safety zones — data-driven |
| python/ros2_bridge/ | 3 files | HAL extensible, just needs brand-specific subclasses when needed |

### MODIFY

| Directory | Problem | Fix |
|-----------|---------|-----|
| python/wcs/ (4 files) | Sorter uses `startswith()` not regex. Lane types hardcoded. | Create RoutingStrategy interface (barcode, RFID, weight) |
| python/intelligence/iogita/ (6 files) | No localization abstraction | Create LocalizationEngine ABC wrapping io-gita |
| python/services/charging/ | Strategy hardcoded in engine | Create ChargeStrategy ABC |
| python/services/maintenance/ | Linear degradation only | Load curve type from config YAML |

---

## 7. Configs

### KEEP (no changes)

| Config | Why |
|--------|-----|
| configs/warehouses/*.json | Generic graph format (nodes, edges, zones) — any warehouse |
| configs/robots/*.yaml | Fully parameterized — motion, battery, sensors, action_codes |
| configs/wms/sku_catalog.yaml | Generic product metadata |
| configs/charging/strategy_profiles.yaml | Parameterized |
| configs/maintenance/component_profiles.yaml | Generic MTBF/degradation |
| configs/fleets/*.json | Robot composition — references robot config names |

### MODIFY

| Config | Problem | Fix |
|--------|---------|-----|
| configs/behavior_trees/*.xml | Action codes in XML should use config injection | Parameterize via `{{ACTION_CODE_LOAD}}` template substitution |
| configs/wcs/conveyor_layout.yaml | Sort rules site-specific | Provide template + document customization |
| configs/robots/*.yaml | Missing `gazebo_model` field | Add `gazebo_model: "manufacturer/model_name"` for Gazebo registry |

### CREATE

| Config | Purpose |
|--------|---------|
| configs/wms/translation_rules/sap.yaml | Declarative field mapping: `AUFNR -> order_id`, `MATNR -> sku` |
| configs/wms/translation_rules/oracle.yaml | Oracle ERP field mapping |
| configs/wms/translation_rules/generic_webhook.yaml | Template for custom ERP |

---

## 8. Docker

### KEEP

| File | Why |
|------|-----|
| docker/Dockerfile | Multi-stage build is clean and generic |
| docker/mosquitto/ | Standard MQTT config, environment-driven |

### MODIFY

| File | Problem | Fix |
|------|---------|-----|
| docker/docker-compose.yml | Default `WAREHOUSE_CONFIG=production_50x60` hardcoded. Missing `BEHAVIOR_TREE_CONFIG`, `FLEET_CONFIG`, `WCS_CONFIG` env vars. | Remove hardcoded defaults. Add all missing env vars. Fail-fast if not set. |
| docker/start.sh | Missing BT config handling. Silent failure if config file not found. | Add BT env var. `exit 1` on missing config instead of silent skip. |

---

## 9. Gazebo

### KEEP

| File/Dir | Why |
|----------|-----|
| gazebo/worlds/*.sdf (6 files) | Existing worlds still valid for testing |
| gazebo/models/generic/ (2 models) | Fallback models for any robot type |
| gazebo/worlds/gen_fleet_world.py | Robot spawning is generic |

### MODIFY

| File/Dir | Problem | Fix |
|----------|---------|-----|
| gazebo/models/addverb/ (5 models) | Vendor-specific, no registry | Robot YAML should declare `gazebo_model` field; spawn script reads it |
| gazebo/worlds/warehouse_distinct_generator.py | Hardcoded to one warehouse layout (40x30m, fixed zones) | Generalize: read ANY warehouse JSON + zone geometry template library |

### CREATE

| File/Dir | Purpose |
|----------|---------|
| gazebo/templates/zone_templates/ | SDF templates: shelf_row.sdf, charging_bay.sdf, conveyor_segment.sdf — generator picks by zone type |

---

## 10. Frontend

### KEEP (95%)

| File/Dir | Why |
|----------|-----|
| frontend/src/types.ts | Generic data contracts (RobotType: diff/uni/omni, MapNode, Task) |
| frontend/src/components/ (all) | Data-driven, graceful fallbacks for unknown types |
| frontend/src/hooks/ | Generic REST/WebSocket hooks |

### CREATE (Phase 2+)

| File/Dir | Purpose |
|----------|---------|
| frontend/src/pages/Onboarding/ | Setup wizard: upload warehouse -> add robots -> connect ERP -> test |

---

## 11. New Files to Create (Complete List)

### HIGH Priority (Phase 0-1)

| # | File | Purpose | Effort |
|---|------|---------|--------|
| 1 | `cpp/include/rdt/network/ProtocolAdapter.h` + `.cpp` | Abstract protocol interface (V1, V2, custom) | 2h |
| 2 | `cpp/include/rdt/robot/RobotTelemetry.h` | Generic telemetry bridge type | 1h |
| 3 | `cpp/include/rdt/robot/MotionControllerFactory.h` | Per-type controller instantiation | 3h |
| 4 | `python/intelligence/localization_engine.py` | Abstract localization (io-gita, barcode, RFID, custom) | 2h |
| 5 | `python/wms/adapter_registry.py` | Plugin registry for ERP adapters (register at runtime) | 1h |
| 6 | `python/wms/standard_order.py` | Standard inbound order Pydantic schema | 1h |

### MEDIUM Priority (Phase 2-3)

| # | File | Purpose | Effort |
|---|------|---------|--------|
| 7 | `python/wcs/routing_strategy.py` | Abstract sorter routing (barcode, RFID, weight) | 2h |
| 8 | `python/services/charging/charge_strategy.py` | Abstract charging interface (depot, in-situ, grid) | 2h |
| 9 | `configs/wms/translation_rules/sap.yaml` | Declarative SAP field mapping | 1h |
| 10 | `configs/wms/translation_rules/oracle.yaml` | Oracle ERP field mapping | 1h |
| 11 | `python/map_importer/dxf_converter.py` | AutoCAD DXF -> warehouse JSON | 4h |
| 12 | `python/map_importer/node_generator.py` | Auto-generate nodes from floor plan geometry | 3h |
| 13 | `gazebo/templates/zone_templates/` | Shelf, charger, conveyor SDF templates for world gen | 3h |

---

## 12. Phase Plan

### Phase 0 — Foundation (2 days)
**Goal:** Remove all hardcoded assumptions from C++ and Python core

1. Fix ActionNodes.cpp — config lookup instead of literal 14/15/31/51
2. Create ProtocolAdapter.h + RobotTelemetry.h
3. Wrap ProtocolV1 as ProtocolV1Adapter
4. Create adapter_registry.py for WMS plugins
5. Create standard_order.py (Pydantic inbound schema)
6. Fix docker-compose.yml defaults + start.sh fail-fast

### Phase 1 — Robot Agnostic (3 days)
**Goal:** Any robot plugs in with a YAML config

7. Create MotionControllerFactory (diff, omni, ackermann)
8. Create LocalizationEngine ABC (io-gita becomes one impl)
9. Add `gazebo_model` field to robot YAML configs
10. Update Gazebo spawn script to read model from robot config
11. Create ChargeStrategy ABC
12. Parametrize maintenance degradation curves

### Phase 2 — Map Agnostic (2 days)
**Goal:** Any warehouse layout generates a working simulation

13. Generalize warehouse_distinct_generator.py for ANY warehouse JSON
14. Create zone geometry template library (shelf, charger, conveyor SDF)
15. Create DXF importer (AutoCAD floor plan -> warehouse JSON)
16. Create auto-node-generator (floor plan -> node graph)

### Phase 3 — WMS Agnostic (2 days)
**Goal:** Any ERP sends orders and they flow through

17. Create declarative translation rules (YAML field mapping per ERP)
18. Create Oracle adapter
19. Create NetSuite adapter stub
20. Enable multi-ERP routing (not singleton connector)
21. Fix WCS: load lane types from YAML, create RoutingStrategy interface

### Phase 4 — Platform (5 days)
**Goal:** Self-service onboarding

22. Dynamic robot registration API (add robots at runtime, not just config)
23. Onboarding wizard (frontend: upload warehouse -> add robots -> connect ERP -> test)
24. Multi-tenant support (tenant-isolated app_state)
25. Standard order validation + DLQ for malformed orders

---

## 13. Archived Documents

The following documents from P29 have been moved to `_archive/docs_pre_p29a/` as they reflect the pre-agnostic state. They remain available as historical reference but are superseded by this document.

| Document | Original Location | Status |
|----------|------------------|--------|
| PROJECT_29_COMPLETE_REFERENCE.md | Both dirs | Superseded by this blueprint |
| FEATURE_TABLE.md | Parent dir | Features list still valid, counts updated here |
| ARCHITECTURE.md | Parent dir | Architecture unchanged, agnostic layer added on top |
| SUMMARY.md | Parent dir | Summary outdated (old test/endpoint counts) |
| EXECUTION_PLAN.md | Digital twin dir | P29 execution complete, P29a plan replaces |
| MASTER_PLAN.md | Digital twin dir | Replaced by Phase Plan above |
| PROJECT_PLAN.md | Digital twin dir | Replaced by Phase Plan above |
| PROJECT_SUMMARY_1PAGE.md | Digital twin dir | Outdated |
| ROADMAP.md | Digital twin dir | Replaced by Phase Plan above |
| SIMULATION_SUMMARY.md | Digital twin dir | Outdated |
| PLAN_PHASES_16_18.md | Parent dir | Phases 16-18 complete |
| SYNTHETIC_DATA_AUDIT_REPORT.md | Parent dir | Historical audit |
| iogita_presentation.md | Parent dir | Historical |
| MANUAL_DEPS_INSTALL.md | Parent dir | Docker handles deps now |
| warehouse_sim_prompt.md | Parent dir | Historical prompt |

**CLAUDE.md is NOT archived** — it contains active project rules.

---

## 14. Complete System Flowchart — Web-Based SaaS Simulation

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

## 15. Updated Phase Plan (with SaaS + 3D)

### Phase 0 — Foundation + Vendor Cleanup (2 days)
1. Scrub all vendor references from code (~15 files)
2. Fix ActionNodes.cpp — config lookup for action codes
3. Create ProtocolAdapter.h + RobotTelemetry.h + ProtocolAdapter.cpp
4. Create adapter_registry.py + standard_order.py
5. Fix docker-compose.yml defaults + start.sh fail-fast
6. Add `gazebo_model` field to robot YAML configs
7. Create `gazebo/models/vendors/README.md`

### Phase 1 — Robot Agnostic (3 days)
8. Create MotionControllerFactory (diff, omni, ackermann)
9. Create LocalizationEngine ABC
10. Create ChargeStrategy ABC
11. Create omnidirectional.yaml + default_omni.xml + Gazebo omni model
12. Parametrize maintenance degradation curves
13. Update spawn_fleet.py for registry-based model loading

### Phase 2 — Map Agnostic (2 days)
14. Generalize warehouse_distinct_generator.py for ANY warehouse JSON
15. Create zone geometry templates (shelf, charger, conveyor SDF)
16. Create DXF importer + auto-node-generator
17. Create map_importer package with tests

### Phase 3 — WMS Agnostic (2 days)
18. Create declarative translation rules (YAML field mapping)
19. Create Oracle + generic_webhook translation rules
20. Enable multi-ERP routing in main.py
21. Fix WCS: load lane types from YAML, create RoutingStrategy
22. Implement 10-field standard order validation

### Phase 4 — Auth + User Accounts (3 days)
23. Add auth service (JWT signup/login/verify)
24. Add user database (PostgreSQL — accounts, configs, sessions)
25. Add file upload API (warehouse JSON, robot YAML, SDF models)
26. Per-user config storage (S3 or local volume)
27. Protect all API routes with JWT middleware

### Phase 5 — Container Orchestration (3 days)
28. Per-user docker-compose template generation
29. Port allocation manager (no conflicts)
30. Container lifecycle API: create / start / stop / status / destroy
31. Volume isolation per user
32. Health check + readiness polling
33. Reverse proxy routing (nginx: /user123/* → user's container)

### Phase 6 — Onboarding Wizard (3 days)
34. Add React Router (page routing)
35. Login/Signup pages
36. 4-step onboarding wizard:
    - Step 1: Choose/upload warehouse (template picker + file upload + designer)
    - Step 2: Choose/upload robots (generic type sliders + custom YAML)
    - Step 3: Connect WMS (10-field mapping form + webhook URL display)
    - Step 4: Review + launch
37. Save onboarding state to user DB

### Phase 7 — 3D Visual Upgrade (2 days)
38. Source/create GLTF robot models (AMR, AGV, Forklift, Omni)
39. Load GLTF via `useGLTF()` in Warehouse3D.tsx (replace primitive boxes)
40. Add `web_model` field to robot YAML → Three.js loads matching .glb
41. Warehouse furniture models (shelves, conveyors, chargers as GLTF)
42. Optional: LiDAR ray visualization, path trails

### Phase 8 — Polish + Testing (3 days)
43. End-to-end test: signup → onboard → simulate → results
44. Load testing: 10 concurrent user containers
45. WebSocket stability under multi-user load
46. PDF/CSV report generation + download
47. Scenario comparison export
48. Error handling: container crash recovery, stale session cleanup

---

## 16. Resource Estimates (SaaS)

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

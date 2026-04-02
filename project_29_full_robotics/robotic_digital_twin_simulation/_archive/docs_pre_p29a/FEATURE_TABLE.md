# Project 29 — Warehouse Robotics Digital Twin: Complete Feature Table

> **Single-table reference** for the entire system: C++ FMS (15Hz) + Python FastAPI (118 endpoints) + React 3D Dashboard + 8 Docker services + io-gita intelligence.
>
> **Live at:** http://localhost:8029/dashboard | API docs: http://localhost:8029/docs

| # | Area | Feature | What It Does | How To Use | Key Technical Detail |
|---|------|---------|-------------|------------|---------------------|
| | **C++ FMS CORE** | | | **Ports: TCP 65123, REST 7012** | |
| 1 | FMS Core | 15Hz Fleet Loop | Orchestrates entire fleet at 66ms cycle: TCP → state → BT → allocate → path → command → persist | Starts automatically in Docker (`start.sh`) | Per-cycle profiling: tcp/state/bt/alloc/path/cmd/write in ms |
| 2 | FMS Core | TCP Robot Protocol (ProtocolV1) | Bi-directional robot communication — telemetry in, commands out | Connect robot/simulator to `localhost:65123` | Newline-delimited frames: `robot_id\|timestamp\|type\|payload` |
| 3 | FMS Core | C++ REST API | Fleet status queries from C++ engine directly | `GET http://localhost:7012/api/robots` | JSON responses, healthcheck at `/health` |
| 4 | FMS Core | A* Path Planner | Shortest path between warehouse nodes | Used internally by FleetManager per cycle | Euclidean heuristic on GraphMap adjacency |
| 5 | FMS Core | Node Reservation | Greedy multi-robot deadlock prevention | Automatic — reserves 4 nodes ahead per robot | Circular-wait detection, mutual exclusion on nodes |
| 6 | FMS Core | Behavior Trees | Per-robot decision trees (idle→move→load→unload→charge) | Configured via `configs/behavior_trees/` YAML | Ticked every 15Hz cycle by FleetManager |
| 7 | FMS Core | Battery Model | Energy consumption + charging simulation per robot | Params from `configs/robots/*.yaml` | Drain during motion/load, charge rate at dock nodes |
| 8 | FMS Core | Task Allocation | Assigns tasks to available robots by strategy | Strategy set per scenario (FIFO / nearest / priority-weighted) | Runs in allocation phase of 15Hz loop |
| 9 | FMS Core | COPP Controller | Cooperative collision-free path coordination | Automatic — combines A* + NodeReservation across fleet | Multi-robot path deconfliction |
| 10 | FMS Core | QuadTree Spatial Index | Fast obstacle proximity queries | Used by ObstacleHandler for collision checks | Spatial partitioning of warehouse area |
| | **FLEET MANAGEMENT API** | | | **Base: http://localhost:8029** | |
| 11 | Fleet API | Robot List | All robots with full status (position, battery, task, model) | `GET /api/robots` | Returns `robot_id`, `position.{x,y,node}`, `battery_pct`, `status` |
| 12 | Fleet API | Robot Detail | Single robot with all telemetry fields | `GET /api/robots/{id}` | Includes firmware_version, odometry_km, max_payload_kg |
| 13 | Fleet API | Robot Command | Send action to specific robot (move, load, charge) | `POST /api/robots/{id}/command` body: `{action, target_node}` | Queued in MongoDB `commands` collection |
| 14 | Fleet API | Fleet Status | Aggregate fleet overview | `GET /api/fleet/status` | `total_robots`, status counts, `utilisation_pct` |
| 15 | Fleet API | Telemetry History | Time-series telemetry for a robot | `GET /api/telemetry/{id}?limit=100` | Up to 10,000 points from InfluxDB |
| 16 | Fleet API | Active Reservations | Current node reservations (collision prevention) | `GET /api/reservations/active` | Shows which robot holds which node |
| | **TASK MANAGEMENT** | | | | |
| 17 | Tasks | Task List | All tasks with status, assignment, progress | `GET /api/tasks` | Paginated (default 10,000 cap) |
| 18 | Tasks | Create Task | New pick-and-drop task | `POST /api/tasks` body: `{type, source_node, destination_node, priority}` | Auto-assigned to nearest available robot |
| 19 | Tasks | Task Detail | Single task with full lifecycle timestamps | `GET /api/tasks/{id}` | Includes created_at, started_at, completed_at |
| 20 | Tasks | Cancel Task | Stop a running or pending task | `POST /api/tasks/{id}/cancel` | Robot returns to idle state |
| | **WAREHOUSE MAP** | | | | |
| 21 | Map | Full Map | Complete warehouse graph (nodes + edges + zones) | `GET /api/map` | 25 nodes, 40 edges in simple_grid config |
| 22 | Map | Node List | All warehouse nodes with position and type | `GET /api/map/nodes` | Types: pick, drop, shelf, charge, aisle, hub, staging |
| 23 | Map | Zone List | All warehouse zones | `GET /api/map/zones` | 8 zones in simple_grid config |
| 24 | Map | Path Query | Compute A* path between two nodes | `GET /api/map/path?from=DOCK_1&to=S_33` | Returns ordered node list + total distance + hops |
| | **WES (Warehouse Execution)** | | | | |
| 25 | WES | Inject Orders | Generate orders into WES pipeline | `POST /api/wes/inject-orders` body: `{num_orders, type}` | Creates random pick/drop orders from node types |
| 26 | WES | WES KPIs | Live execution metrics | `GET /api/wes/kpi` | orders/hr, pick_accuracy_%, throughput, cycle_time_s |
| 27 | WES | Wave List | All waves (pending/active/completed) | `GET /api/wes/waves` | Each wave groups orders for batch release |
| 28 | WES | Create Wave | Group pending orders into a wave (manual or auto-rule) | `POST /api/wes/waves` body: `{order_ids}` or empty for auto | Auto mode applies wave rules from rule engine |
| 29 | WES | Release Wave | Convert wave orders → robot tasks | `POST /api/wes/waves/{id}/release` | Generates pick-and-drop task pairs from orders |
| 30 | WES | Wave Rules | CRUD for automatic wave generation rules | `GET/POST /api/wes/wave-rules` | Conditions: order_count, priority, zone_affinity |
| | **WCS (Warehouse Control)** | | | | |
| 31 | WCS | Conveyor Segments | All conveyor belt segments with speed/status/jam state | `GET /api/wcs/conveyors` | Each segment: id, speed_mps, status, jammed flag |
| 32 | WCS | Conveyor Control | Start/stop/set_speed/maintenance per segment | `POST /api/wcs/conveyors/{id}/control` body: `{action, speed}` | Actions: start, stop, set_speed, maintenance |
| 33 | WCS | Emergency Stop All | Stop all conveyor segments instantly | `POST /api/wcs/conveyors/stop-all` | Sets all segments to stopped state |
| 34 | WCS | Package Transfer | Move package between conveyor segments | `POST /api/wcs/conveyors/transfer` body: `{package_id, from, to}` | Updates package journey events |
| 35 | WCS | Sorter Rules | Barcode pattern → target lane routing | `GET/POST/DELETE /api/wcs/sorter/rules` | Regex patterns, max 500 rules |
| 36 | WCS | Sort Package | Run barcode through sorter rules → determine lane | `POST /api/wcs/sorter/sort` body: `{barcode}` | Handles misreads (empty barcode → default lane) |
| 37 | WCS | Sorter Stats | Sort performance metrics | `GET /api/wcs/sorter/stats` | Total sorts, errors, misreads, per-rule hit counts |
| 38 | WCS | Lane Management | All storage lanes (inbound/outbound/express/returns/staging) | `GET /api/wcs/lanes` or `/by-type/{type}` | Open/close lanes, add/remove packages |
| 39 | WCS | Package Tracking | Full lifecycle tracking per package | `GET /api/wcs/packages/{id}` | Journey: created→sorted→transferred→delivered with events |
| 40 | WCS | Packages In Transit | All packages currently moving | `GET /api/wcs/packages/in-transit` | Filter: currently between locations |
| 41 | WCS | WCS System Stats | Combined conveyor + sorter + lane + package stats | `GET /api/wcs/stats` | Aggregated health dashboard for material handling |
| | **WMS (Warehouse Management)** | | | | |
| 42 | WMS | Connector Status | WMS/ERP connector health | `GET /api/wms/status` | Type (SAP/Odoo/webhook), connected flag, DLQ summary |
| 43 | WMS | Sync Orders | Pull orders from WMS system | `POST /api/wms/sync` | Translates external format → internal orders |
| 44 | WMS | Webhook Receive | Receive order via HTTP webhook | `POST /api/wms/webhook/receive` body: `{items, priority}` | For custom ERP integrations |
| 45 | WMS | Synced Orders | List orders received from WMS | `GET /api/wms/orders?offset=0&limit=50` | Paginated, capped at 10,000 in memory |
| 46 | WMS | Dead Letter Queue | Failed orders awaiting retry | `GET /api/wms/dlq` | RabbitMQ-backed persistent error queue |
| 47 | WMS | DLQ Retry | Retry a failed order | `POST /api/wms/dlq/{id}/retry` | Re-processes through OrderTranslator |
| | **INVENTORY (WMS Phase 14)** | | | | |
| 48 | Inventory | SKU Catalog | All SKUs with metadata | `GET /api/inventory/skus` | From `configs/wms/sku_catalog.yaml` |
| 49 | Inventory | Stock Levels | Current stock per SKU across all nodes | `GET /api/inventory/stock-levels` | Includes min/max/reorder_point/reorder_qty |
| 50 | Inventory | Stock at Node | Inventory at specific warehouse location | `GET /api/inventory/stock/{node_name}` | Per-node breakdown by SKU |
| 51 | Inventory | Receive (Putaway) | Add inventory (inbound goods) | `POST /api/inventory/receive` body: `{sku_id, node, qty}` | Logs movement with reason "receive" |
| 52 | Inventory | Pick (Outbound) | Remove inventory for order fulfillment | `POST /api/inventory/pick` body: `{sku_id, node, qty}` | Validates sufficient stock before picking |
| 53 | Inventory | Adjust (Cycle Count) | Correct stock after physical count | `POST /api/inventory/adjust` body: `{sku_id, node, qty, reason}` | Audit trail in movements log |
| 54 | Inventory | Transfer | Move stock between nodes | `POST /api/inventory/transfer` body: `{sku_id, from_node, to_node, qty}` | Two movements: out + in |
| 55 | Inventory | Cycle Count | Perform count at node, auto-adjust discrepancies | `POST /api/inventory/cycle-count` body: `{node, counts: [{sku_id, qty}]}` | Generates adjustment movements |
| 56 | Inventory | Stock Movements | Audit log of all inventory changes | `GET /api/inventory/movements?limit=50` | Timestamp, SKU, node, qty_change, reason |
| 57 | Inventory | Replenishment Check | Scan all SKUs, generate orders where stock < reorder_point | `POST /api/inventory/replenishment/check` | Creates replenishment orders automatically |
| 58 | Inventory | Replenishment Queue | Pending replenishment orders | `GET /api/inventory/replenishment` | Status: pending, in_progress, completed, cancelled |
| 59 | Inventory | ABC Analysis | Classify SKUs by pick frequency (A/B/C) | `GET /api/inventory/optimizer/abc` | A = top 20% picks, B = next 30%, C = remaining 50% |
| 60 | Inventory | Slotting Recommendations | Move fast-movers closer to pick zones | `GET /api/inventory/optimizer/recommendations` | Suggests node reassignments for efficiency |
| 61 | Inventory | Zone Balance | Inventory distribution heatmap across zones | `GET /api/inventory/optimizer/zone-balance` | Identifies over/under-stocked zones |
| 62 | Inventory | Inventory Stats | Combined inventory + replenishment + optimizer stats | `GET /api/inventory/stats` | Single endpoint for dashboard KPI panel |
| | **VDA5050 PROTOCOL** | | | **MQTT: localhost:1883, WS: 9001** | |
| 63 | VDA5050 | Gateway Status | MQTT broker connection + AGV count | `GET /api/vda5050/status` | `broker_connected`, `agvs_online`, `agvs_total` |
| 64 | VDA5050 | Send Order | Dispatch VDA5050 order to AGV via MQTT | `POST /api/vda5050/orders` body: VDA5050 JSON (nodes, edges, actions) | Max 500 nodes per order, 200 AGVs |
| 65 | VDA5050 | Instant Action | Emergency commands (E-stop, cancel, pause) | `POST /api/vda5050/instant-actions` body: `{agv_id, action}` | Immediate MQTT publish, no queuing |
| 66 | VDA5050 | AGV List | All connected AGVs with latest state | `GET /api/vda5050/agvs` | State cached from MQTT subscriptions |
| 67 | VDA5050 | AGV State | Latest VDA5050 state for specific AGV | `GET /api/vda5050/agvs/{id}/state` | Full VDA5050 state JSON |
| | **MAPF (Multi-Agent Path Finding)** | | | | |
| 68 | MAPF | CBS Solver | Optimal multi-agent path planning | `POST /api/mapf/solve` body: `{agents: [{id, start, goal}], solver: "cbs"}` | Conflict-Based Search, max 200 agents |
| 69 | MAPF | PIBT Solver | Fast real-time path planning | `POST /api/mapf/solve` body: `{agents: [...], solver: "pibt"}` | Priority Inheritance + Backtracking, max 500 agents, linear time |
| 70 | MAPF | PIBT Step | Single-tick move for 15Hz integration | `POST /api/mapf/step` body: `{agents: [{id, pos, goal}]}` | Returns one move per agent per call |
| 71 | MAPF | Solver Status | Last solve time, conflicts found, total solves | `GET /api/mapf/status` | Performance tracking for solver tuning |
| 72 | MAPF | Benchmarks | Solve time vs agent count history | `GET /api/mapf/benchmarks` | Graph data for performance analysis |
| 73 | MAPF | Congestion Map | Traffic hotspots + top 10 bottleneck nodes | `GET /api/mapf/congestion` | Fed by CongestionTracker after each solve/step |
| | **SCENARIO SIMULATION** | | | | |
| 74 | Scenarios | Create Scenario | Define simulation config (fleet size, warehouse, strategy) | `POST /api/scenarios` body: `{name, fleet_size, warehouse_config, strategy}` | Saved to MongoDB `scenarios` collection |
| 75 | Scenarios | Run Scenario | Execute: generate orders → simulate → compute KPIs | `POST /api/scenarios/{id}/run` | Full WES pipeline with task allocation + completion |
| 76 | Scenarios | Scenario Results | KPIs for completed scenario | `GET /api/scenarios/{id}/results` | throughput, avg_cycle_time, utilization, completed, failed |
| 77 | Scenarios | Compare Scenarios | Side-by-side KPI comparison (2+ scenarios) | `GET /api/scenarios/compare?ids=A,B` | Export: JSON, CSV, or PDF report |
| 78 | Scenarios | Archive Scenario | Clean up scenario data | `DELETE /api/scenarios/{id}` | Moves to archive, drops temp collections |
| | **FAULT INJECTION & SIMULATION** | | | | |
| 79 | Simulation | Simulation Status | Current sim state (running, tick count, active faults) | `GET /api/simulation/status` | Shows injected faults and their remaining duration |
| 80 | Simulation | Start/Stop Sim | Control simulation loop | `POST /api/simulation/start` or `/stop` | Toggles internal simulation ticker |
| 81 | Simulation | Inject Fault | Resilience testing (battery drain, obstacle, network, motor) | `POST /api/simulation/inject-fault` body: `{robot_id, type, duration_s}` | Types: battery_drain, obstacle, network_loss, motor_fault |
| | **io-gita INTELLIGENCE** | | | | |
| 82 | Intelligence | Engine Status | io-gita version, backend, zone/node counts | `GET /api/iogita/status` | v5.0, backend=kdtree, 8 zones, 25 nodes |
| 83 | Intelligence | Zone Identification | Identify which zone each robot is in | `GET /api/iogita/zones` | KDTree nearest-neighbor, 0.008ms per query |
| 84 | Intelligence | Cold Start Recovery | Recover lost robot position (hint-based, no LiDAR) | `POST /api/iogita/cold-start/{robot_id}` body: `{hint_x, hint_y}` | 5-phase: scan → zone ID → dual scan → graph → AMCL fallback |
| 85 | Intelligence | Full LiDAR Recovery | KDTree-based 360° scan recovery | `POST /api/iogita/recover/{robot_id}` body: `{scan_data}` | Direct KDTree engine query, 525x faster than Hopfield ODE |
| 86 | Intelligence | KDTree Engine | Spatial nearest-neighbor for zone/node ID | Internal (wrapped by `_KDTreeZoneAdapter`) | 0.008ms, 329x less memory than Hopfield, same 97.2% accuracy |
| 87 | Intelligence | Hopfield ODE (v4 fallback) | Neural ODE zone classifier | Fallback if KDTree import fails | D=10,000 dims, 4.197ms, preserved as backup only |
| 88 | Intelligence | Dual Scan | Corridor disambiguation via two-position scan | `dual_scan.py` — called internally during cold start | Breaks LiDAR symmetry in identical-looking aisles |
| 89 | Intelligence | Safety Checker | Validates clearances before recovery moves | `safety_checker.py` — called during cold start phases | Prevents collision during localization |
| 90 | Intelligence | Symmetry Breaker | Breaks aisle alignment symmetries in LiDAR scans | `symmetry_breaker.py` — called by zone identifier | Resolves mirror-image warehouse sections |
| | **ROS2 BRIDGE** | | | | |
| 91 | ROS2 | Bridge Status | ROS2 availability + mode (live/sim) | `GET /api/ros2/status` | Shows topic count, bridge mode |
| 92 | ROS2 | Topic List | Active ROS2 topics (or simulated) | `GET /api/ros2/topics` | Simulated when ROS2 unavailable |
| 93 | ROS2 | Navigation Goal | Send nav2 goal to robot | `POST /api/ros2/nav-goal` body: `{robot_id, x, y, theta}` | Rate limited: 100 goals/min per robot |
| 94 | ROS2 | Robot Pose | Get robot position from ROS2 odom | `GET /api/ros2/pose/{id}` | Falls back to simulation pose |
| | **ANALYTICS & MONITORING** | | | | |
| 95 | Analytics | Fleet Analytics | Fleet-wide KPIs (throughput, avg task time, avg battery) | `GET /api/analytics/fleet` | Handles both nested `battery.charge_pct` and flat `battery_pct` |
| 96 | Analytics | A/B Comparison | Compare task allocation strategies | `GET /api/analytics/ab-comparison` | Strategies: fifo, nearest, priority_weighted |
| 97 | Analytics | Heat Map | Robot traffic density grid | `GET /api/analytics/heatmap?duration=1h&resolution=0.5` | Grid cells with visit counts + zone congestion overlay |
| 98 | Analytics | Throughput Stats | Task completion rates over time window | `GET /api/stats/throughput` | Windowed metrics for trend analysis |
| 99 | Analytics | System Events | Filtered event log (severity, robot_id) | `GET /api/events?severity=warning&robot_id=DYN-001` | Event types: info, warning, error, critical |
| 100 | Analytics | Robot Config | Loaded robot configuration from YAML | `GET /api/config/robots` | Returns runtime config (mass, speed, battery, wheels) |
| | **DESIGNER (Layout Editor)** | | | | |
| 101 | Designer | Validate Layout | Check warehouse JSON for errors | `POST /api/designer/validate` body: warehouse JSON | Checks: node uniqueness, edge validity, zone coverage |
| 102 | Designer | Export Layout | Save designed warehouse to `configs/warehouses/` | `POST /api/designer/export` body: `{name, config}` | Writes JSON file to disk |
| 103 | Designer | Templates | Pre-built warehouse templates by size/type | `GET /api/designer/templates` | Categories: small (<15), medium (15-30), large (31-60), addverb |
| 104 | Designer | Import Layout | Load existing warehouse JSON into editor | `POST /api/designer/import` body: warehouse JSON | Converts to editor format |
| 105 | Designer | Validate 3D | 3D layout check with conveyor paths + charge stations | `POST /api/designer/validate-3d` body: layout JSON | Recommends charge station placement |
| 106 | Designer | Export Bundle | Full config bundle (warehouse + conveyor YAML + fleet) | `POST /api/designer/export-all` body: complete design | Generates all config files at once |
| 107 | Designer | Auto-Generate Edges | Create edges between nearby nodes by distance | `POST /api/designer/auto-edges` body: `{nodes, max_distance}` | Distance-based edge generation |
| 108 | Designer | Scale Template | Scale warehouse template up/down | `POST /api/designer/template/scale` body: `{template, factor}` | Multiplies node positions + adds proportional nodes |
| | **HEALTH & SYSTEM** | | | | |
| 109 | Health | Health Check | Real service probes (not hardcoded) | `GET /health` | MongoDB ping, Redis PING, InfluxDB /health, RabbitMQ mgmt API |
| 110 | Health | WebSocket | Real-time fleet events (pose updates, state changes) | `ws://localhost:8029/ws/fleet` | Push events to 3D dashboard without polling |
| 111 | Health | API Docs | Auto-generated OpenAPI/Swagger | `GET /docs` (Swagger UI) or `/redoc` (ReDoc) | Full endpoint documentation |
| | **REACT DASHBOARD** | | | **http://localhost:8029/dashboard** | |
| 112 | Frontend | 2D Warehouse Grid | Top-down node/edge map with robot positions | Dashboard → **2D** tab | Shows nodes by type (color-coded), robot dots, edges |
| 113 | Frontend | 3D Warehouse View | Interactive Three.js 3D scene | Dashboard → **3D** tab | Robot models, path highlighting, camera follow mode |
| 114 | Frontend | Warehouse Designer | Interactive drag-and-drop layout editor | Dashboard → **Designer** tab | Place nodes, draw edges, assign zones, validate, export |
| 115 | Frontend | Robot Status Panel | Real-time robot grid (ID, status, battery, position, task) | Dashboard → right panel (always visible) | Click robot to select/follow in 3D view |
| 116 | Frontend | Task Queue | Active tasks with source/dest/priority/robot | Dashboard → right panel | Color-coded by status (pending/assigned/in_progress) |
| 117 | Frontend | Battery Levels | Fleet battery histogram | Dashboard → row 2 | Visual alert for robots below 25% |
| 118 | Frontend | Fleet Analytics Panel | Fleet-wide KPI cards | Dashboard → row 2 | Tasks, throughput, avg time, avg battery, robot count |
| 119 | Frontend | WES KPI Panel | Warehouse execution metrics | Dashboard → row 2 | Orders/hr, pick accuracy, throughput, cycle time |
| 120 | Frontend | Wave Status Panel | Wave management (create/release/monitor) | Dashboard → row 2 | Pending/active/completed wave cards |
| 121 | Frontend | Heat Map Controls | Toggle + configure traffic heat map overlay | Dashboard → row 1 (next to map) | Duration slider (1h/4h/24h), resolution control |
| 122 | Frontend | Scenario Panel | Create/run/compare simulation scenarios | Dashboard → row 3 (left) | Launch comparison dashboard overlay |
| 123 | Frontend | Scenario Comparison | Full-screen side-by-side KPI comparison | Triggered from Scenario Panel → Compare | Bar charts, export to CSV/PDF |
| 124 | Frontend | VDA5050 Panel | AGV gateway status + connected AGVs | Dashboard → row 3 (right) | Broker status, online/total AGV count |
| 125 | Frontend | Congestion Panel | MAPF congestion hotspots + bottleneck nodes | Dashboard → row 4 (left) | Top bottleneck nodes with traffic count |
| 126 | Frontend | WMS Panel | WMS/ERP connector status + synced orders | Dashboard → row 4 (right) | Connector type, DLQ count, last sync time |
| 127 | Frontend | 3D Error Boundary | Catches Three.js crashes, falls back to 2D | Automatic — wraps Warehouse3D | "3D scene crashed" → Retry button |
| 128 | Frontend | Follow Mode | Camera tracks selected robot in 3D | 3D tab → select robot → click **Follow** | Smooth camera interpolation |
| | **DOCKER INFRASTRUCTURE** | | | | |
| 129 | Infra | MongoDB 7 | State IPC: robots, tasks, orders, all collections | `localhost:27017` (auth: rdt/changeme) | 20+ collections, motor async driver |
| 130 | Infra | RabbitMQ 3 | Task queue, event bus, DLQ for failed orders | `localhost:5672` (AMQP), `localhost:15672` (mgmt UI) | User: fms/changeme, management plugin enabled |
| 131 | Infra | Redis 7 | Real-time cache (robot positions, telemetry) | `localhost:6380` (mapped from 6379 in Docker) | Password: changeme, used for hot data |
| 132 | Infra | InfluxDB 2 | Time-series telemetry storage | `localhost:8086` | Org: rdt, Bucket: fleet_telemetry, Token: changeme |
| 133 | Infra | Mosquitto 2 | MQTT broker for VDA5050 AGV protocol | `localhost:1883` (MQTT), `localhost:9001` (WebSocket) | Configured via `docker/mosquitto/mosquitto.conf` |
| 134 | Infra | Grafana | Telemetry dashboards (InfluxDB data source) | `http://localhost:3000` (admin/changeme) | Pre-configured for fleet health, battery, throughput |
| 135 | Infra | ROS2 Bridge | nav2 integration container (ROS Humble) | Automatic in Docker — connects to rdt API | Subscribes to odom/scan, publishes nav goals |
| | **CONFIGURATION** | | | | |
| 136 | Config | Warehouse JSON | Node/edge/zone definitions | `configs/warehouses/simple_grid.json` | 25 nodes, 40 edges, 8 zones, grid_spacing_m |
| 137 | Config | Robot YAML | Robot parameters (mass, speed, battery, wheels) | `configs/robots/differential_drive.yaml` | Also: amr500.yaml, zippy10.yaml (Addverb models) |
| 138 | Config | SKU Catalog | Product definitions for inventory | `configs/wms/sku_catalog.yaml` | SKU ID, name, weight, dimensions, reorder_point |
| 139 | Config | Conveyor Layout | Conveyor segment definitions | `configs/wcs/conveyor_layout.yaml` | Segment IDs, connections, speeds, types |
| 140 | Config | Fleet Presets | Addverb robot presets (Dynamo/Veloce/Quadron) | `configs/robots/` + `configs/fleet/` | Phase 9: real Addverb AMR parameters |
| 141 | Config | Environment Vars | Docker service configuration | Set in `docker-compose.yml` environment block | WAREHOUSE_CONFIG, ROBOT_CONFIG, API_PORT, LOG_LEVEL |
| | **TESTING & QUALITY** | | | | |
| 142 | Testing | C++ gtest | 371 tests — network, navigation, collision, BT | `cd build && ctest` | TCP socket binding requires non-sandboxed env |
| 143 | Testing | Python pytest | 800+ tests — API, WES/WCS/WMS, intelligence | `cd python && pytest` | Real connections, graceful degradation (no MagicMock) |
| 144 | Testing | Playwright E2E | Dashboard UI interaction tests | `npx playwright test` | headless:false, slowMo:500, screenshot every state |
| 145 | Testing | Phase Audits | External review per phase (Kimi/Gemini/Codex) | Manual — audit scores in `audit/` directory | 85% minimum on first audit per CLAUDE.md |
| 146 | Testing | 1200+ Total Tests | Combined across all phases (0 failures) | Full suite: gtest + pytest + playwright | Covers all 118 endpoints + C++ core |

## Quick Start

```bash
# 1. Start all services
cd robotic_digital_twin_simulation
docker compose -f docker/docker-compose.yml up -d

# 2. Wait for health (30s for C++ compile + startup)
curl http://localhost:8029/health

# 3. Open dashboard
open http://localhost:8029/dashboard

# 4. Open API docs
open http://localhost:8029/docs

# 5. Open Grafana
open http://localhost:3000  # admin/changeme
```

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                    React 3D Dashboard (:8029/dashboard)           │
│  [2D Grid] [3D Three.js] [Designer] [Panels×12] [WebSocket]     │
└──────────────────────┬───────────────────────────────────────────┘
                       │ HTTP + WS
┌──────────────────────▼───────────────────────────────────────────┐
│              Python FastAPI (:8029) — 118 REST endpoints          │
│  Fleet│Tasks│WES│WCS│WMS│Inventory│VDA5050│MAPF│Scenarios│io-gita │
└──┬────┬────┬────┬────┬────┬────┬─────────────────────────────────┘
   │    │    │    │    │    │    │
   ▼    ▼    ▼    ▼    ▼    ▼    ▼
┌─────┐┌─────┐┌─────┐┌──────┐┌──────────┐┌──────────────────────┐
│Mongo││Redis││Influx││Rabbit││Mosquitto ││  C++ FMS (:7012/65123)│
│:2701││:6380││:8086 ││:5672 ││:1883/9001││  15Hz loop, A*, BT   │
│state││cache││telem ││queue ││VDA5050   ││  NodeRes, COPP, TCP  │
└─────┘└─────┘└─────┘└──────┘└──────────┘└──────────────────────┘
                                              │
                                    ┌─────────▼──────────┐
                                    │  ROS2 Bridge        │
                                    │  nav2 + HAL         │
                                    │  (ROS Humble)       │
                                    └─────────────────────┘
```

# WAREHOUSE ROBOTICS INTELLIGENCE ENGINE — SIMULATION PROMPT

## ALIGNED TO ADDVERB FLEET_CORE PRODUCTION CODE

> This document is derived from deep analysis of the actual Addverb fleet_core
> codebase (~200K LOC C++). Every parameter, protocol, and architectural decision
> below comes from their production code — not from generic robotics defaults.

---

You are a senior robotics engineer helping me build a production-grade warehouse robotics intelligence engine. No shortcuts. No simplifications. Exact stack — matched to Addverb's actual production system. I know every language — use whatever is correct for the job.

---

## WHO I AM

- Mac M3 Ultra, 96GB RAM
- Full stack — C++, Python, any language needed
- io-gita cold start already built and proven (<1ms zone identification, 100% accuracy, Hopfield ODE engine)
- Building toward a complete warehouse intelligence platform
- Target: Addverb Technologies research team
- I have their exact production fleet_core code and full architectural documentation

---

## WHAT I AM BUILDING

A unified simulation engine that replicates Addverb's exact production fleet behavior — their FMS (MoveCT), their robot types (Zippy, AMR, Forklift), their navigation (A* + MPC + OSQP), their localization (barcode grid), their communication protocol (TCP + RabbitMQ), their behavior trees (BTCPP v4) — running in a physics-accurate virtual warehouse.

Semantic Gravity sits on top as the predictive intelligence layer that Addverb doesn't have today. io-gita provides resilient zone identification when barcode localization degrades.

The goal: when this simulation runs, behavior is indistinguishable from their physical deployment. Sim-to-real gap is minimal by design.

---

## REAL ROBOT CODE INTEGRATION

I have the exact production robot code (open source / publicly available). Use this as the base — do not simulate generic robots. Simulate EXACT Addverb AMR behavior.

### What this means:
- Use their exact motion parameters — not generic defaults
- Use their exact communication protocol — TCP port 65123, not ROS2 topics
- Use their exact behavior trees — BTCPP v4, not Nav2 recovery behaviors
- Use their exact pathfinding — A* with custom heuristics, not Smac/TEB
- Use their exact controller — Linear MPC + OSQP, not DWB/TEB controllers
- Use their exact localization — barcode grid (0.8m resolution), not AMCL
- Use their exact sensor specs — obstacle sensor (+-15deg, 1.5m), not SICK nanoScan3
- Use their exact task lifecycle — WCS -> RabbitMQ -> FIFO Allocator -> TCP dispatch
- Match their exact 15 Hz main loop timing (67ms budget)

### How to proceed:
1. First — read ALL fleet_core code files completely
2. Extract every parameter value from their ActionCodes.yaml, config.xml, robot_params_new.yaml
3. Build simulation that EXACTLY mirrors their stack
4. Every parameter value comes from their code — not from defaults, not from guesswork
5. If anything is missing from their code, flag it explicitly — do not fill gaps silently

### Goal:
When this simulation runs, behavior must be indistinguishable from their physical robot fleet.
Sim-to-real gap must be minimal by design.

---

## FULL STACK

| Layer | Technology | Language | Source |
|---|---|---|---|
| Container | Docker Desktop ARM (Mac M3) | — | New |
| OS inside container | Ubuntu 22.04 | — | New |
| Physics simulation | Gazebo Fortress | C++ | New (visual layer only) |
| Visualization | Gazebo GUI + Grafana dashboard | — | New |
| Fleet management (FMS) | Addverb MoveCT replica | Python | Mirrors fleet_core/src/fleet/ |
| Robot control | Per-robot behavior engine | C++ + Python | Mirrors fleet_core/src/robot/ |
| Task management | TaskManager + FIFO allocator | Python | Mirrors fleet_core/src/task/ |
| Navigation | A* pathfinding + Linear MPC | C++ | Mirrors fleet_core/src/graph/ |
| Localization | Barcode grid (0.8m resolution) | C++ + Python | Mirrors fleet_core barcode driver |
| Behavior trees | BTCPP v4 (charge, move, load, unload) | C++ | Mirrors fleet_core_assets/models/behavior/ |
| Communication | TCP (65123) + RabbitMQ (5672) + REST (7012) | C++ + Python | Mirrors fleet_core/src/network/ |
| Database | MongoDB (27017) | — | Mirrors fleet_core/src/database/ |
| Scene/Map | Graph-based node map | C++ + Python | Mirrors fleet_core/src/scene/ |
| Deadlock prevention | ILP-based Coupled Node Reservation | C++ | Mirrors fleet_core/src/graph/ |
| Zone identification | io-gita node (barcode fallback) | C++ | NEW — augments barcode localization |
| Prediction engine | Semantic Gravity core | Python | NEW — Addverb doesn't have this |
| Warehouse execution (WES) | Order flow engine | Python | New, interfaces via RabbitMQ |
| Warehouse control (WCS) | Conveyor + sorter simulation | C++ + Python | Mirrors fleet_core WCS interface |
| Data storage | MongoDB + InfluxDB (time-series) | — | MongoDB from fleet_core, InfluxDB new |
| CI/CD | Basic pipeline | Shell + Python | New |

---

## ADDVERB ROBOT TYPES TO SIMULATE

### Priority 1: Zippy10 (Most Deployed)

| Parameter | Value | Source File |
|---|---|---|
| Type | Unidirectional (cannot turn freely) | ActionCodes.yaml |
| Max linear velocity | 1.4 m/s | ActionCodes.yaml |
| Max linear velocity (curve) | 0.6 m/s | ActionCodes.yaml |
| Max angular velocity | 1.57 rad/s (90deg/s) | ActionCodes.yaml |
| Linear acceleration | 0.8 m/s^2 | ActionCodes.yaml |
| Linear deceleration | 0.8 m/s^2 | ActionCodes.yaml |
| Jerk max | 10.0 m/s^3 | ActionCodes.yaml |
| Position tolerance | 0.07 m | ActionCodes.yaml |
| Angular tolerance | 0.025 rad | ActionCodes.yaml |
| Creep distance | 0.02 m | ActionCodes.yaml |
| Creep velocity | 0.02 m/s | ActionCodes.yaml |
| Exit velocity | 0.4 m/s | ActionCodes.yaml |
| Attachment | Single conveyor (bidirectional) | ActionCodes.yaml |
| Charge duration | 450 s (7.5 min) | ActionCodes.yaml |
| Discharge duration | 60,000 s (16.7 hours) | ActionCodes.yaml |
| Motion energy factor | 1.02x | ActionCodes.yaml |
| Attachment energy factor | 1.02x | ActionCodes.yaml |
| Obstacle sensor FOV | +-15deg (+-pi/12 rad) | ActionCodes.yaml |
| Obstacle sensor range | 1.5 m max | ActionCodes.yaml |
| Planning range | 0.88 m | ActionCodes.yaml |
| Warning threshold | 0.8 m | ActionCodes.yaml |
| Critical threshold | 0.7 m | ActionCodes.yaml |
| Path follower | SINGLE (straight) or LINEAR_MPC | ActionCodes.yaml |
| Motion model | DIFFERENTIAL with plant model | ActionCodes.yaml |
| Localization | Barcode reader (irayple, 5ms debounce) | robot_params_new.yaml |

### Priority 2: AMR500 (Differential Drive Heavy Load)

| Parameter | Value | Source File |
|---|---|---|
| Type | Differential drive (free rotation) | ActionCodes.yaml |
| Max linear velocity | 2.0 m/s | robot_params_new.yaml |
| Min linear velocity | 0.02 m/s | robot_params_new.yaml |
| Max angular velocity | 2.5 rad/s | robot_params_new.yaml |
| Min angular velocity | 0.02 rad/s | robot_params_new.yaml |
| Linear acceleration | 0.8 m/s^2 | robot_params_new.yaml |
| Position tolerance | 0.07 m | robot_params_new.yaml |
| Angular tolerance | 0.025 rad | robot_params_new.yaml |
| Payload capacity | 500 kg | Agent manifest |
| Localization | Barcode grid (0.8m resolution) | robot_params_new.yaml |
| Communication | FASTDDS | robot_params_new.yaml |

### Future: Additional Robot Types

| Robot | Type | Key Difference |
|---|---|---|
| Zippy6 | Unidirectional, compact | Smallest sorter |
| Zippy25 | Unidirectional, conveyor | Multi-purpose |
| Zippy40 | Unidirectional, conveyor | Heavy-duty sorter |
| ZippyTug | Unidirectional, tug | Pulls carts/pallets |
| ZippyX | Omnidirectional, conveyor | Can move sideways |
| AMR100-2500 | Differential drive | 100kg to 2500kg payload range |
| Veloce1x7 | High-speed GTP | Good-to-Person picking |
| Forklift | Scissor lift | 0-1.4M encoder height range |
| FWayShuttle | Fixed waypoint | Shuttle for high-density storage |

---

## SIMULATION REQUIREMENTS

### 1. Physically Accurate Warehouse World (Gazebo)

- Correct dimensions matching Addverb deployment sites
- Barcode grid on floor — 0.8m x 0.8m resolution (their exact grid)
- Shelf physics — collision geometry for obstacle detection
- Floor friction coefficients for wheel slip modeling
- Conveyor belt physics — accurate belt movement for Zippy handoff
- Dynamic obstacles — human agents, forklifts
- Emergency stop zones — fleet-wide e-stop within 100ms (their spec)
- Safety speed zones — obstacle sensor triggers at 0.7m critical / 0.8m warning

### 2. Robot Models (Matched to Addverb Specs)

#### Zippy10 Model:
- Unidirectional chassis — cannot rotate in place
- Single conveyor attachment (bidirectional, 0.2m offset, 0.35m height)
- Obstacle sensor: forward-facing, +-15deg FOV, 1.5m range
- Barcode reader: bottom-mounted, irayple, 5ms debounce, port 5689
- Battery: 450s charge / 60,000s discharge cycle
- Motor controller: Linear MPC + OSQP (12 opt vars, dt=0.1s, 500 iterations)

#### AMR500 Model:
- Differential drive — full rotation capability
- No conveyor attachment (platform-based payload)
- Obstacle sensor: forward-facing, same spec as Zippy10
- Barcode reader: same as Zippy10
- Battery: configurable per deployment
- Motor controller: Differential model with plant

### 3. Multi-Robot Fleet — 10 Robots (Mixed Fleet)

- 6x Zippy10 + 4x AMR500 (realistic mixed fleet)
- Each robot connects to FMS via TCP (port 65123) — their exact protocol
- Protocol V1 message format (33 fields: pose, state, battery, velocity, error)
- 15 Hz telemetry updates (67ms per cycle) — their exact timing
- ILP-based Coupled Node Reservation for deadlock prevention:
  - Reserve 4 nodes ahead of current position
  - 12+ constraint types (mutual exclusion, narrow aisles, bidirectional paths, zone capacity)
- FIFO task allocation (their default strategy)
- COPP Controller (Cooperative Path Planning) for multi-agent coordination
- Dynamic task reassignment — robot fails -> task redistributed
- Charging cycle: CHARGE_DOCK (cmd 2) -> START_CHARGING (cmd 3) -> CHARGE_UNDOCK (cmd 4)
- Communication outage simulation — test behavior under TCP disconnect
- Sensor failure simulation — barcode reader failure per robot

### 4. Navigation Stack (Addverb Custom, NOT Nav2)

**Pathfinding:**
- A* algorithm with configurable heuristics (Manhattan/Euclidean/Chebyshev)
- Turn cost penalties — penalize unnecessary rotation
- Storage area filtering — exclude certain zones during planning
- Graph-based map — nodes and edges, not costmaps

**Motion Control:**
- Linear MPC (Model Predictive Control) for straight-line segments
- OSQP quadratic solver:
  - `num_opt_vars: 12`
  - `dt: 0.1 s`
  - `position_weight: 1.0`
  - `velocity_weight: 0.0`
  - `weight_scale: 0.05`
  - `jerk_scale: 1.0`
  - `acceleration_scale: 1.0`
  - `final_position_offset: 0.015 m`
  - `final_velocity_threshold: 0.05 m/s`
  - `osqp_iterations: 500`
  - `osqp_eps_abs_threshold: 0.01`
  - `osqp_eps_rel_threshold: 0.01`

**Obstacle Handling:**
- Single sensor, forward-facing
- Detection range: 1.5m (planning), 0.88m (replan), 0.8m (warning), 0.7m (critical/stop)
- No costmaps — binary detect/stop/wait/replan

**Recovery Behaviors (from Behavior Trees):**
- Wait for obstacle to clear
- Request FMS for replanning
- Fallback to nearest safe node

### 5. Localization: Barcode Grid (Primary) + io-gita (Augmentation)

**Primary — Addverb's Actual System:**
- Barcode markers on floor at 0.8m grid intervals
- irayple barcode reader (bottom-mounted, debounce 5ms, failure threshold 5 reads)
- Robot reads barcode -> looks up grid coordinate -> exact position known
- No AMCL, no particles, no laser-based localization

**io-gita Augmentation Layer (NEW — Addverb doesn't have this):**
- Activates when barcode localization degrades:
  - Barcode damaged/missing on floor
  - Reader malfunction (exceeds failure threshold)
  - Robot driven off-grid (manual move, collision)
- Zone identification from obstacle sensor data + odometry
- Hopfield ODE classification — <1ms zone identification
- Graph topology for zone disambiguation
- Provides zone-level position hint until next valid barcode read
- Fleet-wide shared atlas — one robot discovers zone state, all robots benefit
- Map change detection — flags when environment doesn't match expected layout

**io-gita topics per robot:**
- /robot_N/iogita/zone — current zone classification
- /robot_N/iogita/zone_confidence — classification confidence
- /robot_N/iogita/barcode_fallback — true when barcode system degraded
- /robot_N/iogita/map_change — environment mismatch alert

**Demo value:** "Your robots are blind when a barcode is damaged. io-gita gives them spatial awareness without changing hardware."

### 6. FMS Layer — Fleet Management System (Python, Mirrors MoveCT)

Exact replica of Addverb's fleet_core/src/fleet/ architecture:

- **COPP Controller** — Cooperative Path Planning, coordinates all robot paths
- **FIFO Task Allocator** — first available robot gets next queued task (their default)
- Task lifecycle: NOT_ASSIGNED -> ACCEPTED -> ASSIGNED -> IN_PROGRESS -> COMPLETED
- 9-check task validation before assignment (from their TaskManager)
- Fleet health monitoring — per-robot status via 15 Hz telemetry
- Dynamic task reassignment — robot disconnects -> task status reverts -> reassigned
- REST API — 200+ endpoints mirroring their actual REST interface on port 7012
- MongoDB persistence — tasks, events, statistics, agent state (matching their collections)

**Communication matches their exact protocol:**
- Robot discovery via RabbitMQ exchange `FMS.ROBOT.DISCOVERY`
- Robot updates via exchange `FMS.ROBOT.UPDATE`
- Robot feedback via queue `FMS.ROBOT.FEEDBACK`
- Keep-alive: 10 seconds, timeout: 30 seconds
- TCP port 65123 for direct robot commands

### 7. WES Layer — Warehouse Execution System (Python)

- Order queue simulation — Poisson arrival process
- Task generation: order -> pick tasks + place tasks + conveyor handoff
- Interfaces with FMS via RabbitMQ (their actual integration point)
- Task message format: `{pickup: location, dropoff: location, priority: HIGH/MED/LOW}`
- TTL: 60 seconds per message, 5 retry attempts, 30s heartbeat (their config)
- Priority management — SLA-based urgency
- Surge handling — sudden 50-order injection test
- KPI tracking — orders/hour, pick accuracy, throughput

### 8. WCS Layer — Warehouse Control System (C++ + Python)

- Conveyor simulation in Gazebo — physics-accurate belt movement
- Sorter logic — divert decisions based on destination zone
- Robot-conveyor handoff zones — Zippy10 conveyor attachment coordinates load/unload
- Handoff actions: START_LOADING (cmd 14), START_UNLOADING (cmd 15)
- OPC UA gateway simulation (their opcGateway module):
  - OPC tags: FMS.LANE_HEALTHY, CONV.LANE_HEALTHY
  - Lane health monitoring
  - Port 65023 (their config)
- Conveyor failure simulation — belt stops, WCS reroutes to alternate lane

### 9. Behavior Trees (BTCPP v4 — From Their Actual XML)

Each robot runs a behavior tree matching Addverb's 18 XML behavior files:

**Core Actions (from ActionCodes.yaml):**

| Command | Code | Description |
|---|---|---|
| MOVE | 0 | Navigate to target node |
| CHARGE_DOCK | 2 | Approach charging station |
| START_CHARGING | 3 | Activate charger |
| CHARGE_UNDOCK | 4 | Detach and resume |
| START_LOADING | 14 | Conveyor: accept parcel |
| START_UNLOADING | 15 | Conveyor: deliver parcel |
| RESET_ERRORS | 31 | Clear non-charging errors |
| HARD_RESET | 51 | Clear charging errors |

**Response Codes:**

| Response | Code | Meaning |
|---|---|---|
| REACHED_DOCK | 10 | At charging station |
| REACHED_PREDOCK | 8 | Approaching dock |
| CHARGING_STOPPED | 18 | Charge complete |
| CHARGING_ERROR | 501 | Charge failure |

### 10. Semantic Gravity Prediction Layer (Python — NEW)

This is Addverb's missing piece — the intelligence layer:

- Warehouse state encoded as high-dimensional vector every second
- State vector components:
  - Per-robot: position, velocity, battery, task status, current zone
  - Per-zone: congestion level, robot count, throughput
  - Fleet-wide: active tasks, pending orders, charging queue depth
- Zones as atoms, robot states as patterns, fleet state as query
- Attractor landscape of warehouse operational states
- Bottleneck prediction — flags congestion 2-5 minutes before it happens
- Deadlock prevention — identifies basin traps before robots enter them
- Couples with COPP Controller — SG suggestions feed directly into path planning
- Energy optimization — suggests charging schedule to minimize fleet downtime
- Learning component — attractor landscape adapts from observed traffic patterns
- A/B comparison — run same scenario with and without SG, show the difference

---

## SENSOR SUITE (MATCHED TO ADDVERB)

| Sensor | Actual Spec | Purpose | Source |
|---|---|---|---|
| Obstacle sensor | +-15deg FOV, 1.5m range, forward-facing | Safety stop + replanning trigger | ActionCodes.yaml |
| Barcode reader | irayple, bottom-mount, 5ms debounce | Primary localization (0.8m grid) | robot_params_new.yaml |
| Battery monitor | Voltage + current, charge/discharge curves | State of charge, charging decisions | ActionCodes.yaml |
| Wheel encoders | Integrated (odometry between barcodes) | Dead reckoning between grid points | robot_params_new.yaml |
| Conveyor sensors | Load/unload detection | Parcel handoff confirmation | ActionCodes.yaml |

**NOTE:** Addverb robots do NOT have 270deg LiDAR, depth cameras, IMU, RFID, or acoustic sensors in their standard configuration. The obstacle sensor is a minimal safety sensor, not a navigation LiDAR. Do not simulate sensors they don't have.

---

## FAILURE MODES TO SIMULATE (MATCHED TO THEIR ARCHITECTURE)

| Failure | How to simulate | Expected behavior | Addverb current | With io-gita + SG |
|---|---|---|---|---|
| Robot restart mid-task | Kill TCP connection, respawn | Robot reconnects, FMS reassigns task | Reconnect + re-localize on barcode | io-gita provides instant zone hint before barcode read |
| Barcode reader failure | Stop barcode data | Robot stops (no localization) | Manual intervention required | io-gita maintains zone-level awareness, robot continues cautiously |
| Damaged floor barcodes | Remove barcodes from grid section | Robot cannot localize in that area | Manual intervention required | io-gita bridges the gap, robot navigates through |
| Communication outage | Drop TCP to FMS | Robot stops and waits | Timeout after 30s, e-stop | SG predicted the outage zone, rerouted fleet preemptively |
| Obstacle sensor failure | Publish no data | Robot enters safe stop | Safety stop, manual clear | Same — safety-critical, no override |
| Conveyor failure | Stop belt physics | WCS reroutes to alternate lane | Manual WCS intervention | SG flags lane degradation trend before failure |
| Robot physically moved | Teleport in sim | Barcode mismatch on next read | Re-localize on nearest barcode | io-gita detects zone mismatch instantly |
| Forklift blocking path | Dynamic obstacle in graph node | A* replanning triggered | Wait + FMS replan | SG predicted congestion, preemptive reroute |
| 2 robots simultaneous failure | Kill 2 TCP connections | FMS reassigns both tasks | FIFO reassignment | SG adjusts attractor landscape, prevents cascade |
| Network packet loss 30% | TCP latency injection | Degraded telemetry frequency | Graceful degradation | SG compensates with predicted positions |
| ILP solver timeout | Overload node reservation | Potential deadlock | Wait + manual resolve | SG prevents overload by pre-distributing traffic |
| Battery critical during task | Accelerate discharge curve | Robot abandons task, seeks charger | Reactive charging | SG predicts battery critical 10min ahead, pre-schedules |

---

## COMMUNICATION PROTOCOL (EXACT ADDVERB MATCH)

### Robot <-> FMS (TCP Port 65123)

**Protocol V1 — 33 field message:**
```
[Timestamp | RobotID | Pose(x,y,theta) | State | BatterySOC | LinearVel | AngularVel | ErrorCode | TaskID | CurrentNode | ...]
```

**Update frequency:** 15 Hz (robot -> FMS telemetry)
**Command frequency:** On-demand (FMS -> robot path/action commands)
**Keep-alive:** Every 10 seconds
**Timeout:** 30 seconds (robot marked disconnected)

### WCS <-> FMS (RabbitMQ Port 5672)

**Exchanges:**
- `FMS.ROBOT.DISCOVERY` — robot announces itself
- `FMS.ROBOT.UPDATE` — telemetry stream
- `FMS.ROBOT.FEEDBACK` — task completion/failure

**Queue settings:**
- TTL: 60 seconds per message
- Retry: 5 attempts
- Heartbeat: 30 seconds

### REST API (Port 7012)

200+ endpoints matching their actual interface:
- `/api/robots/*` — Robot CRUD, status, tracking (25+ endpoints)
- `/api/tasks/*` — Task create, assign, cancel, query (30+ endpoints)
- `/api/maps/*` — Map load, locations, zones (20+ endpoints)
- `/api/stats/*` — Throughput, performance, analytics (15+ endpoints)
- `/api/config/*` — Runtime settings (20+ endpoints)
- `/api/admin/*` — System control, health checks (15+ endpoints)

### External Systems

| System | Port | Protocol | Purpose |
|---|---|---|---|
| FMS TCP | 65123 | TCP | Robot direct communication |
| RabbitMQ | 5672 | AMQP | WCS/WMS task queue |
| REST API | 7012 | HTTP | UI & external APIs |
| MongoDB | 27017 | MongoDB Wire | Persistence |
| gRPC | 50051 | gRPC | Python integration |
| OPC Gateway | 65023 | OPC UA | Conveyor/shuttle integration |

---

## DATA MANAGEMENT

### MongoDB Collections (Matching fleet_core)

| Collection | Purpose | TTL | Update Frequency |
|---|---|---|---|
| tasks | Task records | 30 days | Per task event |
| events | System events | 7 days | Continuous |
| statistics | Performance metrics | 90 days | Async batch |
| agents | Robot state snapshots | 1 day | 15 Hz (main loop) |
| paths | Path history | 7 days | Per path generation |

### InfluxDB (New — Time-Series for SG + Grafana)

- Fleet throughput (orders/hour)
- Per-robot battery curves
- Barcode read success rate (per robot, per zone)
- io-gita zone accuracy vs barcode ground truth
- SG prediction accuracy vs actual outcomes
- Bottleneck heatmap data
- Deadlock frequency and resolution time
- Node reservation solve time (ILP performance)

### Grafana Dashboard

Live visualization of:
- Fleet overview — all robots on map, color-coded by state
- Task queue depth and assignment rate
- Per-robot battery levels and predicted charge times
- Barcode read success rate (highlights damaged floor areas)
- io-gita fallback activations (when/where barcode fails)
- SG prediction accuracy — predicted vs actual congestion
- A/B panel — with SG vs without SG, side by side

---

## SECURITY & NETWORK (MATCHED TO THEIR CONFIG)

- Network latency simulation — 10ms, 50ms, 200ms scenarios
- Packet loss simulation — 5%, 15%, 30% on TCP connections
- TCP connection limits — 5000 concurrent (their config)
- Robot-to-FMS keep-alive — 10s interval, 30s timeout
- Fleet-wide e-stop signal — all robots halt within 100ms
- RabbitMQ auto-reconnection testing (known issue HIGH-003 in their debt tracker)

---

## FMS MAIN LOOP BUDGET (15 Hz = 67ms)

Matching their actual execution timing:

```
1. Receive robot telemetry        (2-3ms)
2. Update agent states            (3-5ms)
3. Allocate pending tasks         (2-5ms)
4. Generate/update paths (A*)     (2-5ms)
5. Node reservation ILP           (5-15ms) — MOST EXPENSIVE
6. Send commands to robots        (1-2ms)
7. Database flush                 (Async — non-blocking)
8. Event system dispatch          (1-3ms)
9. SG prediction query            (NEW — budget TBD, must fit in remaining ~30ms)
─────────────────────────────────
TOTAL CRITICAL PATH: 15-38ms (22-57% of 67ms budget)
SG MUST NOT EXCEED: ~25ms per cycle to stay within budget
```

---

## AUTOMATED TESTING

- Unit tests — C++ simulation components (gtest)
- Unit tests — Python FMS/WES/SG logic (pytest)
- Integration tests — full task lifecycle: order -> WES -> FMS -> robot -> conveyor -> complete
- Protocol tests — verify TCP message format matches fleet_core V1 spec exactly
- Stress test — 10 robots, 100 orders, simulated 8-hour shift
- SG accuracy test — compare predicted bottlenecks vs actual outcomes
- io-gita accuracy test — compare zone identification vs barcode ground truth
- Regression tests — run after every commit
- CI pipeline — build + test on every push

---

## FOLDER STRUCTURE

```
warehouse_engine/
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml            # FMS + MongoDB + RabbitMQ + InfluxDB + Grafana
├── src/
│   ├── warehouse_sim/                 # Gazebo world + robot models (physics only)
│   │   ├── worlds/
│   │   │   └── addverb_warehouse.sdf  # Warehouse with barcode grid floor
│   │   ├── models/
│   │   │   ├── zippy10/               # Zippy10 model (exact dimensions)
│   │   │   ├── amr500/                # AMR500 model (exact dimensions)
│   │   │   ├── conveyor/              # Conveyor belt model
│   │   │   └── charging_station/      # Docking station model
│   │   └── plugins/                   # Gazebo C++ plugins
│   │       ├── barcode_sensor.cpp     # Simulates irayple barcode reader
│   │       ├── obstacle_sensor.cpp    # +-15deg, 1.5m range
│   │       └── conveyor_belt.cpp      # Belt physics
│   │
│   ├── fleet_manager/                 # Python — FMS (mirrors fleet_core/src/fleet/)
│   │   ├── copp_controller.py         # Cooperative Path Planning
│   │   ├── fifo_allocator.py          # Task allocation (their default)
│   │   ├── fleet_manager.py           # Main orchestration loop (15 Hz)
│   │   ├── rest_api.py                # 200+ endpoints on port 7012
│   │   ├── tcp_server.py              # Robot comms on port 65123
│   │   └── config/
│   │       └── config.xml             # Mirrors their config.xml structure
│   │
│   ├── robot_sim/                     # Per-robot simulation (mirrors fleet_core/src/robot/)
│   │   ├── robot.py                   # Robot state machine
│   │   ├── behavior_tree.py           # BTCPP v4 execution engine
│   │   ├── motion_controller.py       # Linear MPC + OSQP
│   │   ├── barcode_localizer.py       # Grid-based localization
│   │   ├── battery.py                 # Charge/discharge model
│   │   ├── protocol_v1.py             # 33-field TCP message format
│   │   └── config/
│   │       ├── zippy10_params.yaml    # Exact Zippy10 ActionCodes
│   │       └── amr500_params.yaml     # Exact AMR500 params
│   │
│   ├── navigation/                    # Pathfinding (mirrors fleet_core/src/graph/)
│   │   ├── astar.py                   # A* with configurable heuristics
│   │   ├── node_reservation.py        # ILP-based coupled reservation
│   │   ├── graph_map.py               # Node/edge warehouse map
│   │   └── quadtree.py                # Spatial indexing
│   │
│   ├── iogita_node/                   # C++ — zone identification (NEW)
│   │   ├── src/
│   │   │   ├── zone_classifier.cpp    # Hopfield ODE engine
│   │   │   ├── barcode_fallback.cpp   # Activates when barcode degrades
│   │   │   └── fleet_atlas.cpp        # Shared zone knowledge
│   │   ├── include/
│   │   └── config/
│   │
│   ├── sg_prediction/                 # Python — Semantic Gravity (NEW)
│   │   ├── sg_engine.py               # Attractor landscape
│   │   ├── state_encoder.py           # Warehouse state -> vector
│   │   ├── bottleneck_predictor.py    # 2-5 min advance warning
│   │   ├── deadlock_preventer.py      # Basin trap identification
│   │   └── fms_adapter.py             # SG -> FMS actionable suggestions
│   │
│   ├── warehouse_execution/           # Python — WES
│   │   ├── order_generator.py         # Poisson arrival simulation
│   │   ├── task_generator.py          # Order -> pick/place tasks
│   │   └── kpi_tracker.py             # Orders/hour, throughput
│   │
│   ├── warehouse_control/             # C++/Python — WCS
│   │   ├── conveyor_controller.py     # Belt control logic
│   │   ├── sorter_logic.py            # Divert decisions
│   │   └── opc_gateway.py             # OPC UA simulation (port 65023)
│   │
│   └── monitoring/                    # Grafana + InfluxDB
│       ├── influx_writer.py           # Time-series metrics
│       └── dashboards/
│           └── grafana_warehouse.json
│
├── behavior_trees/                    # BTCPP v4 XML (from fleet_core_assets)
│   ├── zippy10_default.xml
│   ├── zippy10_move.xml
│   ├── amr500_default.xml
│   └── amr500_move.xml
│
├── maps/
│   ├── warehouse_graph.json           # Node/edge graph (not PGM occupancy grid)
│   └── barcode_grid.json              # Barcode positions (0.8m intervals)
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── protocol/                      # TCP V1 message format compliance
│   └── stress/
│
├── bags/                              # Simulation run recordings
├── logs/
├── reference/                         # Addverb fleet_core docs for cross-reference
│   └── fleet_core_assets/             # Their ActionCodes, behavior trees, configs
└── README.md
```

---

## DEBUG AND OBSERVABILITY

Every component must have:
- Structured logging — timestamped, JSON format, one file per component per run
- Performance timer — log execution time for critical functions (especially ILP solver, A*, SG)
- Connection health monitor — alert if any TCP connection or RabbitMQ queue goes silent
- Main loop timing — log per-cycle execution time, flag when exceeding 67ms budget
- MongoDB event logging — matching their event collection schema

---

## VERIFICATION AT EACH STEP

After every component built:
- Exact command to verify it works
- Expected output defined
- Performance benchmark (timing, CPU, memory)
- Cross-reference with fleet_core behavior — "does our simulation match their code?"
- Git commit with descriptive message

---

## DEMO SCENARIO — 10 MINUTES

```
Scene opens — Gazebo top-down warehouse view
Barcode grid visible on floor. 10 robots moving. Orders flowing. Conveyors running.
Grafana dashboard on second screen showing live metrics.

--- Act 1: "This Is Your Exact System" (2 min) ---

Show fleet operating normally:
- 6 Zippy10 bots running sorter routes (unidirectional)
- 4 AMR500 bots running heavy-load delivery routes
- TCP messages flowing at 15 Hz
- Task lifecycle: WCS order -> RabbitMQ -> FIFO assign -> robot executes -> conveyor handoff
- "Every parameter here comes from YOUR ActionCodes.yaml. This IS MoveCT."

--- Act 2: "Your Blind Spot — Barcode Failure" (2 min) ---

Scenario 1: Damage 3 barcodes on floor in aisle_4
- Addverb baseline: Zippy10_3 enters damaged zone -> barcode read fails ->
  robot stops dead -> manual intervention needed -> 3 min downtime
- With io-gita: Zippy10_3 enters damaged zone -> barcode fails ->
  io-gita activates -> zone-level awareness maintained ->
  robot continues to next valid barcode -> 0 downtime
- "Your robots are blind when a barcode is damaged.
   io-gita gives them spatial awareness without changing hardware."

--- Act 3: "Predicting Before It Happens" (3 min) ---

Scenario 2: Inject 50 orders simultaneously (surge)
- WITHOUT Semantic Gravity:
  FIFO allocator floods aisle_4 -> 4 robots converge ->
  ILP solver overloaded -> deadlock -> throughput drops 40%
- WITH Semantic Gravity:
  SG detects converging attractor 3 minutes before jam ->
  suggests load redistribution to FMS ->
  FMS reroutes 2 robots preemptively -> no jam -> throughput stable
- Side-by-side Grafana: throughput with SG vs without SG

Scenario 3: 2 robots fail simultaneously
- Kill Zippy10_3 and AMR500_2 TCP connections
- FMS detects timeout (30s) -> reverts tasks -> FIFO reassignment
- WITH SG: predicted capacity drop, pre-adjusted task queue
- Fleet continues at 80% throughput

--- Act 4: "The Intelligence Layer" (2 min) ---

Scenario 4: SG adapts to traffic patterns
- Show attractor landscape visualization
- Run same fleet for 30 simulated minutes
- SG learns: "aisle_4 is always congested at 14:00 during shift change"
- Next cycle: SG preemptively reroutes before 14:00
- "This learns YOUR warehouse. Not generic patterns. YOUR patterns."

--- Final Screen (1 min) ---

Split screen:
Left: "Addverb Today" — reactive, barcode-dependent, no prediction
Right: "Addverb + io-gita + SG" — resilient localization, predictive routing

"This is what your customer's factory looks like
before you deploy a single robot.
And this is what it looks like with intelligence."
```

---

## KNOWN ADDVERB TECHNICAL DEBT (From Their Code)

These are real issues in fleet_core we can demonstrate solutions for:

| ID | Issue | Severity | Our Solution |
|---|---|---|---|
| CRITICAL-003 | Node Reservation deadlock risk | Critical | SG predicts deadlock-prone states, prevents entry |
| HIGH-001 | Unbounded TaskPool memory growth | High | Time-bounded task retention in our FMS replica |
| HIGH-003 | No RabbitMQ auto-reconnection | High | Resilient message queue with retry in our WES |
| HIGH-004 | Disconnected agents not auto-removed | High | Timeout + SG-aware fleet rebalancing |
| MED-002 | Path planning CPU intensive | Medium | SG pre-computes preferred routes, reduces A* calls |
| — | No predictive intelligence | — | Semantic Gravity (our primary differentiator) |
| — | Barcode-only localization | — | io-gita augmentation (our secondary differentiator) |

---

## START

Check all prerequisites on Mac M3:
Docker Desktop ARM, XQuartz, git, Python 3.11+, C++ compiler.

Then begin Step 1:
Docker container with Ubuntu 22.04 + Gazebo Fortress + MongoDB + RabbitMQ + InfluxDB + Grafana
running and verified on Apple Silicon.

No ROS2. No Nav2. No AMCL. We build on their actual stack.

# Configuration Guide

The simulation is configured through three types of files plus environment variables. No code changes are needed to customize the simulation for your warehouse and robots.

## Overview

```
configs/
  warehouses/           # Warehouse navigation graphs (JSON)
    simple_grid.json    # 25 nodes, 3 zones (demo)
    botvalley.json      # 63 nodes (production)
  robots/               # Robot physical parameters (YAML)
    differential_drive.yaml   # AMR preset
    unidirectional.yaml       # AGV preset
  behavior_trees/       # Decision logic (XML, BTCPP v4)
    default_agv.xml     # AGV lifecycle
    default_amr.xml     # AMR lifecycle with obstacle avoidance
```

---

## Custom Warehouse JSON

A warehouse map defines the navigation graph that robots traverse.

### Structure

```json
{
  "name": "My Warehouse",
  "description": "Description of the layout",
  "grid_spacing_m": 2.0,
  "nodes": [...],
  "edges": [...],
  "zones": [...]
}
```

### Nodes

Each node has a unique name, position, and type.

```json
{
  "name": "A_01",
  "x": 2.0,
  "y": 4.0,
  "type": "aisle"
}
```

| Node Type | Purpose |
|-----------|---------|
| `aisle` | Traversal corridor |
| `shelf` | Storage location |
| `charge` | Charging dock |
| `pick` | Order pickup station |
| `drop` | Order dropoff station |
| `hub` | Central intersection |

### Edges

Edges define which nodes are connected. All edges are bidirectional by default.

```json
{"from": "A_01", "to": "A_02"}
```

For unidirectional edges (one-way aisles):

```json
{"from": "A_01", "to": "A_02", "bidirectional": false}
```

### Zones

Zones group nodes into logical areas for io-gita intelligence.

```json
{
  "name": "Storage",
  "type": "shelf",
  "nodes": ["S_01", "S_02", "S_03"]
}
```

| Zone Type | Purpose |
|-----------|---------|
| `dock` | Charging area |
| `shelf` | Storage area |
| `ops` | Operations (pick/drop) |
| `aisle` | Transit corridors |

### Creating a Custom Warehouse

1. Copy the closest preset:
   ```bash
   cp configs/warehouses/simple_grid.json configs/warehouses/my_warehouse.json
   ```

2. Edit the file. Key rules:
   - Every node name must be unique
   - Every edge must reference existing node names
   - Every zone must reference existing node names
   - Coordinates are in meters from origin (0, 0)
   - At least one `charge` node is required for battery management
   - At least one `pick` and one `drop` node for task execution

3. Set the environment variable:
   ```bash
   WAREHOUSE_CONFIG=my_warehouse docker compose up
   ```

### Example: Simple L-Shaped Warehouse

```json
{
  "name": "L-Shape Demo",
  "description": "8 nodes in an L pattern",
  "grid_spacing_m": 3.0,
  "nodes": [
    {"name": "DOCK", "x": 0, "y": 0, "type": "charge"},
    {"name": "A1",   "x": 3, "y": 0, "type": "aisle"},
    {"name": "A2",   "x": 6, "y": 0, "type": "aisle"},
    {"name": "PICK", "x": 9, "y": 0, "type": "pick"},
    {"name": "A3",   "x": 0, "y": 3, "type": "aisle"},
    {"name": "S1",   "x": 0, "y": 6, "type": "shelf"},
    {"name": "S2",   "x": 0, "y": 9, "type": "shelf"},
    {"name": "DROP", "x": 0, "y": 12, "type": "drop"}
  ],
  "edges": [
    {"from": "DOCK", "to": "A1"}, {"from": "A1", "to": "A2"},
    {"from": "A2", "to": "PICK"}, {"from": "DOCK", "to": "A3"},
    {"from": "A3", "to": "S1"}, {"from": "S1", "to": "S2"},
    {"from": "S2", "to": "DROP"}
  ],
  "zones": [
    {"name": "Charging", "type": "dock", "nodes": ["DOCK"]},
    {"name": "Storage", "type": "shelf", "nodes": ["S1", "S2"]},
    {"name": "Operations", "type": "ops", "nodes": ["PICK", "DROP"]}
  ]
}
```

---

## Custom Robot YAML

Robot presets define physical parameters read by both C++ and Python layers.

### Structure

```yaml
name: "MyRobot"
type: differential_drive    # differential_drive | unidirectional | omnidirectional

motion:
  max_linear_velocity: 2.0  # m/s
  min_linear_velocity: 0.02
  max_angular_velocity: 2.5 # rad/s
  min_angular_velocity: 0.02
  linear_acceleration: 0.8  # m/s^2
  linear_deceleration: 0.8
  jerk_max: 10.0            # m/s^3
  position_tolerance: 0.07  # m — "close enough"
  angular_tolerance: 0.025  # rad
  creep_distance: 0.02      # m — final approach
  creep_velocity: 0.02      # m/s
  exit_velocity: 0.4        # m/s — speed leaving a node

dimensions:
  length: 0.8               # m
  width: 0.6
  height: 0.3
  weight: 50.0              # kg empty
  payload_capacity: 500.0   # kg
  wheel_separation: 0.5     # m
  wheel_radius: 0.075       # m

sensors:
  lidar:
    enabled: true
    type: "2d"              # 2d | 3d
    fov_deg: 360            # Field of view in degrees
    range_m: 5.0            # Max detection range
    rays: 360
    height_m: 0.15
    noise_stddev_m: 0.03
  barcode_reader:
    enabled: true
    debounce_ms: 5
    failure_threshold: 5
  imu:
    enabled: true
    noise_stddev_deg: 3.0

battery:
  charge_duration_s: 600    # Seconds to full charge
  discharge_duration_s: 54000  # 15 hours of operation
  motion_energy_factor: 1.05
  attachment_energy_factor: 1.0
  critical_threshold_pct: 20
  initial_charge_pct: 100

obstacle_thresholds:
  critical_m: 0.7           # Emergency stop
  warning_m: 0.8            # Decelerate
  planning_m: 1.5           # Replan path

attachment:
  type: "none"              # none | conveyor | lifter | tug
  load_time_s: 3.0
  unload_time_s: 3.0

mpc:
  num_opt_vars: 12
  dt: 0.1
  position_weight: 1.0
  velocity_weight: 0.0
  weight_scale: 0.05
  jerk_scale: 1.0
  acceleration_scale: 1.0
  final_position_offset: 0.015
  final_velocity_threshold: 0.05
  osqp_iterations: 500
  osqp_eps_abs: 0.01
  osqp_eps_rel: 0.01

behavior_tree: "default_amr.xml"

action_codes:
  move: 0
  charge_dock: 2
  start_charging: 3
  charge_undock: 4
  start_loading: 14
  start_unloading: 15
  reset_errors: 31
  hard_reset: 51

response_codes:
  reached_dock: 10
  reached_predock: 8
  charging_stopped: 18
  charging_error: 501
  load_error: 401
  unload_error: 402
```

### Creating a Custom Robot

1. Copy the closest preset:
   ```bash
   cp configs/robots/differential_drive.yaml configs/robots/my_robot.yaml
   ```

2. Edit the file. Key sections to customize:
   - `motion` — Speed, acceleration, tolerances (match your robot's specs)
   - `dimensions` — Physical size (affects collision avoidance)
   - `sensors` — LiDAR FOV and range (360 for AMR, 30 for AGV)
   - `battery` — Charge/discharge times (measure from your real robot)
   - `obstacle_thresholds` — Safety distances
   - `action_codes` — Match your robot's firmware protocol

3. Set the environment variable:
   ```bash
   ROBOT_CONFIG=my_robot docker compose up
   ```

### Robot Types

| Type | Movement | LiDAR | Typical Use |
|------|----------|-------|-------------|
| `differential_drive` | Omnidirectional, rotates in place | 360 deg | AMR pallet movers |
| `unidirectional` | Forward only, turns at nodes | 30 deg | Sortation AGVs |
| `omnidirectional` | Any direction, no rotation needed | 360 deg | Mecanum wheel robots |

---

## Custom Behavior Trees

Behavior trees define the decision logic for robots using BTCPP v4 XML format.

### Structure

```xml
<?xml version="1.0" encoding="UTF-8"?>
<root BTCPP_format="4" main_tree_to_execute="MyTree">

  <BehaviorTree ID="MyTree">
    <Sequence>
      <!-- Actions and conditions here -->
    </Sequence>
  </BehaviorTree>

</root>
```

### Available Action Nodes

| Node | Purpose | Parameters |
|------|---------|-----------|
| `NavigateToNode` | Move to a map node | `target_node`, `action_code`, `velocity_profile` |
| `AlignAtStation` | Align with pick/drop station | `station_type`, `tolerance_m` |
| `ExecuteAttachment` | Load or unload cargo | `action_code`, `timeout_s` |
| `DockAtCharger` | Dock at charging station | `action_code`, `timeout_s` |
| `StartCharging` | Begin charging | `action_code` |
| `WaitUntilCharged` | Wait for battery level | `target_pct` |
| `UndockFromCharger` | Undock from charger | `action_code`, `timeout_s` |
| `SendActionCode` | Send raw action code | `action_code`, `description`, `timeout_s` |
| `ReportTaskComplete` | Mark task complete | `task_id` |
| `WaitSeconds` | Pause for N seconds | `seconds` |
| `AcceptTask` | Accept an assigned task | `task_id`, `pickup_node`, `drop_node` |
| `RotateToHeading` | Rotate in place (AMR only) | `target_heading`, `angular_velocity`, `tolerance_rad` |
| `EmergencyStop` | Immediate stop | (none) |
| `Decelerate` | Reduce speed | (none) |
| `RequestReplan` | Request path replanning | `target_node` |
| `LowerLifter` | Lower lifter attachment | `timeout_s` |
| `RaiseLifter` | Raise lifter attachment | `timeout_s` |

### Available Condition Nodes

| Node | Purpose | Parameters |
|------|---------|-----------|
| `TaskAvailable` | Check if a task is assigned | (none) |
| `BatteryAboveThreshold` | Check battery level | `threshold_pct` |
| `CargoSecured` | Check if cargo is loaded | (none) |
| `HasErrors` | Check for active errors | (none) |
| `NoErrors` | Check errors are cleared | (none) |
| `ObstacleInCriticalZone` | Check obstacle proximity | `distance_m` |
| `ObstacleInWarningZone` | Check obstacle warning zone | `distance_m` |
| `HasLifterAttachment` | Check if robot has lifter | (none) |

### Composites

| Node | Purpose |
|------|---------|
| `Sequence` | Execute children left-to-right, stop on first FAILURE |
| `Fallback` | Execute children left-to-right, stop on first SUCCESS |
| `ReactiveSequence` | Re-evaluate from first child on each tick |
| `RepeatNode` | Repeat children N times (`num_cycles=-1` for infinite) |
| `RetryNode` | Retry children N times on failure |
| `Inverter` | Invert child result (SUCCESS <-> FAILURE) |

### Creating a Custom Behavior Tree

1. Copy the closest preset:
   ```bash
   cp configs/behavior_trees/default_amr.xml configs/behavior_trees/my_bt.xml
   ```

2. Edit the XML.

3. Reference it in your robot YAML:
   ```yaml
   behavior_tree: "my_bt.xml"
   ```

---

## Environment Variables

All settings can be overridden via environment variables.

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGODB_URL` | `mongodb://localhost:27017` | MongoDB connection string |
| `MONGODB_DATABASE` | `fleet_twin` | Database name |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection string |
| `INFLUXDB_URL` | `http://localhost:8086` | InfluxDB URL |
| `INFLUXDB_TOKEN` | (empty) | InfluxDB auth token |
| `INFLUXDB_ORG` | `robotic_twin` | InfluxDB organization |
| `INFLUXDB_BUCKET` | `telemetry` | InfluxDB bucket |
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | RabbitMQ connection |
| `WAREHOUSE_CONFIG` | `simple_grid` | Warehouse config name (no extension) |
| `ROBOT_CONFIG` | `differential_drive` | Robot config name (no extension) |
| `API_HOST` | `0.0.0.0` | FastAPI bind address |
| `API_PORT` | `8029` | FastAPI port |
| `FMS_HOST` | `localhost` | C++ FMS server host |
| `FMS_PORT` | `7012` | C++ REST server port |
| `FMS_TCP_PORT` | `65123` | C++ TCP protocol port |
| `LOG_LEVEL` | `info` | Logging level |

### Using with Docker Compose

```bash
# Override via environment
WAREHOUSE_CONFIG=botvalley ROBOT_CONFIG=unidirectional docker compose up

# Or edit .env file
cp .env.example .env
# Edit .env, then:
docker compose up
```

### Using for Local Development

```bash
export WAREHOUSE_CONFIG=simple_grid
export ROBOT_CONFIG=differential_drive
export MONGODB_URL=mongodb://localhost:27017
cd python && uvicorn app.main:app --port 8029
```

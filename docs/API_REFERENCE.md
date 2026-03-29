# API Reference

The Python FastAPI server runs on port **8029** and exposes 32 REST endpoints plus 1 WebSocket endpoint.

> **Note:** io-gita intelligence endpoints (3) and SG predictions endpoint (1) were removed when the intelligence layer was dropped. See ARCHITECTURE.md for details.

Interactive docs: `http://localhost:8029/docs`

## Table of Contents

- [Health and Root](#health-and-root)
- [Fleet](#fleet)
- [Robots](#robots)
- [Tasks](#tasks)
- [Map](#map)
- [Analytics and Predictions](#analytics-and-predictions)
- [Telemetry](#telemetry)
- [Events](#events)
- [Simulation](#simulation)
- [WES (Warehouse Execution)](#wes-warehouse-execution)
- [WCS (Warehouse Control)](#wcs-warehouse-control)
- [Config](#config)
- [Stats](#stats)
- [Reservations](#reservations)
- [WebSocket](#websocket)

---

## Health and Root

### GET /

Root endpoint with API info.

```bash
curl http://localhost:8029/
```

```json
{
  "service": "Robotic Digital Twin API",
  "version": "0.1.0",
  "docs": "/docs",
  "endpoints": 32
}
```

### GET /health

Health check — probes MongoDB, Redis, InfluxDB, and RabbitMQ.

```bash
curl http://localhost:8029/health
```

```json
{
  "status": "healthy",
  "mongodb_ok": true,
  "redis_ok": true,
  "influxdb_ok": true,
  "rabbitmq_ok": true,
  "warehouse_loaded": true,
  "robot_loaded": true,
  "wes_loaded": true,
  "check_duration_ms": 45.2
}
```

---

## Fleet

### GET /api/fleet/status

Aggregate fleet overview: robot counts, task counts, utilisation.

```bash
curl http://localhost:8029/api/fleet/status
```

```json
{
  "total_robots": 10,
  "status_counts": {"idle": 3, "moving": 5, "charging": 2},
  "active_tasks": 8,
  "completed_tasks": 142,
  "failed_tasks": 1,
  "utilisation_pct": 70.0
}
```

---

## Robots

### GET /api/robots

List all robots from MongoDB.

```bash
curl http://localhost:8029/api/robots
```

```json
[
  {
    "robot_id": "robot_01",
    "name": "DiffDrive_01",
    "status": "moving",
    "pose": {"x": 4.0, "y": 2.0, "theta": 1.57},
    "velocity": {"linear": 1.2, "angular": 0.0},
    "battery": {"charge_pct": 85.0, "is_charging": false},
    "current_node": "S_12",
    "target_node": "DROP_1",
    "current_task_id": "task_abc123"
  }
]
```

### GET /api/robots/{robot_id}

Get a single robot by ID.

```bash
curl http://localhost:8029/api/robots/robot_01
```

Returns the full robot state object. Returns 404 if not found.

### POST /api/robots/{robot_id}/command

Send a command to a robot (writes to MongoDB command queue).

```bash
curl -X POST http://localhost:8029/api/robots/robot_01/command \
  -H "Content-Type: application/json" \
  -d '{
    "action": "move",
    "target_node": "DOCK_1",
    "parameters": {"velocity_profile": "cautious"}
  }'
```

```json
{
  "command_id": "65a1b2c3d4e5f6a7b8c9d0e1",
  "robot_id": "robot_01",
  "action": "move",
  "status": "pending"
}
```

---

## Tasks

### GET /api/tasks

List all tasks.

```bash
curl http://localhost:8029/api/tasks
```

```json
[
  {
    "task_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "task_type": "pick_and_drop",
    "status": "in_progress",
    "assigned_robot_id": "robot_01",
    "source_node": "PICK_1",
    "destination_node": "DROP_1",
    "priority": 5,
    "payload_kg": 12.5
  }
]
```

### POST /api/tasks

Create a new task.

```bash
curl -X POST http://localhost:8029/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "pick_and_drop",
    "source_node": "PICK_1",
    "destination_node": "DROP_1",
    "priority": 5,
    "payload_kg": 10.0
  }'
```

```json
{
  "task_id": "generated-uuid",
  "task_type": "pick_and_drop",
  "status": "pending",
  "source_node": "PICK_1",
  "destination_node": "DROP_1",
  "priority": 5,
  "payload_kg": 10.0
}
```

### GET /api/tasks/{task_id}

Get a single task by ID. Returns 404 if not found.

```bash
curl http://localhost:8029/api/tasks/f47ac10b-58cc-4372-a567-0e02b2c3d479
```

### DELETE /api/tasks/{task_id}

Delete (cancel) a task.

```bash
curl -X DELETE http://localhost:8029/api/tasks/f47ac10b-58cc-4372-a567-0e02b2c3d479
```

```json
{"task_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479", "status": "cancelled"}
```

### POST /api/tasks/{task_id}/cancel

Cancel a running task explicitly.

```bash
curl -X POST http://localhost:8029/api/tasks/f47ac10b-58cc-4372-a567-0e02b2c3d479/cancel
```

```json
{"task_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479", "status": "cancelled"}
```

---

## Map

### GET /api/map

Full warehouse map (nodes, edges, zones).

```bash
curl http://localhost:8029/api/map
```

```json
{
  "name": "Simple 5x5 Grid",
  "description": "Minimal demo warehouse - 25 nodes, 40 edges, 3 zones",
  "grid_spacing_m": 2.0,
  "nodes": [{"name": "DOCK_1", "x": 0, "y": 0, "type": "charge"}, "..."],
  "edges": [{"from": "DOCK_1", "to": "N_01"}, "..."],
  "zones": [{"name": "Charging", "type": "dock", "nodes": ["DOCK_1", "DOCK_2"]}, "..."]
}
```

### GET /api/map/nodes

List all nodes.

```bash
curl http://localhost:8029/api/map/nodes
```

### GET /api/map/path

Compute A* path between two nodes.

```bash
curl "http://localhost:8029/api/map/path?start=DOCK_1&end=DROP_1"
```

```json
{
  "path": ["DOCK_1", "N_10", "N_20", "N_30", "PICK_1", "N_41", "N_42", "N_43", "DROP_1"],
  "distance": 22.63,
  "hops": 8
}
```

### GET /api/map/zones

List all zones.

```bash
curl http://localhost:8029/api/map/zones
```

```json
[
  {"name": "Charging", "type": "dock", "nodes": ["DOCK_1", "DOCK_2"]},
  {"name": "Storage", "type": "shelf", "nodes": ["S_11", "S_12", "S_13", "S_21", "S_23", "S_31", "S_32", "S_33"]},
  {"name": "Operations", "type": "ops", "nodes": ["PICK_1", "DROP_1", "HUB"]}
]
```

---

## Analytics and Predictions

### GET /api/analytics/fleet

Fleet-wide analytics: throughput, average task time, battery stats.

```bash
curl http://localhost:8029/api/analytics/fleet
```

```json
{
  "total_tasks": 200,
  "completed_tasks": 180,
  "failed_tasks": 3,
  "avg_task_time_s": 45.2,
  "total_robots": 10,
  "avg_battery_pct": 72.5,
  "throughput_tasks_per_hour": 120.0
}
```

### GET /api/analytics/ab-comparison

A/B comparison of task allocation strategies.

```bash
curl http://localhost:8029/api/analytics/ab-comparison
```

```json
{
  "comparisons": [],
  "strategies": ["fifo", "nearest", "priority_weighted"]
}
```

---

## Telemetry

### GET /api/telemetry/{robot_id}

Recent telemetry points for a robot.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 100 | Max points to return (1-10000) |

```bash
curl "http://localhost:8029/api/telemetry/robot_01?limit=10"
```

```json
{
  "robot_id": "robot_01",
  "points": [
    {"timestamp": 1711500000.0, "robot_id": "robot_01", "measurement": "battery", "fields": {"charge_pct": 85.0}}
  ]
}
```

---

## Events

### GET /api/events

List system events, newest first.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 100 | Max events (1-10000) |
| `severity` | string | null | Filter: info, warning, error, critical |
| `robot_id` | string | null | Filter by robot ID |

```bash
curl "http://localhost:8029/api/events?severity=warning&limit=5"
```

```json
[
  {
    "event_id": "evt_001",
    "timestamp": 1711500000.0,
    "severity": "warning",
    "source": "battery_monitor",
    "robot_id": "robot_03",
    "message": "Battery below 20%",
    "data": {"charge_pct": 18.5}
  }
]
```

---

## Simulation

### GET /api/simulation/status

Current simulation status.

```bash
curl http://localhost:8029/api/simulation/status
```

```json
{
  "running": false,
  "tick_count": 0,
  "elapsed_s": 0.0,
  "num_robots": 0,
  "num_active_tasks": 0,
  "faults_injected": 0,
  "started_at": null
}
```

### POST /api/simulation/start

Start the simulation.

```bash
curl -X POST http://localhost:8029/api/simulation/start
```

```json
{"status": "started", "started_at": 1711500000.0}
```

### POST /api/simulation/stop

Stop the simulation.

```bash
curl -X POST http://localhost:8029/api/simulation/stop
```

```json
{"status": "stopped", "elapsed_s": 120.5}
```

### POST /api/simulation/inject-fault

Inject a fault for testing resilience.

```bash
curl -X POST http://localhost:8029/api/simulation/inject-fault \
  -H "Content-Type: application/json" \
  -d '{
    "fault_type": "motor_failure",
    "robot_id": "robot_01",
    "duration_s": 30.0,
    "parameters": {"severity": "hard"}
  }'
```

Supported fault types: `battery_drain`, `obstacle`, `network_loss`, `motor_failure`

```json
{
  "status": "fault_injected",
  "fault": {
    "fault_type": "motor_failure",
    "robot_id": "robot_01",
    "duration_s": 30.0,
    "injected_at": 1711500000.0,
    "status": "active"
  }
}
```

---

## WES (Warehouse Execution)

### POST /api/wes/inject-orders

Inject orders into the WES order generator.

```bash
curl -X POST http://localhost:8029/api/wes/inject-orders \
  -H "Content-Type: application/json" \
  -d '{"num_orders": 10, "order_type": "pick_and_drop"}'
```

```json
{
  "injected": 10,
  "orders": [
    {
      "order_id": "uuid",
      "source_node": "PICK_1",
      "destination_node": "DROP_1",
      "priority": 7,
      "payload_kg": 15.3,
      "status": "pending"
    }
  ]
}
```

### GET /api/wes/kpi

WES key performance indicators.

```bash
curl http://localhost:8029/api/wes/kpi
```

```json
{
  "orders_per_hour": 120.0,
  "pick_accuracy_pct": 98.5,
  "throughput_items_per_hour": 95.0,
  "avg_order_cycle_time_s": 45.0,
  "pending_orders": 12,
  "completed_orders": 88,
  "total_orders": 100,
  "completed_tasks": 85,
  "failed_tasks": 2
}
```

---

## WCS (Warehouse Control)

### GET /api/wcs/conveyors

List conveyor belt status.

```bash
curl http://localhost:8029/api/wcs/conveyors
```

Returns array of conveyor objects from MongoDB.

### GET /api/wcs/lanes

List warehouse lane occupancy.

```bash
curl http://localhost:8029/api/wcs/lanes
```

Returns array of lane objects from MongoDB.

---

## Config

### GET /api/config/robots

Return the loaded robot configuration (from YAML).

```bash
curl http://localhost:8029/api/config/robots
```

```json
{
  "config": {
    "name": "DiffDrive_AMR",
    "type": "differential_drive",
    "motion": {"max_linear_velocity": 2.0, "...": "..."},
    "battery": {"charge_duration_s": 600, "...": "..."}
  },
  "source": "yaml"
}
```

---

## Stats

### GET /api/stats/throughput

Throughput statistics within a time window.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `window_s` | int | 3600 | Time window in seconds (60-86400) |

```bash
curl "http://localhost:8029/api/stats/throughput?window_s=3600"
```

```json
{
  "window_s": 3600,
  "tasks_completed": 45,
  "tasks_per_hour": 45.0,
  "by_type": {"pick_and_drop": 40, "charge": 5}
}
```

---

## Reservations

### GET /api/reservations/active

List active node reservations (prevents robot collisions).

```bash
curl http://localhost:8029/api/reservations/active
```

Returns array of reservation objects from MongoDB.

---

## WebSocket

### WS /ws/fleet

Real-time fleet updates via WebSocket.

**Connect:**
```javascript
const ws = new WebSocket("ws://localhost:8029/ws/fleet");
```

**On connect, receive:**
```json
{
  "type": "connected",
  "message": "Connected to fleet WebSocket",
  "active_connections": 1
}
```

**Event types broadcast:**

| Type | Description |
|------|-------------|
| `robot_position` | Robot position update |
| `robot_state_change` | Robot status changed (idle -> moving, etc.) |
| `task_update` | Task status changed |
| `collision_alert` | Near-collision detected |
| `deadlock_event` | Deadlock detected |
| `fleet_metrics` | Periodic fleet-wide metrics |
| `wcs_event` | Warehouse control event |

**Send ping:**
```json
{"type": "ping"}
```

**Receive pong:**
```json
{"type": "pong", "ts": 1711500000.0}
```

**All messages include:**
- `_seq`: Message sequence number
- `_ts`: Server timestamp

---

## Endpoint Summary

| # | Method | Path | Description |
|---|--------|------|-------------|
| 1 | GET | `/` | Root info |
| 2 | GET | `/health` | Health check |
| 3 | GET | `/api/fleet/status` | Fleet overview |
| 4 | GET | `/api/robots` | List robots |
| 5 | GET | `/api/robots/{id}` | Single robot |
| 6 | POST | `/api/robots/{id}/command` | Send command |
| 7 | GET | `/api/tasks` | List tasks |
| 8 | POST | `/api/tasks` | Create task |
| 9 | GET | `/api/tasks/{id}` | Single task |
| 10 | DELETE | `/api/tasks/{id}` | Delete task |
| 11 | POST | `/api/tasks/{id}/cancel` | Cancel task |
| 12 | GET | `/api/map` | Full map |
| 13 | GET | `/api/map/nodes` | List nodes |
| 14 | GET | `/api/map/path` | Compute path |
| 15 | GET | `/api/map/zones` | List zones |
| 16 | GET | `/api/analytics/fleet` | Fleet analytics |
| 17 | GET | `/api/analytics/ab-comparison` | A/B comparison |
| 18 | GET | `/api/telemetry/{id}` | Robot telemetry |
| 19 | GET | `/api/events` | System events |
| 20 | GET | `/api/simulation/status` | Simulation status |
| 21 | POST | `/api/simulation/start` | Start simulation |
| 22 | POST | `/api/simulation/stop` | Stop simulation |
| 23 | POST | `/api/simulation/inject-fault` | Inject fault |
| 24 | POST | `/api/wes/inject-orders` | Inject orders |
| 25 | GET | `/api/wes/kpi` | WES KPIs |
| 26 | GET | `/api/wcs/conveyors` | Conveyor status |
| 27 | GET | `/api/wcs/lanes` | Lane occupancy |
| 28 | GET | `/api/config/robots` | Robot config |
| 29 | GET | `/api/stats/throughput` | Throughput stats |
| 30 | GET | `/api/reservations/active` | Active reservations |
| WS | WS | `/ws/fleet` | Real-time updates |

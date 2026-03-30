# API Reference

The Python FastAPI server runs on port **8029** and exposes 71 REST endpoints plus 1 WebSocket endpoint.

> **Note:** io-gita v4 intelligence layer was reinstated with a hierarchical zone-first approach after v1-v3 failed (see ARCHITECTURE.md). 3 io-gita endpoints are active.

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
- [Waves (WES)](#waves-wes)
- [io-gita Intelligence](#io-gita-intelligence)
- [Scenarios](#scenarios)
- [VDA5050 Gateway](#vda5050-gateway)
- [MAPF (Multi-Agent Path Finding)](#mapf-multi-agent-path-finding)
- [ROS2 Bridge](#ros2-bridge)
- [Warehouse Designer](#warehouse-designer)
- [WMS/ERP Connector](#wmserp-connector)
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
  "endpoints": 71
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
    "robot_type": "differential_drive",
    "status": "moving",
    "pose": {"x": 4.0, "y": 2.0, "theta": 1.57},
    "velocity": {"linear": 1.2, "angular": 0.0},
    "battery": {"charge_pct": 85.0, "is_charging": false, "voltage": 24.0, "current": 1.5, "temperature_c": 35.0},
    "current_node": "S_12",
    "target_node": "DROP_1",
    "current_task_id": "task_abc123",
    "path": ["S_12", "N_20", "N_30", "DROP_1"],
    "path_index": 1,
    "errors": [],
    "last_seen": "2026-03-30T12:00:00Z",
    "action_code": 1,
    "response_code": 0
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
  "description": "Minimal demo warehouse - 25 nodes, 40 edges, 8 zones",
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

## Order Import

### POST /api/wes/orders/import

Upload a CSV file of orders. Validates node names against warehouse config, enforces row limits, and creates tasks. Requires `X-API-Key` header.

**CSV format** (required columns: `source_node`, `destination_node`; optional: `priority`, `payload_kg`, `order_type`, `order_id`):
```csv
source_node,destination_node,priority,payload_kg,order_type
PICK_1,DROP_1,5,12.5,pick_and_drop
S_12,DROP_1,3,8.0,pick_and_drop
```

```bash
curl -X POST http://localhost:8029/api/wes/orders/import \
  -H "X-API-Key: your-api-key" \
  -F "file=@orders.csv"
```

```json
{
  "imported": 2,
  "tasks_created": 2,
  "errors": [],
  "order_ids": ["uuid-1", "uuid-2"],
  "persisted": true
}
```

**Validation rules:**
- File size limit: 10MB. Returns 413 if exceeded.
- Row limit: 10,000. Errors after limit.
- Node names must exist in loaded warehouse config.
- `source_node` and `destination_node` must differ.
- `priority` must be 0-100. `payload_kg` must be >= 0.
- `order_type` must be `pick_and_drop` or `separate`.
- CSV formula injection protection (OWASP: strips `=`, `+`, `-`, `@` prefixes).

---

## Heat Map

### GET /api/analytics/heatmap

Spatial traffic density grid for warehouse visualization. Queries InfluxDB for historical positions, falls back to MongoDB telemetry or simulated data.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `duration` | string | `1h` | Time window: 1h, 4h, 8h, 24h |
| `resolution` | float | `0.5` | Grid cell size in meters |

```bash
curl "http://localhost:8029/api/analytics/heatmap?duration=1h&resolution=0.5"
```

```json
{
  "cells": [
    {"x": 0.0, "y": 0.0, "intensity": 0.75, "visit_count": 12, "avg_dwell_time_s": 3.2, "col": 0, "row": 0}
  ],
  "resolution_m": 0.5,
  "duration": "1h",
  "data_source": "simulated",
  "grid": {
    "min_x": 0.0,
    "min_y": 0.0,
    "max_x": 8.0,
    "max_y": 8.0,
    "cols": 16,
    "rows": 16
  },
  "total_positions": 50,
  "cell_count": 12,
  "zones": [
    {
      "zone_name": "Charging",
      "zone_type": "dock",
      "node_count": 2,
      "total_visits": 15,
      "avg_visits_per_node": 7.5,
      "avg_dwell_time_s": 4.2,
      "congestion_score": 0.32
    }
  ]
}
```

**Data source priority:** InfluxDB → MongoDB telemetry → simulated from warehouse config. The `data_source` field indicates which was used.

---

## Waves (WES)

### POST /api/wes/waves

Create a wave manually (with order IDs) or auto-generate from active rules.

**Manual (explicit order IDs):**
```bash
curl -X POST http://localhost:8029/api/wes/waves \
  -H "Content-Type: application/json" \
  -d '{"order_ids": ["order_001", "order_002"], "zone_affinity": "Storage", "max_robots": 3}'
```

```json
{
  "wave": {
    "wave_id": "wave_abc123",
    "order_ids": ["order_001", "order_002"],
    "zone_affinity": "Storage",
    "max_robots": 3,
    "status": "pending",
    "created_at": 1711500000.0
  },
  "mode": "manual",
  "persisted": true
}
```

**Auto (from rules on pending orders):**
```bash
curl -X POST http://localhost:8029/api/wes/waves \
  -H "Content-Type: application/json" -d '{}'
```

```json
{
  "waves": [],
  "count": 0,
  "mode": "auto",
  "pending_orders_evaluated": 12
}
```

### GET /api/wes/waves

List all waves with status summary.

```bash
curl http://localhost:8029/api/wes/waves
```

```json
{
  "waves": [],
  "count": 0,
  "summary": {"pending": 0, "active": 0, "completed": 0}
}
```

### POST /api/wes/waves/{wave_id}/release

Release a pending wave — generates tasks for all orders in the wave.

```bash
curl -X POST http://localhost:8029/api/wes/waves/wave_abc123/release
```

```json
{
  "wave_id": "wave_abc123",
  "status": "active",
  "tasks_created": 2,
  "task_ids": ["task_001", "task_002"]
}
```

Returns 404 if wave not found. Returns 409 if wave is not in "pending" status.

### POST /api/wes/wave-rules

Create a wave rule for auto-wave generation.

```bash
curl -X POST http://localhost:8029/api/wes/wave-rules \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Zone A batch",
    "conditions": {"zone": "Storage", "min_orders": 5},
    "action": {"max_robots": 3},
    "enabled": true
  }'
```

```json
{
  "rule": {
    "rule_id": "rule_abc",
    "name": "Zone A batch",
    "conditions": {"zone": "Storage", "min_orders": 5},
    "action": {"max_robots": 3},
    "enabled": true
  }
}
```

### GET /api/wes/wave-rules

List all wave rules.

```bash
curl http://localhost:8029/api/wes/wave-rules
```

```json
{
  "rules": [],
  "count": 0
}
```

---

## io-gita Intelligence

### GET /api/iogita/status

Return io-gita v4 intelligence layer status.

```bash
curl http://localhost:8029/api/iogita/status
```

```json
{
  "engine": "io-gita-v4-hierarchical",
  "version": "4.0",
  "zone_identifier_loaded": true,
  "cold_start_loaded": true,
  "backend": "hierarchical_hopfield_d10000",
  "num_zones": 3,
  "num_nodes": 25,
  "strategy": "zone-first (12 geometry features) → node-second (graph + 16 features)"
}
```

### GET /api/iogita/zones

Return zone identification results for each robot from MongoDB poses.

```bash
curl http://localhost:8029/api/iogita/zones
```

```json
{
  "zones": [
    {"robot_id": "robot_01", "zone": "Storage", "pose": {"x": 4.0, "y": 2.0, "theta": 1.57}}
  ],
  "engine": "io-gita-v4-hierarchical"
}
```

### POST /api/iogita/cold-start/{robot_id}

Trigger cold start recovery for a robot. Requires `X-API-Key` header.

```bash
curl -X POST http://localhost:8029/api/iogita/cold-start/robot_01 \
  -H "X-API-Key: your-api-key"
```

```json
{
  "robot_id": "robot_01",
  "recovery_hints": {"suggested_zone": "Charging", "confidence": 0.85},
  "cold_start_engine": "io-gita-v4"
}
```

Returns 503 if cold start engine is not available.

### POST /api/iogita/recover/{robot_id}

Full LiDAR-based cold start recovery using KDTree engine. Requires `X-API-Key` header.

**Request body:**

| Field | Type | Description |
|-------|------|-------------|
| `scan` | list[float] | 360-ray LiDAR scan |
| `last_known_node` | string | Last confirmed node (from FMS) |
| `heading_deg` | float | Current heading in degrees (from IMU) |

```bash
curl -X POST http://localhost:8029/api/iogita/recover/robot_01 \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"scan": [1.0, 1.5, ...], "last_known_node": "DOCK_1", "heading_deg": 90.0}'
```

```json
{
  "robot_id": "robot_01",
  "zone": "Charging",
  "node": "DOCK_1",
  "zone_confidence": 0.95,
  "node_confidence": 0.88,
  "method": "kdtree_nearest",
  "recovery_time_ms": 0.008,
  "safety_ok": true,
  "engine": "io-gita-v5-kdtree"
}
```

Returns 400 if `scan` is missing or invalid. Returns 503 if KDTree engine is not available.

---

## Scenarios

Parallel scenario comparison: create, list, run, compare, and archive scenarios. Mutation endpoints require `X-API-Key` header.

### GET /api/scenarios

List all scenarios.

```bash
curl http://localhost:8029/api/scenarios
```

```json
[
  {
    "scenario_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "name": "Baseline FIFO",
    "status": "completed",
    "config": {"fleet_size": 5, "allocation_strategy": "fifo", "...": "..."},
    "created_at": 1711500000.0,
    "completed_at": 1711500060.0,
    "kpis": {"throughput_items_per_hour": 95.0, "...": "..."}
  }
]
```

Returns empty array if no scenarios exist. Returns 503 if MongoDB is unavailable.

### POST /api/scenarios

Create a new scenario with the given configuration. Validates that warehouse and robot configs exist. Maximum 1000 active (non-archived) scenarios allowed.

**Request body (ScenarioConfig):**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | *required* | Scenario name (1-200 chars) |
| `description` | string | `""` | Optional description |
| `fleet_size` | int | `5` | Number of robots (1-200) |
| `robot_config` | string | `"differential_drive"` | Robot config name |
| `allocation_strategy` | string | `"fifo"` | Strategy: fifo, nearest, priority_weighted |
| `warehouse_config` | string | `"simple_grid"` | Warehouse config name |
| `order_count` | int | `50` | Orders to generate (1-10000) |
| `order_seed` | int | `null` | RNG seed for reproducibility |
| `duration_s` | float | `60` | Simulation duration (10-3600) |

```bash
curl -X POST http://localhost:8029/api/scenarios \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Baseline FIFO",
    "description": "Baseline with FIFO allocation",
    "fleet_size": 5,
    "robot_config": "differential_drive",
    "allocation_strategy": "fifo",
    "warehouse_config": "simple_grid",
    "order_count": 50,
    "order_seed": 42,
    "duration_s": 60
  }'
```

```json
{
  "scenario_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "name": "Baseline FIFO",
  "description": "Baseline with FIFO allocation",
  "status": "created",
  "config": {
    "fleet_size": 5,
    "robot_config": "differential_drive",
    "allocation_strategy": "fifo",
    "warehouse_config": "simple_grid",
    "order_count": 50,
    "order_seed": 42,
    "duration_s": 60
  },
  "created_at": 1711500000.0,
  "completed_at": null,
  "kpis": null
}
```

Returns 400 if warehouse/robot config not found, allocation strategy invalid, or active scenario limit (1000) reached. Returns 422 if field validation fails. Returns 503 if database is unavailable.

### POST /api/scenarios/{id}/run

Execute a scenario — generates orders, simulates task completion, computes KPIs. Optionally override simulation duration (10-3600s).

```bash
curl -X POST http://localhost:8029/api/scenarios/a1b2c3d4-e5f6-7890-abcd-ef1234567890/run \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"duration_override": 120}'
```

```json
{
  "scenario_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "completed",
  "kpis": {
    "throughput_items_per_hour": 95.0,
    "avg_order_cycle_time_s": 12.3,
    "pick_accuracy_pct": 100.0,
    "completed_orders": 45,
    "pending_orders": 5,
    "total_orders": 50,
    "completed_tasks": 45,
    "failed_tasks": 0
  },
  "completed_at": 1711500060.0
}
```

Returns 404 if scenario not found. Returns 409 if scenario is in an invalid state for running. Returns 422 if `duration_override` is outside 10-3600 range. Returns 503 if database is unavailable.

### DELETE /api/scenarios/{id}

Archive a scenario — drops namespace collections and sets status to 'archived'. Requires `X-API-Key` header.

```bash
curl -X DELETE http://localhost:8029/api/scenarios/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "X-API-Key: your-api-key"
```

```json
{
  "scenario_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "archived"
}
```

Returns 404 if scenario not found. Returns 503 if database is unavailable.

### GET /api/scenarios/{id}/results

Get KPIs for a completed scenario.

```bash
curl http://localhost:8029/api/scenarios/a1b2c3d4-e5f6-7890-abcd-ef1234567890/results
```

```json
{
  "scenario_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "name": "Baseline FIFO",
  "status": "completed",
  "config": {
    "fleet_size": 5,
    "robot_config": "differential_drive",
    "allocation_strategy": "fifo",
    "warehouse_config": "simple_grid",
    "order_count": 50,
    "order_seed": 42,
    "duration_s": 60
  },
  "kpis": {
    "throughput_items_per_hour": 95.0,
    "avg_order_cycle_time_s": 12.3,
    "pick_accuracy_pct": 100.0,
    "completed_orders": 45,
    "pending_orders": 5,
    "total_orders": 50,
    "completed_tasks": 45,
    "failed_tasks": 0
  },
  "completed_at": 1711500060.0
}
```

Returns 404 if scenario not found. Returns 409 if scenario is not yet completed. Returns 503 if database is unavailable.

### GET /api/scenarios/compare

Compare 2 or more completed scenarios. Returns JSON by default, or CSV/PDF exports. Maximum 10 scenario IDs per comparison.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ids` | string | *required* | Comma-separated scenario IDs (2-10) |
| `format` | string | `null` | Export format: `csv` or `pdf` |

```bash
# JSON comparison
curl "http://localhost:8029/api/scenarios/compare?ids=id_a,id_b"

# CSV export
curl "http://localhost:8029/api/scenarios/compare?ids=id_a,id_b&format=csv" -o comparison.csv

# PDF export
curl "http://localhost:8029/api/scenarios/compare?ids=id_a,id_b&format=pdf" -o comparison.pdf
```

**JSON response:**
```json
{
  "scenarios": [
    {
      "scenario_id": "id_a",
      "name": "Small Fleet",
      "config": {"fleet_size": 3, "allocation_strategy": "fifo", "...": "..."},
      "kpis": {"throughput_items_per_hour": 60.0, "avg_order_cycle_time_s": 15.0, "...": "..."}
    },
    {
      "scenario_id": "id_b",
      "name": "Large Fleet",
      "config": {"fleet_size": 10, "allocation_strategy": "nearest", "...": "..."},
      "kpis": {"throughput_items_per_hour": 120.0, "avg_order_cycle_time_s": 8.0, "...": "..."}
    }
  ],
  "deltas": [
    {
      "scenario_id": "id_b",
      "name": "Large Fleet",
      "vs_baseline": {"throughput_items_per_hour": 60.0, "avg_order_cycle_time_s": -7.0}
    }
  ],
  "rankings": [
    {"rank": 1, "scenario_id": "id_b", "name": "Large Fleet", "throughput_items_per_hour": 120.0, "avg_order_cycle_time_s": 8.0},
    {"rank": 2, "scenario_id": "id_a", "name": "Small Fleet", "throughput_items_per_hour": 60.0, "avg_order_cycle_time_s": 15.0}
  ],
  "baseline_scenario_id": "id_a"
}
```

**CSV export** contains one row per KPI metric, one column per scenario. CSV values are sanitized against formula injection (=, +, -, @, \t, \r prefixes stripped).

**PDF export** contains configuration table, KPI comparison table, and rankings table in a formatted A4 report. HTML/script content is escaped in all text cells.

Returns 400 if fewer than 2 IDs or more than 10 IDs provided. Returns 404 if any scenario not found. Returns 409 if any scenario is not yet completed. Returns 503 if database is unavailable.

---

## VDA5050 Gateway

VDA5050 v2.0 standard AGV communication via MQTT. Orders and instant actions are published to the MQTT broker; AGV state/connection/visualization messages are received and cached.

Write endpoints (`POST`) require `X-API-Key` header when `API_KEY` is set. Resource limits: max 200 AGVs, max 500 nodes per order, max 256 KB MQTT message size.

### GET /api/vda5050/status

Gateway status: broker connection state and connected AGV count.

```bash
curl http://localhost:8029/api/vda5050/status
```

```json
{
  "broker_connected": true,
  "agvs_online": 3,
  "agvs_total": 5,
  "gateway_initialized": true
}
```

### POST /api/vda5050/orders

Send VDA5050 order to AGV via MQTT. Requires `X-API-Key` header.

```bash
curl -X POST http://localhost:8029/api/vda5050/orders \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "agv_id": "AGV-001",
    "order": {
      "headerId": 1,
      "timestamp": "2026-03-30T10:00:00.000Z",
      "version": "2.0.0",
      "manufacturer": "TestCorp",
      "serialNumber": "AGV-001",
      "orderId": "order_001",
      "orderUpdateId": 0,
      "nodes": [
        {"nodeId": "PICK_1", "sequenceId": 0, "released": true,
         "nodePosition": {"x": 0.0, "y": 8.0, "theta": 0.0, "mapId": "wh1"},
         "actions": [{"actionType": "pick", "actionId": "a1", "blockingType": "HARD"}]},
        {"nodeId": "DROP_1", "sequenceId": 2, "released": true,
         "nodePosition": {"x": 8.0, "y": 8.0, "theta": 0.0, "mapId": "wh1"},
         "actions": [{"actionType": "drop", "actionId": "a2", "blockingType": "HARD"}]}
      ],
      "edges": [
        {"edgeId": "e1", "sequenceId": 1, "released": true,
         "startNodeId": "PICK_1", "endNodeId": "DROP_1"}
      ]
    }
  }'
```

```json
{
  "status": "dispatched",
  "agv_id": "AGV-001",
  "order_id": "order_001"
}
```

Returns 400 if order is invalid or exceeds 500 nodes. Returns 403 if API key is missing/invalid. Returns 503 if MQTT broker is not connected.

### POST /api/vda5050/instant-actions

Send instant action (E-stop, cancel, pause) to AGV via MQTT. Requires `X-API-Key` header.

```bash
curl -X POST http://localhost:8029/api/vda5050/instant-actions \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "agv_id": "AGV-001",
    "action_type": "cancelOrder",
    "action_id": "cancel_001"
  }'
```

```json
{
  "status": "sent",
  "agv_id": "AGV-001",
  "action_type": "cancelOrder",
  "action_id": "cancel_001"
}
```

Returns 403 if API key is missing/invalid. Returns 503 if MQTT broker is not connected.

### GET /api/vda5050/agvs

List all connected AGVs with their latest VDA5050 state.

```bash
curl http://localhost:8029/api/vda5050/agvs
```

```json
[
  {
    "serial_number": "AGV-001",
    "last_state": {
      "orderId": "order_001",
      "lastNodeId": "N_20",
      "agvPosition": {"x": 4.0, "y": 4.0, "theta": 1.57},
      "batteryState": {"batteryCharge": 85.0, "charging": false},
      "operatingMode": "AUTOMATIC",
      "driving": true
    }
  }
]
```

### GET /api/vda5050/agvs/{agv_id}/state

Get latest VDA5050 state for a specific AGV.

```bash
curl http://localhost:8029/api/vda5050/agvs/AGV-001/state
```

```json
{
  "serial_number": "AGV-001",
  "state": {
    "orderId": "order_001",
    "lastNodeId": "N_20",
    "agvPosition": {"x": 4.0, "y": 4.0, "theta": 1.57, "mapId": "wh1", "positionInitialized": true},
    "batteryState": {"batteryCharge": 85.0, "batteryVoltage": 48.0, "charging": false},
    "operatingMode": "AUTOMATIC",
    "driving": true,
    "safetyState": {"eStop": "NONE", "fieldViolation": false}
  }
}
```

Returns 404 if AGV not found or no state received.

---

## MAPF (Multi-Agent Path Finding)

Phase 11: Multi-Agent Path Finding for 100+ robot fleets. Two algorithms:
- **CBS** (Conflict-Based Search): Optimal, offline planning. Exponential complexity — use for ≤50 agents.
- **PIBT** (Priority Inheritance with Backtracking): Suboptimal, real-time. Linear complexity — use for 15Hz FMS loops.

### POST /api/mapf/solve

Solve MAPF for given agents using CBS or PIBT.

**CBS (full path planning):**
```bash
curl -X POST http://localhost:8029/api/mapf/solve \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "solver": "cbs",
    "agents": [
      {"agent_id": "R1", "start": "DOCK_1", "goal": "DROP_1"},
      {"agent_id": "R2", "start": "DROP_1", "goal": "DOCK_1"}
    ],
    "time_limit_s": 5.0
  }'
```

```json
{
  "paths": {
    "R1": ["DOCK_1", "N_01", "N_02", "DROP_1"],
    "R2": ["DROP_1", "N_02", "N_01", "DOCK_1"]
  },
  "cost": 6,
  "conflicts_resolved": 2,
  "solve_time_ms": 45.2,
  "success": true
}
```

**PIBT (single step for real-time):**
```bash
curl -X POST http://localhost:8029/api/mapf/solve \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "solver": "pibt",
    "agents": [
      {"agent_id": "R1", "start": "DOCK_1", "goal": "DROP_1"},
      {"agent_id": "R2", "start": "DROP_1", "goal": "DOCK_1"}
    ]
  }'
```

```json
{
  "success": true,
  "moves": {
    "R1": "N_01",
    "R2": "N_02"
  }
}
```

**Limits:**
- CBS: max 200 agents (exponential complexity — practical limit ~50 for reliable solving)
- PIBT: max 500 agents (linear complexity — completes in <67ms for 100 agents)
- `time_limit_s`: 0.001–30 seconds

### GET /api/mapf/status

Solver status — last solve time, conflicts resolved, total solves.

```bash
curl http://localhost:8029/api/mapf/status
```

```json
{
  "last_solve_time_ms": 45.2,
  "last_conflicts_resolved": 2,
  "total_solves": 15
}
```

### POST /api/mapf/step

Single PIBT step for real-time FMS integration (15Hz loop). Requires auth.

```bash
curl -X POST http://localhost:8029/api/mapf/step \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "agents": [
      {"agent_id": "R1", "position": "DOCK_1", "goal": "DROP_1", "priority": 1, "wait_time": 0},
      {"agent_id": "R2", "position": "DROP_1", "goal": "DOCK_1", "priority": 2, "wait_time": 5}
    ]
  }'
```

```json
{
  "success": true,
  "moves": {
    "R1": "N_01",
    "R2": "DROP_1"
  }
}
```

Priority: higher value = processed first. Wait time: longer wait = higher effective priority.

### GET /api/mapf/benchmarks

Performance metrics — solve time vs agent count.

```bash
curl http://localhost:8029/api/mapf/benchmarks
```

```json
{
  "solves": [
    {"solver": "cbs", "agent_count": 10, "solve_time_ms": 45.2, "conflicts_resolved": 2, "success": true},
    {"solver": "pibt", "agent_count": 100, "solve_time_ms": 12.3, "success": true}
  ],
  "total_solves": 15
}
```

History limited to 1000 entries (prevents unbounded memory growth).

### GET /api/mapf/congestion

Congestion hotspot data — top bottleneck nodes and full congestion map. Updated after every MAPF solve/step with agent positions.

```bash
curl http://localhost:8029/api/mapf/congestion
```

```json
{
  "congestion_map": {
    "HUB": {"occupancy": 30, "wait_time_avg": 2.5, "throughput": 8},
    "N_01": {"occupancy": 10, "wait_time_avg": 1.0, "throughput": 5},
    "DOCK_1": {"occupancy": 2, "wait_time_avg": 0.0, "throughput": 2}
  },
  "bottlenecks": [
    {"node_id": "HUB", "occupancy": 30, "wait_time_avg": 2.5, "throughput": 8},
    {"node_id": "N_01", "occupancy": 10, "wait_time_avg": 1.0, "throughput": 5}
  ],
  "total_nodes_tracked": 3
}
```

Returns top 10 bottleneck nodes sorted by occupancy descending.

---

## ROS2 Bridge

Phase 10: Bridge between FMS and ROS2 nav2 stack. Graceful fallback when ROS2 is unavailable.

### GET /api/ros2/status

Bridge status (ROS2 available, mode, topics).

```bash
curl http://localhost:8029/api/ros2/status
```

```json
{
  "ros2_available": false,
  "bridge_mode": "simulated",
  "fms_url": "http://localhost:7012",
  "subscribed_topics": 0,
  "discovered_nodes": 0,
  "bridge_initialized": true
}
```

### GET /api/ros2/topics

List canonical ROS2 topics with message types.

```bash
curl http://localhost:8029/api/ros2/topics
```

```json
[
  {"topic_type": "cmd_vel", "template": "/{robot_id}/cmd_vel", "msg_type": "geometry_msgs/msg/Twist", "source": "simulated"},
  {"topic_type": "odom", "template": "/{robot_id}/odom", "msg_type": "nav_msgs/msg/Odometry", "source": "simulated"},
  {"topic_type": "scan", "template": "/{robot_id}/scan", "msg_type": "sensor_msgs/msg/LaserScan", "source": "simulated"},
  {"topic_type": "nav_goal", "template": "/{robot_id}/navigate_to_pose", "msg_type": "nav2_msgs/action/NavigateToPose", "source": "simulated"}
]
```

### POST /api/ros2/nav-goal

Send navigation goal to robot via ROS2 nav2 or simulated HAL. Requires API key when auth is enabled.

```bash
curl -X POST http://localhost:8029/api/ros2/nav-goal \
  -H "Content-Type: application/json" \
  -d '{"robot_id": "AMR-01", "x": 5.0, "y": 3.0, "theta": 1.57}'
```

```json
{
  "status": "simulated",
  "robot_id": "AMR-01",
  "goal": {"x": 5.0, "y": 3.0, "theta": 1.57},
  "mode": "simulated",
  "timestamp": 1711800000.0
}
```

### GET /api/ros2/pose/{robot_id}

Get robot pose from ROS2 odom topic or simulation.

```bash
curl http://localhost:8029/api/ros2/pose/AMR-01
```

```json
{
  "robot_id": "AMR-01",
  "pose": {"x": 0.0, "y": 0.0, "theta": 0.0},
  "source": "simulated",
  "mode": "simulated"
}
```

---

## Warehouse Designer

### POST /api/designer/validate

Validate a warehouse JSON config. Checks node fields, edge references, graph connectivity, required node types (charge, pick, drop), duplicate names, and overlapping positions.

```bash
curl -X POST http://localhost:8029/api/designer/validate \
  -H "Content-Type: application/json" \
  -d '{"name":"test","nodes":[{"name":"A","x":0,"y":0,"type":"charge"}],"edges":[]}'
```

```json
{
  "valid": false,
  "errors": ["No pick node found. At least 1 pick node is required.", "No drop node found. At least 1 drop node is required."],
  "warnings": []
}
```

### POST /api/designer/export

Save a validated warehouse config to `configs/warehouses/{name}.json`. Rejects invalid configs with 400.

```bash
curl -X POST http://localhost:8029/api/designer/export \
  -H "Content-Type: application/json" \
  -d '{"name":"my_warehouse","config":{...valid config...}}'
```

```json
{
  "saved": true,
  "path": "/path/to/configs/warehouses/my_warehouse.json",
  "node_count": 25,
  "edge_count": 40
}
```

### GET /api/designer/templates

List available warehouse templates (files matching `template_*.json`).

```bash
curl http://localhost:8029/api/designer/templates
```

```json
[
  {"name": "template_small", "description": "Minimal 9-node warehouse...", "node_count": 9, "edge_count": 12},
  {"name": "template_medium", "description": "Medium 25-node warehouse...", "node_count": 25, "edge_count": 40},
  {"name": "template_large", "description": "Large 49-node warehouse...", "node_count": 49, "edge_count": 84}
]
```

### GET /api/designer/templates/{name}

Get a specific template JSON for editing. Returns 404 if template not found.

```bash
curl http://localhost:8029/api/designer/templates/template_small
```

Returns the full warehouse config JSON (nodes, edges, zones).

---

## WMS/ERP Connector

WMS integration layer supporting SAP, Odoo, and generic webhook adapters.
All write endpoints require `X-API-Key` header (see Auth).

### GET /api/wms/status

Connector status including type, connection state, and DLQ summary.

```bash
curl http://localhost:8029/api/wms/status
```

```json
{
  "connector_initialized": true,
  "type": "webhook",
  "connected": true,
  "dlq": {"total": 0, "dead": 0, "retrying": 0, "rabbitmq_connected": false},
  "pending_orders": 0,
  "processed_orders": 3
}
```

### POST /api/wms/sync

Trigger order sync — pulls pending orders from the active connector, translates them to internal format, and stores them. Requires API key.

```bash
curl -X POST http://localhost:8029/api/wms/sync \
  -H "X-API-Key: $API_KEY"
```

```json
{"synced": 2, "errors": 0, "total_orders": 5}
```

### GET /api/wms/orders

List all synced orders (translated to internal format).

```bash
curl http://localhost:8029/api/wms/orders
```

```json
{
  "orders": [
    {"order_id": "WH-001", "source": "webhook", "items": [...], "priority": 3, "customer": "Acme"}
  ],
  "total": 1
}
```

### POST /api/wms/webhook/receive

Receive an order via webhook push. Any external WMS can POST orders here. Requires API key. Returns 409 for duplicate order IDs.

```bash
curl -X POST http://localhost:8029/api/wms/webhook/receive \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"id": "WH-001", "items": [{"sku": "BOLT-M8", "quantity": 50}], "priority": 2, "customer": "Acme"}'
```

```json
{"internal_id": "a1b2c3d4", "status": "received"}
```

### GET /api/wms/dlq

List dead letter queue entries (failed order processing), newest first.

```bash
curl http://localhost:8029/api/wms/dlq?limit=50
```

```json
{
  "dead_letters": [
    {"message_id": "abc123", "order": {...}, "error": "Connection timeout", "status": "dead"}
  ],
  "total": 1,
  "rabbitmq_connected": false
}
```

### POST /api/wms/dlq/{id}/retry

Retry a dead letter. Returns the order for re-processing. Requires API key.

```bash
curl -X POST http://localhost:8029/api/wms/dlq/abc123/retry \
  -H "X-API-Key: $API_KEY"
```

```json
{"message_id": "abc123", "status": "retrying", "retry_count": 1, "order": {...}}
```

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
| 31 | POST | `/api/wes/orders/import` | CSV order import |
| 32 | GET | `/api/analytics/heatmap` | Traffic density heat map |
| 33 | POST | `/api/wes/waves` | Create/auto-generate wave |
| 34 | GET | `/api/wes/waves` | List waves |
| 35 | POST | `/api/wes/waves/{id}/release` | Release wave → tasks |
| 36 | POST | `/api/wes/wave-rules` | Create wave rule |
| 37 | GET | `/api/wes/wave-rules` | List wave rules |
| 38 | GET | `/api/iogita/status` | io-gita v4 status |
| 39 | GET | `/api/iogita/zones` | Zone identification |
| 40 | POST | `/api/iogita/cold-start/{id}` | Cold start recovery |
| 41 | POST | `/api/iogita/recover/{id}` | LiDAR-based recovery (KDTree) |
| 42 | GET | `/api/scenarios` | List scenarios |
| 43 | POST | `/api/scenarios` | Create scenario |
| 44 | POST | `/api/scenarios/{id}/run` | Run scenario |
| 45 | GET | `/api/scenarios/{id}/results` | Scenario KPIs |
| 46 | DELETE | `/api/scenarios/{id}` | Archive scenario |
| 47 | GET | `/api/scenarios/compare` | Compare scenarios (csv/pdf) |
| 48 | POST | `/api/designer/validate` | Validate warehouse config |
| 49 | POST | `/api/designer/export` | Export warehouse config to file |
| 50 | GET | `/api/designer/templates` | List warehouse templates |
| 51 | GET | `/api/designer/templates/{name}` | Get template JSON |
| 52 | GET | `/api/vda5050/status` | VDA5050 gateway status |
| 53 | POST | `/api/vda5050/orders` | Send VDA5050 order to AGV |
| 54 | POST | `/api/vda5050/instant-actions` | Send instant action (E-stop) |
| 55 | GET | `/api/vda5050/agvs` | List connected AGVs |
| 56 | GET | `/api/vda5050/agvs/{id}/state` | Get AGV VDA5050 state |
| 57 | GET | `/api/ros2/status` | ROS2 bridge status |
| 58 | GET | `/api/ros2/topics` | List ROS2 topics |
| 59 | POST | `/api/ros2/nav-goal` | Send navigation goal |
| 60 | GET | `/api/ros2/pose/{robot_id}` | Get robot pose from ROS2 |
| 61 | GET | `/api/wms/status` | WMS connector status |
| 62 | POST | `/api/wms/sync` | Trigger order sync from WMS |
| 63 | GET | `/api/wms/orders` | List synced orders |
| 64 | POST | `/api/wms/webhook/receive` | Receive order via webhook |
| 65 | GET | `/api/wms/dlq` | List dead letter queue |
| 66 | POST | `/api/wms/dlq/{id}/retry` | Retry dead letter |
| WS | WS | `/ws/fleet` | Real-time updates |

# User Experience — How It Works

## The Promise

You have a warehouse. You have robots. You want to simulate them before deploying.

```
Step 1: Describe your warehouse (JSON)
Step 2: Describe your robot (YAML)
Step 3: docker compose up
Step 4: Open browser → robots moving in your warehouse
```

That's it. No C++ compilation. No ROS2 setup. No Gazebo configuration.
You bring the map and robot specs. We bring the simulation.

---

## Step 1: Describe Your Warehouse

Create `my_warehouse.json`:

```json
{
  "name": "My Warehouse",
  "grid_spacing_m": 0.8,
  "nodes": [
    {"name": "DOCK_1",  "x": 0.0,  "y": 0.0, "type": "charge"},
    {"name": "AISLE_1", "x": 5.0,  "y": 0.0, "type": "aisle"},
    {"name": "SHELF_1", "x": 5.0,  "y": 5.0, "type": "shelf"},
    {"name": "SHELF_2", "x": 10.0, "y": 5.0, "type": "shelf"},
    {"name": "DROP_1",  "x": 10.0, "y": 0.0, "type": "drop"}
  ],
  "edges": [
    {"from": "DOCK_1",  "to": "AISLE_1"},
    {"from": "AISLE_1", "to": "SHELF_1"},
    {"from": "SHELF_1", "to": "SHELF_2"},
    {"from": "SHELF_2", "to": "DROP_1"},
    {"from": "DROP_1",  "to": "AISLE_1"}
  ],
  "zones": [
    {"name": "Storage", "type": "shelf", "nodes": ["SHELF_1", "SHELF_2"]},
    {"name": "Docking", "type": "dock",  "nodes": ["DOCK_1"]}
  ]
}
```

Or use our demo warehouse (BotValley — 63 nodes, real Addverb layout).

---

## Step 2: Describe Your Robot

Create `my_robot.yaml`:

```yaml
name: "MyAMR"
type: differential_drive       # or: unidirectional, omnidirectional

motion:
  max_linear_velocity: 1.4     # m/s
  max_angular_velocity: 1.57   # rad/s
  linear_acceleration: 0.8     # m/s²
  position_tolerance: 0.07     # m

dimensions:
  length: 0.8                  # m
  width: 0.6                   # m
  height: 0.3                  # m
  wheel_separation: 0.5        # m
  wheel_radius: 0.075          # m

sensors:
  lidar:
    type: "2d"
    fov_deg: 360               # or 30 for obstacle-only sensor
    range_m: 5.0
    rays: 360
  barcode_reader:
    enabled: true
    debounce_ms: 5

battery:
  charge_duration_s: 450       # seconds to full charge
  discharge_duration_s: 60000  # seconds of operation
  critical_threshold: 20       # % — seek charger below this

obstacle_thresholds:
  critical_m: 0.7              # emergency stop
  warning_m: 0.8               # decelerate
  planning_m: 1.5              # replan path

attachment:
  type: "conveyor"             # or: lifter, none, tug
  load_time_s: 3
  unload_time_s: 3

behavior_tree: "default_agv.xml"  # or custom XML path
```

Or use our presets: `differential_drive.yaml`, `unidirectional.yaml`.

---

## Step 3: Run

```bash
# Clone
git clone https://github.com/ai-meharbnsingh/robotic_digital_twin_simulation.git
cd robotic_digital_twin_simulation

# Drop your files in
cp my_warehouse.json configs/warehouses/
cp my_robot.yaml configs/robots/

# Run
docker compose up

# Or with a specific config
WAREHOUSE=my_warehouse ROBOT=my_robot docker compose up
```

---

## Step 4: See It

Open browser:

| URL | What |
|-----|------|
| http://localhost:5199 | React Dashboard — live warehouse grid, robot positions, tasks |
| http://localhost:8029/docs | REST API — Swagger docs, try endpoints |
| http://localhost:3000 | Grafana — throughput, battery metrics |
| Gazebo GUI (X11) | 3D warehouse with robots moving |

---

## What You Get

### Out of the box:
- 10 robots running simultaneously in your warehouse
- Task assignment (FIFO) — orders come in, robots pick and deliver
- A* pathfinding on your map
- Deadlock prevention (ILP node reservation)
- Collision avoidance
- Battery management (charge when low)
- Behavior trees (dock, charge, pick, move, drop)

---

## API Examples

```bash
# Fleet status
curl http://localhost:8029/api/fleet/status

# Create a task
curl -X POST http://localhost:8029/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"type": "PICK", "source": "SHELF_1", "dest": "DROP_1", "priority": 1}'

# Get robot positions
curl http://localhost:8029/api/robots

# Inject 50 orders (stress test)
curl -X POST http://localhost:8029/api/wes/inject-orders \
  -d '{"count": 50, "priority": "HIGH"}'

# Inject a fault
curl -X POST http://localhost:8029/api/simulation/inject-fault \
  -d '{"robot_id": "robot_01", "fault_type": "motor_failure"}'
```

---

## For Robotics Companies

### "I have Addverb Zippy10 robots"
```bash
cp configs/robots/unidirectional.yaml configs/robots/zippy10.yaml
# Edit zippy10.yaml with your ActionCodes.yaml values
ROBOT=zippy10 docker compose up
```

### "I have MiR AMR 250 robots"
```bash
cp configs/robots/differential_drive.yaml configs/robots/mir250.yaml
# Edit with MiR specs: 1.5 m/s, differential drive, 250kg payload
ROBOT=mir250 docker compose up
```

### "I have a custom warehouse"
```bash
# Export your warehouse map as JSON (nodes + edges + zones)
# Most fleet management systems can export this
cp my_export.json configs/warehouses/my_site.json
WAREHOUSE=my_site docker compose up
```


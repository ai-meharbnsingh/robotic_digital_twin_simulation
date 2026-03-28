# Configuration System

Three things to configure before running the simulation:

1. **Warehouse** — the navigation graph (nodes, edges, zones)
2. **Robot** — the physical robot parameters (speed, size, battery, sensors)
3. **Behavior Tree** — the decision logic (what the robot does and when)

## Directory Layout

```
configs/
  warehouses/           # Warehouse map files (JSON)
    simple_grid.json    # 25-node demo grid
    botvalley.json      # 63-node production warehouse
  robots/               # Robot preset files (YAML)
    differential_drive.yaml   # AMR (2-wheel, omnidirectional)
    unidirectional.yaml       # AGV (forward-only, conveyor-top)
  behavior_trees/       # Behavior tree definitions (XML, BTCPP v4)
    default_agv.xml     # AGV lifecycle: idle -> pickup -> move -> drop -> charge
    default_amr.xml     # AMR lifecycle: same, with obstacle avoidance + lifter
```

## Quick Start

Run the simulation with default settings (simple grid, differential drive AMR):

```bash
docker compose up
```

Run with a specific warehouse and robot:

```bash
WAREHOUSE=botvalley ROBOT=unidirectional docker compose up
```

## How They Connect

The robot YAML references its behavior tree:

```yaml
# In configs/robots/unidirectional.yaml
behavior_tree: "default_agv.xml"
```

The FMS server loads the warehouse map at startup:

```
configs/warehouses/{WAREHOUSE}.json  -->  C++ GraphMap  -->  A* pathfinding
configs/robots/{ROBOT}.yaml          -->  C++ Config    -->  MPC, battery, sensors
configs/behavior_trees/{BT}.xml      -->  C++ BTEngine  -->  action sequencing
```

## Customization

Each subdirectory has its own README with the full format specification:

- `warehouses/README.md` — JSON format, node types, how to build a custom map
- `robots/README.md` — YAML format, all parameters with descriptions, how to copy and customize

To add a new robot or warehouse, copy the closest preset and edit. No code changes needed.

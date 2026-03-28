# Warehouse Configuration

Warehouse maps define the navigation graph that robots drive on: nodes (positions), edges (connections between nodes), and zones (logical areas).

## JSON Format

### Top-level keys

| Key | Type | Description |
|-----|------|-------------|
| `nodes` | array | All navigable positions in the warehouse |
| `edges` | array | Connections between nodes (the paths robots can drive) |
| `zones` | array | Logical groupings of nodes (charging area, storage, operations) |

### Node object

```json
{
  "name": "DOCK_1",
  "x": 0,
  "y": 0,
  "type": "charge"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Unique node identifier. Convention: `DOCK_*` for chargers, `S_*` for shelves, `N_*` for aisle nodes, `PICK_*` / `DROP_*` for operations. |
| `x` | float | X position in meters |
| `y` | float | Y position in meters |
| `type` | string | One of: `charge`, `aisle`, `shelf`, `hub`, `pick`, `drop` |

For advanced maps (like BotValley), nodes may include full pose data with orientation quaternions:

```json
{
  "name": "c1",
  "pose": {
    "position": {"x": 1.71, "y": -1.73, "z": 0.0},
    "orientation": {"x": 0.0, "y": 0.0, "z": 0.978, "w": -0.209}
  },
  "type": "charge",
  "sleepType": "none",
  "turnCost": {"Clockwise": 3.14, "antiClockwise": 3.14}
}
```

### Edge object

Minimal form:
```json
{"from": "DOCK_1", "to": "N_01"}
```

Full form (BotValley style):
```json
{
  "from": "c1|k1_1",
  "to": "c1",
  "name": "c1|k1_1|c1",
  "isUniDirectional": false,
  "useAwake": true,
  "useSleep": true
}
```

| Field | Type | Description |
|-------|------|-------------|
| `from` | string | Source node name |
| `to` | string | Destination node name |
| `name` | string | (optional) Edge identifier |
| `isUniDirectional` | bool | (optional) If true, only traversable from->to. Default: false (bidirectional). |

### Zone object

```json
{
  "name": "Charging",
  "type": "dock",
  "nodes": ["DOCK_1", "DOCK_2"]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Human-readable zone label |
| `type` | string | Zone category: `dock`, `shelf`, `ops`, `none` |
| `nodes` | array | Node names belonging to this zone |

## Included Maps

| File | Nodes | Edges | Description |
|------|-------|-------|-------------|
| `simple_grid.json` | 25 | 40 | Minimal 5x5 demo grid. Good for learning and quick tests. |
| `botvalley.json` | 63 | 63 | Production-grade warehouse from BotValley simulation. Real-world topology with corridors, junctions, and charge docks. |

## Creating a Custom Warehouse

1. Copy `simple_grid.json` as your starting template:
   ```bash
   cp configs/warehouses/simple_grid.json configs/warehouses/my_warehouse.json
   ```

2. Edit the nodes array. Every node needs a unique `name`, an `x`/`y` position in meters, and a `type`.

3. Add edges connecting the nodes. Every node should be reachable from at least one other node (no orphans).

4. Group nodes into zones for fleet management logic (charging areas, storage racks, pick/drop stations).

5. Validate your JSON:
   ```bash
   python3 -c "import json; json.load(open('configs/warehouses/my_warehouse.json')); print('OK')"
   ```

6. Reference your map in docker-compose or the FMS config:
   ```bash
   WAREHOUSE=my_warehouse docker compose up
   ```

## Design Tips

- Keep `grid_spacing_m` consistent (2.0m is typical for AMRs).
- Place charge docks at the warehouse perimeter so they don't block traffic.
- Mark intersection nodes as `hub` type for fleet path planning priority.
- Ensure there are at least 2 charge docks per 5 robots.

# Addverb Fleet Presets

Pre-configured robot and warehouse profiles matching Addverb's real product line.

## Robots

### Dynamo AMR (Goods-to-Person)
- **Config:** `configs/robots/addverb_dynamo.yaml`
- **Type:** differential_drive (LiDAR SLAM)
- **Payload:** 1500 kg
- **Max Speed:** 1.5 m/s
- **Acceleration:** 0.2 m/s²
- **Battery:** 2.4 kWh, 1 hour charge
- **Navigation:** 360° LiDAR + reflector backup
- **Docking Precision:** 10 mm
- **Attachment:** Lifter (raise/lower)
- **Behavior Tree:** `configs/behavior_trees/addverb_dynamo.xml` — pick → move → drop cycle with reactive obstacle avoidance and charging fallback

### Veloce ACR (Automated Case-handling Robot)
- **Config:** `configs/robots/addverb_veloce.yaml`
- **Type:** unidirectional (grid-based)
- **Payload:** 240 kg
- **Max Speed:** 1.5 m/s
- **Acceleration:** 0.3 m/s²
- **Battery:** 1.2 kWh, 40 min charge
- **Navigation:** Barcode scanner + IMU on QR code grid
- **Docking Precision:** 5 mm
- **Attachment:** Conveyor top
- **Behavior Tree:** `configs/behavior_trees/addverb_veloce.xml` — grid navigation with barcode verification at each node, conveyor load/unload

### Quadron Shuttle (Pallet Shuttle)
- **Config:** `configs/robots/addverb_quadron.yaml`
- **Type:** unidirectional (rail-guided)
- **Payload:** 50 kg
- **Max Speed:** 4.0 m/s
- **Acceleration:** 0.5 m/s²
- **Battery:** 0.8 kWh, 30 min charge
- **Navigation:** Rail encoder + limit switches
- **Docking Precision:** 2 mm
- **Angular Velocity:** 0.0 (no turning — rail-guided)
- **Behavior Tree:** `configs/behavior_trees/addverb_quadron.xml` — enter lane → navigate to pallet → load → exit lane → deliver

## Warehouse

### Addverb Noida Test Facility
- **Config:** `configs/warehouses/addverb_noida.json`
- **Layout:** 49 nodes (7x7 grid, 3m spacing)
- **Zones:**
  - Inbound: 3 pick stations (west side)
  - Storage: 5 shelf rows (center)
  - Outbound: 3 drop stations (east side)
  - Charging: 4 stations (south corners)
  - Staging: 1 hub (center)
- **Supports:** All 3 robot types simultaneously

## Fleet Manifest

### Mixed Fleet (10 robots)
- **Config:** `configs/fleets/addverb_mixed.json`
- **Composition:** 3 Dynamo (DYN_001-003) + 5 Veloce (VEL_001-005) + 2 Quadron (QDR_001-002)

## Usage

```bash
# Run with Addverb preset
WAREHOUSE_CONFIG=addverb_noida ROBOT_CONFIG=addverb_dynamo docker compose up

# Or use mixed fleet
WAREHOUSE_CONFIG=addverb_noida FLEET_CONFIG=addverb_mixed docker compose up
```

## C++ Integration

All configs verified through actual C++ FMS `Config::loadRobotConfig()` and `Config::loadWarehouseConfig()`:
- 13 gtest tests in `cpp/tests/test_config.cpp` (LoadAddverb* filter)
- Mixed fleet manifest expands to 10 robots with correct per-type speeds
- 398 C++ tests pass (current), 0 failures

## YAML Security

All robot YAML configs are loaded via `yaml-cpp` SafeLoad (C++) and `yaml.safe_load()` (Python). No arbitrary code execution from YAML. Config values are validated:
- Path traversal protection on config names (reject `/`, `\`, `..`; resolve + is_relative_to check)
- Velocities must be positive (max_linear_velocity > 0)
- `yaml.safe_load()` / yaml-cpp SafeLoad prevents arbitrary code execution

# WRIE Simulation System — Build Summary

## What Was Built (7 Items, 4 Waves)

| Item | Wave | What | Files | Tests |
|------|------|------|-------|-------|
| 3 | A | Fault Scheduler | `services/simulation/fault_scheduler.py` + config JSON | 18 |
| 4 | A | Time-Series CSV Export | `app/routes/telemetry_export.py` | 15 |
| 5 | A | Post-Simulation Validator | `services/simulation/validator.py` | 12 |
| 7 | A | Per-Scenario Config Overrides | Modified `scenarios.py` + `scenario_manager.py` | 8 |
| 2 | B | wrie_cli.py Orchestrator | `wrie_cli.py` (3 subcommands) | 9 |
| 1 | C | FMS Bridge + ProtocolV1 TCP | `services/simulation/fms_bridge.py` | 17 |
| 6 | D | Playwright E2E Recorder | `e2e/record_simulation.py` | 6 |
| **TOTAL** | | | **14 new files, 5 modified** | **85** |

## CLI Usage

```bash
# Full simulation workflow
python wrie_cli.py simulate \
    --scenario-name "Stress Test" \
    --warehouse simple_grid \
    --robots differential_drive \
    --duration 120 \
    --num-orders 200 \
    --fault-config configs/faults/factory_stress_test.json \
    --monitor-interval 5 \
    --export-csv output/telemetry.csv \
    --validate \
    --record-video output/sim.mp4

# Validate existing scenario
python wrie_cli.py validate --scenario-id <uuid>

# Export telemetry
python wrie_cli.py export --duration 1h --output output/export.csv
```

## What Works vs What's Approximated

### WORKS (real execution):
- **ProtocolV1 TCP protocol** — Python implementation matches C++ exactly (33 fields, CRC32 via zlib IEEE polynomial)
- **VirtualRobot position updates** — follows A* path node-by-node at configured velocity
- **Fault scheduling** — timed injection from JSON config via daemon thread
- **CSV export** — InfluxDB query with MongoDB fallback, streaming CSV response
- **Post-simulation validation** — KPI thresholds, negative inventory, orphaned tasks
- **Per-scenario config overrides** — different warehouse/robot configs per scenario
- **Video recording** — Playwright screenshots → ffmpeg MP4 assembly

### APPROXIMATED (known limitations):
- **FMS Bridge TCP** — VirtualRobots can connect to C++ FMS, but without the FMS running, `connect()` fails gracefully. The protocol serialization and position logic are fully tested independently.
- **ScenarioRunner** — still uses discrete math estimation (distance/velocity) for task completion times. The FMSBridge provides an alternative real-time path, but requires the C++ FMS to be running.
- **Playwright recording** — requires dashboard serving at the expected URL. Tests use dummy frames + real ffmpeg, not actual browser screenshots.
- **InfluxDB CSV export** — falls back to MongoDB if InfluxDB unavailable. Both paths tested.

### HONEST: What This Doesn't Do
1. The simulation is **not continuous physics** — VirtualRobot updates position via linear interpolation toward nodes, not dynamics simulation
2. The FMS Bridge does NOT replace the C++ 15Hz loop — it feeds data TO the C++ loop for processing
3. Video recording captures screenshots at fps rate — not a smooth screen capture. Motion appears as slideshow at lower fps.
4. The fault scheduler calls the API from a separate thread — timing accuracy is ~100ms (0.1s tick resolution)

## File Inventory

### New Files (14)
```
configs/faults/factory_stress_test.json
python/services/simulation/__init__.py
python/services/simulation/fault_scheduler.py
python/services/simulation/validator.py
python/services/simulation/fms_bridge.py
python/app/routes/telemetry_export.py
python/wrie_cli.py
python/tests/test_fault_scheduler.py
python/tests/test_telemetry_export.py
python/tests/test_validator.py
python/tests/test_scenario_overrides.py
python/tests/test_wrie_cli.py
python/tests/test_fms_bridge.py
e2e/record_simulation.py
e2e/tests/test_recorder.py
```

### Modified Files (5)
```
python/app/main.py — telemetry_export router added
python/app/routes/scenarios.py — 3 override fields + path traversal validator
python/wes/scenario_manager.py — loads override configs in run_scenario()
python/wrie_cli.py — --record-video flag added in Wave D
python/tests/conftest.py — MongoDB auth fix
```

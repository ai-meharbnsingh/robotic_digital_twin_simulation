# CODEX BRUTAL AUDIT

## Scope
Read order honored: `CLAUDE.md` -> `PROJECT_PLAN.md` -> all files in `cpp/`, `python/`, `configs/`, `docker/`, `gazebo/`, `demo/`, `docs/`, `frontend/src/`.

Files audited: **160**

## Verdict
This project is not production-honest yet. Core implementation quality is decent in many modules, but there are severe contract and behavior mismatches that violate your own stated rules (`No faking`, `Blueprint delta = 0`, real behavior trees).

## Category Scores (0-100)
1. DEAD CODE: **72**
2. HARDCODED VALUES: **84**
3. MEMORY SAFETY (C++): **78**
4. THREAD SAFETY (C++): **68**
5. TEST QUALITY: **70**
6. PROTOCOL V1 (33 fields + CRC32): **88**
7. BEHAVIOR TREES (XML ↔ action/condition parity): **25**
8. CONFIG FIDELITY (YAML/JSON vs runtime use): **80**
9. API CONTRACTS (34 endpoints + shape): **52**
10. ARCHITECTURE (docs vs code): **40**
11. DOCKER (build/run reality): **45**
12. REAL vs FAKE checks: **58**

## Overall Score
**59 / 100**

## Critical Findings
- **FAIL** Behavior tree contract is broken for AMR profile.
  - `configs/behavior_trees/default_amr.xml` uses action/condition IDs not registered in C++.
  - Missing actions include `EmergencyStop`, `RotateToHeading`, `LowerLifter`, `RaiseLifter`, `Decelerate`, `RequestReplan`.
  - Missing conditions include `ObstacleInCriticalZone`, `ObstacleInWarningZone`, `HasLifterAttachment`.
  - Evidence:
    - `cpp/src/behavior/ActionNodes.cpp:249-280` registered set
    - `cpp/src/behavior/ConditionNodes.cpp:73-94` registered set
    - `configs/behavior_trees/default_amr.xml:27,29,82,90,92,103,105,117,125,127,149,154`
- **FAIL** BT engine silently converts unknown actions into success.
  - `cpp/src/behavior/BTEngine.cpp:273-276` returns `SUCCESS` for unregistered actions.
  - This masks configuration errors and can fake mission completion.
- **FAIL** Obstacle condition is hardcoded false.
  - `cpp/src/behavior/ConditionNodes.cpp:50` (`return false;`) makes obstacle detection path fake.
- **FAIL** Fleet shutdown bug.
  - `cpp/src/fleet/FleetManager.cpp:76` early-return in `stop()` skips server shutdown when `run()` never set `running_ = true`.
  - Potential resource leak / dangling open server threads.
- **FAIL** Frontend/API contract is inconsistent and currently broken.
  - `frontend/src/App.tsx:33` calls `/api/health` but backend exposes `/health`.
  - `frontend/src/App.tsx:35` calls `/api/sg/predictions` but backend exposes `/api/analytics/predictions`.
  - `frontend/src/App.tsx:63` expects `status === 'ok'`; backend returns `healthy|degraded` (`python/app/main.py:280`).
  - `frontend/src/App.tsx:100` expects `health.fms_ok`, not returned by backend health schema.
- **FAIL** Dockerfile has invalid `COPY` semantics.
  - `docker/Dockerfile:78` uses shell redirection/`|| true` in `COPY`; Docker `COPY` is not shell-executed.

## High Findings
- **ISSUE** Docs claim modules that do not exist (`MongoDBWriter`).
  - `docs/ARCHITECTURE.md:22,74`
  - `PROJECT_PLAN.md:48,89`
- **ISSUE** `fms_server` signal handler is not async-signal-safe and uses global raw pointer.
  - `cpp/src/apps/fms_server.cpp:35,37-41` calls logging and object methods from signal handler.
- **ISSUE** Compose RabbitMQ env wiring mismatches Python settings model.
  - `docker/docker-compose.yml:35-38` defines host/port/user/pass vars, but app reads `rabbitmq_url` (`python/app/config.py:34`).
- **ISSUE** Weak tests exist (`is not None`, trivial truth).
  - `python/tests/test_wes.py:180`
  - `cpp/tests/test_hello.cpp:4`
  - Several Gazebo tests use presence assertions as primary checks in portions of suite.
- **ISSUE** Protocol comment map is inconsistent and misleading (implementation/tests appear correct).
  - `cpp/include/rdt/network/ProtocolV1.h:33-40`

## File-by-File Audit
Format: `PASS` | `ISSUE(line: reason)` | `FAIL(line: reason)`

| File | Status |
|---|---|
| `/PROJECT_PLAN.md` | ISSUE(26,48,89: stale/inaccurate architecture claims incl. MongoDBWriter + drifting totals) |
| `/CLAUDE.md` | ISSUE(34,50: rules demand no weak assertions, but repo contains weak assertions) |
| `/demo/cold_start_demo.py` | PASS |
| `/demo/fleet_demo.py` | PASS |
| `/docs/USER_EXPERIENCE.md` | PASS |
| `/docs/CONFIGURATION.md` | PASS |
| `/docs/GETTING_STARTED.md` | PASS |
| `/docs/API_REFERENCE.md` | PASS |
| `/docs/ARCHITECTURE.md` | ISSUE(22,74: MongoDBWriter shown in architecture/dataflow but missing in codebase) |
| `/docker/start.sh` | PASS |
| `/docker/docker-compose.yml` | ISSUE(35-38: RabbitMQ env vars don't map to app settings.rabbitmq_url) |
| `/docker/Dockerfile` | FAIL(78: invalid COPY syntax attempting shell redirection/conditional) |
| `/configs/README.md` | PASS |
| `/configs/behavior_trees/default_agv.xml` | PASS |
| `/configs/behavior_trees/default_amr.xml` | FAIL(27,29,82,90,92,103,105,117,125,127,149,154: action/condition IDs do not match registered C++ nodes) |
| `/gazebo/scripts/generate_robot.py` | PASS |
| `/gazebo/scripts/generate_world.py` | PASS |
| `/gazebo/launch.py` | PASS |
| `/python/monitoring/redis_cache.py` | PASS |
| `/frontend/src/hooks/useApi.ts` | PASS |
| `/gazebo/tests/test_world_gen.py` | ISSUE(84,106,109,142,145,155,162,217,220,259: several existence-only assertions lower depth) |
| `/gazebo/tests/__init__.py` | PASS |
| `/gazebo/tests/test_robot_gen.py` | ISSUE(81,87,93,113,131,163,175,186,199,210,221,240,245,266,291,293: many structure-presence assertions; partial depth) |
| `/python/monitoring/__init__.py` | PASS |
| `/python/monitoring/influx_writer.py` | PASS |
| `/frontend/src/hooks/useFleetWebSocket.ts` | PASS |
| `/frontend/src/vite-env.d.ts` | PASS |
| `/configs/warehouses/README.md` | PASS |
| `/configs/robots/differential_drive.yaml` | PASS |
| `/configs/warehouses/simple_grid.json` | PASS |
| `/configs/warehouses/botvalley.json` | PASS |
| `/configs/robots/unidirectional.yaml` | PASS |
| `/configs/robots/README.md` | PASS |
| `/python/requirements.txt` | PASS |
| `/python/pytest.ini` | PASS |
| `/cpp/src/apps/fms_server.cpp` | ISSUE(35,37-41: global raw pointer + non-async-signal-safe calls in signal handler) |
| `/gazebo/models/diffdrive_amr/model.config` | PASS |
| `/gazebo/models/diffdrive_amr/model.sdf` | PASS |
| `/python/wes/kpi_tracker.py` | PASS |
| `/python/wes/order_generator.py` | PASS |
| `/python/wes/task_generator.py` | PASS |
| `/python/wes/__init__.py` | PASS |
| `/frontend/src/components/RobotStatusPanel.tsx` | PASS |
| `/frontend/src/components/SGPredictions.tsx` | PASS |
| `/frontend/src/components/WarehouseGrid.tsx` | PASS |
| `/frontend/src/components/IoGitaZones.tsx` | PASS |
| `/frontend/src/components/BatteryLevels.tsx` | PASS |
| `/frontend/src/components/TaskQueue.tsx` | PASS |
| `/frontend/src/types.ts` | ISSUE(120-121: expects health fields not returned by backend) |
| `/frontend/src/index.css` | PASS |
| `/frontend/src/main.tsx` | PASS |
| `/frontend/src/App.tsx` | FAIL(33,35,63,100: wrong endpoint paths and health-schema assumptions vs backend) |
| `/gazebo/plugins/lidar_sensor.cpp` | PASS |
| `/cpp/src/fleet/FleetManager.cpp` | FAIL(76: stop() early-return can skip TCP/REST shutdown when run() not entered) |
| `/cpp/src/fleet/TaskManager.cpp` | PASS |
| `/cpp/src/fleet/COPPController.cpp` | PASS |
| `/gazebo/plugins/barcode_sensor.cpp` | PASS |
| `/gazebo/plugins/CMakeLists.txt` | PASS |
| `/gazebo/models/uni_agv/model.config` | PASS |
| `/gazebo/models/uni_agv/model.sdf` | PASS |
| `/python/app/__init__.py` | PASS |
| `/python/app/models.py` | PASS |
| `/python/app/config.py` | PASS |
| `/gazebo/worlds/botvalley.sdf` | PASS |
| `/python/app/websocket.py` | PASS |
| `/python/intelligence/iogita/cold_start.py` | PASS |
| `/gazebo/worlds/simple_5x5_grid.sdf` | PASS |
| `/python/tests/test_wes.py` | ISSUE(180: weak assertion only checks non-None) |
| `/python/tests/test_api.py` | PASS |
| `/python/tests/test_integration.py` | PASS |
| `/python/tests/test_health.py` | PASS |
| `/python/tests/test_config.py` | PASS |
| `/python/tests/test_iogita.py` | PASS |
| `/python/tests/__init__.py` | PASS |
| `/python/tests/test_sg.py` | PASS |
| `/python/tests/conftest.py` | PASS |
| `/python/tests/test_iogita_accuracy.py` | PASS |
| `/python/app/main.py` | PASS |
| `/python/intelligence/iogita/zone_identifier.py` | PASS |
| `/python/intelligence/__init__.py` | PASS |
| `/python/intelligence/iogita/__init__.py` | PASS |
| `/python/intelligence/iogita/fleet_atlas.py` | PASS |
| `/python/intelligence/sg_prediction/bottleneck_predictor.py` | PASS |
| `/cpp/src/robot/BatteryModel.cpp` | PASS |
| `/cpp/src/robot/MotionController.cpp` | PASS |
| `/cpp/src/robot/RobotState.cpp` | PASS |
| `/cpp/src/robot/ObstacleHandler.cpp` | PASS |
| `/python/intelligence/sg_prediction/state_encoder.py` | PASS |
| `/python/intelligence/sg_prediction/sg_engine.py` | PASS |
| `/python/intelligence/sg_prediction/__init__.py` | PASS |
| `/python/app/routes/reservations.py` | PASS |
| `/python/app/routes/robots.py` | PASS |
| `/python/app/routes/analytics.py` | ISSUE(18-20: _get_sg_engine appears unused/dead helper) |
| `/python/app/routes/wes.py` | PASS |
| `/python/app/routes/stats.py` | PASS |
| `/python/app/routes/wcs.py` | PASS |
| `/python/app/routes/telemetry.py` | PASS |
| `/python/app/routes/__init__.py` | PASS |
| `/python/app/routes/config_routes.py` | PASS |
| `/python/app/routes/events.py` | PASS |
| `/python/app/routes/fleet.py` | PASS |
| `/cpp/src/behavior/ConditionNodes.cpp` | FAIL(50: obstacle condition hardcoded false) |
| `/python/app/routes/tasks.py` | PASS |
| `/cpp/src/behavior/BTEngine.cpp` | FAIL(273-276: unknown action treated as SUCCESS; hides config errors) |
| `/python/app/routes/maps.py` | PASS |
| `/cpp/src/behavior/ActionNodes.cpp` | PASS |
| `/python/app/routes/iogita.py` | PASS |
| `/python/app/routes/simulation.py` | PASS |
| `/cpp/CMakeLists.txt` | PASS |
| `/cpp/src/core/Logger.cpp` | PASS |
| `/cpp/src/navigation/AStar.cpp` | PASS |
| `/cpp/src/core/Config.cpp` | PASS |
| `/cpp/src/core/Timer.cpp` | PASS |
| `/cpp/tests/CMakeLists.txt` | PASS |
| `/cpp/tests/test_bt.cpp` | PASS |
| `/cpp/tests/test_fleet.cpp` | PASS |
| `/cpp/src/navigation/GraphMap.cpp` | PASS |
| `/cpp/src/navigation/NodeReservation.cpp` | PASS |
| `/cpp/src/navigation/QuadTree.cpp` | PASS |
| `/cpp/tests/test_astar.cpp` | PASS |
| `/cpp/tests/test_motion.cpp` | PASS |
| `/cpp/tests/test_protocol.cpp` | PASS |
| `/cpp/tests/test_tcp.cpp` | PASS |
| `/cpp/tests/test_hello.cpp` | ISSUE(4: trivial EXPECT_TRUE(true) no behavior verification) |
| `/cpp/tests/test_logger.cpp` | PASS |
| `/cpp/tests/test_graph.cpp` | PASS |
| `/cpp/tests/test_timer.cpp` | PASS |
| `/cpp/tests/test_robot_state.cpp` | PASS |
| `/cpp/tests/test_obstacle.cpp` | PASS |
| `/cpp/tests/test_reservation.cpp` | PASS |
| `/cpp/tests/test_types.cpp` | PASS |
| `/cpp/tests/test_config.cpp` | PASS |
| `/cpp/tests/test_rest.cpp` | PASS |
| `/cpp/tests/test_battery.cpp` | PASS |
| `/cpp/tests/test_quadtree.cpp` | PASS |
| `/cpp/src/network/ProtocolV1.cpp` | PASS |
| `/cpp/src/network/RESTServer.cpp` | PASS |
| `/cpp/src/network/TCPServer.cpp` | PASS |
| `/cpp/include/rdt/version.h` | PASS |
| `/cpp/include/rdt/behavior/BTEngine.h` | PASS |
| `/cpp/include/rdt/behavior/ActionNodes.h` | PASS |
| `/cpp/include/rdt/behavior/ConditionNodes.h` | PASS |
| `/cpp/include/rdt/navigation/NodeReservation.h` | PASS |
| `/cpp/include/rdt/fleet/COPPController.h` | PASS |
| `/cpp/include/rdt/fleet/FleetManager.h` | PASS |
| `/cpp/include/rdt/fleet/TaskManager.h` | PASS |
| `/cpp/include/rdt/navigation/QuadTree.h` | PASS |
| `/cpp/include/rdt/navigation/GraphMap.h` | PASS |
| `/cpp/include/rdt/navigation/AStar.h` | PASS |
| `/cpp/include/rdt/core/Logger.h` | PASS |
| `/cpp/include/rdt/robot/MotionController.h` | PASS |
| `/cpp/include/rdt/core/Timer.h` | PASS |
| `/cpp/include/rdt/core/Types.h` | PASS |
| `/cpp/include/rdt/core/Config.h` | PASS |
| `/cpp/include/rdt/network/RESTServer.h` | PASS |
| `/cpp/include/rdt/network/ProtocolV1.h` | ISSUE(33-40: field index comments inconsistent with declared layout; integration risk) |
| `/cpp/include/rdt/network/TCPServer.h` | PASS |
| `/cpp/include/rdt/robot/RobotState.h` | PASS |
| `/cpp/include/rdt/robot/BatteryModel.h` | PASS |
| `/cpp/include/rdt/robot/ObstacleHandler.h` | PASS |

## Checklist Mapping
1. DEAD CODE: one confirmed dead helper (`python/app/routes/analytics.py:_get_sg_engine`), plus low-value stubs/tests.
2. HARDCODED VALUES: mostly good; config-driven design is largely respected.
3. MEMORY SAFETY: mostly RAII/`unique_ptr`; no obvious raw heap misuse; signal global pointer is still a safety smell.
4. THREAD SAFETY: broad mutex coverage, but shutdown sequencing bug and signal-handler behavior are real risks.
5. TEST QUALITY: strong in many modules, but weak assertion pockets exist.
6. PROTOCOL V1: implementation/tests largely consistent; header index commentary drift is a doc hazard.
7. BEHAVIOR TREES: AMR XML to C++ registry mismatch is severe and currently invalidates AMR logic.
8. CONFIG FIDELITY: generally strong for robot/world generation and C++ config loaders.
9. API CONTRACTS: backend endpoint count is 34, but frontend contracts drift from backend paths/shapes.
10. ARCHITECTURE: docs claim components/dataflow not implemented (notably MongoDBWriter in C++).
11. DOCKER: Dockerfile has an invalid command pattern; compose env wiring partially mismatched.
12. REAL vs FAKE: health probes are real; obstacle condition fake and BT unknown-action-success behavior undermines realism.

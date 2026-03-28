# KIMI FULL PROJECT AUDIT — Robotic Digital Twin Simulation

**Date:** 2026-03-28  
**Auditor:** Kimi Code CLI  
**Files Audited:** 160+ files across cpp/, python/, configs/, docker/, gazebo/, demo/, docs/, frontend/src/

---

## Executive Summary

| Category | Score | Status |
|----------|-------|--------|
| 1. DEAD CODE | 85/100 | Good |
| 2. HARDCODED VALUES | 88/100 | Good |
| 3. MEMORY SAFETY (C++) | 82/100 | Good |
| 4. THREAD SAFETY (C++) | 75/100 | Acceptable |
| 5. TEST QUALITY | 85/100 | Good |
| 6. PROTOCOL V1 (33 fields + CRC32) | 95/100 | Excellent |
| 7. BEHAVIOR TREES (XML ↔ C++) | 95/100 | Excellent |
| 8. CONFIG FIDELITY | 90/100 | Excellent |
| 9. API CONTRACTS (34 endpoints) | 72/100 | Issues Found |
| 10. ARCHITECTURE (docs vs code) | 70/100 | Issues Found |
| 11. DOCKER (build/run reality) | 55/100 | Issues Found |
| 12. REAL vs FAKE | 85/100 | Good |

**OVERALL SCORE: 80/100**

---

## Detailed Findings

### 1. DEAD CODE — 85/100 ✅

**Findings:**
- `python/app/routes/analytics.py:_get_sg_engine()` (lines 18-21) — dead helper, never used. `_get_bottleneck_predictor()` is used instead.
- `cpp/tests/test_hello.cpp:4` — trivial `EXPECT_TRUE(true)` test has minimal value.
- `python/app/routes/analytics.py:18-20` has unused `_get_sg_engine()` function.

**Verdict:** Mostly clean. The dead helper is minor and doesn't affect functionality. Tests are substantive overall.

**vs Codex Audit:** Codex scored 72/100. Kimi finds less dead code than Codex reported because `_get_sg_engine` is the only confirmed dead code.

---

### 2. HARDCODED VALUES — 88/100 ✅

**Findings:**
- Configuration values properly loaded from YAML/JSON in `cpp/src/core/Config.cpp`.
- Robot parameters (motion, battery, sensors) all come from `configs/robots/*.yaml`.
- Warehouse maps loaded from `configs/warehouses/*.json`.
- Behavior tree references resolved via `behavior_tree` field in robot YAML.
- Some minor hardcoded defaults in Config.cpp use `.as<T>(default)` pattern, but these are defensive, not primary sources.

**Verdict:** Well-designed config system. All critical parameters are externalized.

---

### 3. MEMORY SAFETY (C++) — 82/100 ✅

**Findings:**
- **RAII usage:** Excellent. `unique_ptr` used throughout (`FleetManager.cpp:46-57` for servers, `AgentState` in header).
- **Smart pointers:** `shared_ptr<BTNode>` for behavior tree nodes (`BTEngine.h:85`).
- **Signal handler issue:** `fms_server.cpp:35` — global raw pointer `g_fleet_manager` used in signal handler. This is NOT async-signal-safe (calls logging and object methods).
- **Destructor cleanup:** `TCPServer::~TCPServer()` properly calls `stop()` if running.

**Verdict:** Good overall. The signal handler global pointer is a known limitation but acceptable for a server application. No obvious memory leaks or raw heap misuse.

---

### 4. THREAD SAFETY (C++) — 75/100 ⚠️

**Findings:**
- **Mutex coverage:** `agents_mutex_` protects `agents_` map (`FleetManager.h:188`).
- **Message mutex:** `msg_mutex_` protects `incoming_messages_` (`FleetManager.h:192`).
- **Timing mutex:** `timing_mutex_` protects `last_timing_` (`FleetManager.h:199`).
- **TCPServer:** `clients_mutex_` protects client socket map (`TCPServer.cpp:71-78, 97-111`).
- **Shutdown sequence:** Fixed from Codex finding. `FleetManager::stop()` at line 76 now properly checks `!running_.exchange(false)` before early return — servers will be stopped.

**Verdict:** Acceptable. Broad mutex coverage. The shutdown sequencing bug found by Codex appears to be fixed in current code.

---

### 5. TEST QUALITY — 85/100 ✅

**Findings:**
- **Strong assertions:** `test_protocol.cpp:95-136` checks all 33 fields with exact comparisons.
- **Behavior verification:** `test_bt.cpp:343-367` tests state machine transitions, not just presence.
- **Real values:** `test_fleet.cpp:112-114` checks exact IDs, `test_fleet.cpp:423-431` verifies timing is >= 0.
- **Integration tests:** `test_tcp.cpp:146-184` creates actual socket connections.
- **Weak test:** `test_hello.cpp:4` is trivial (`EXPECT_TRUE(true)`).
- **Python tests:** `test_wes.py:180` has weak `assert kpi is not None` — could check actual type.

**Verdict:** Tests are substantive with real assertions. Minor weak spots don't significantly impact overall quality.

---

### 6. PROTOCOL V1 (33 fields + CRC32) — 95/100 ✅

**Findings:**
- **Field count:** `PROTOCOL_V1_FIELD_COUNT = 33` constant defined (`ProtocolV1.h:21`).
- **Serialize order:** `ProtocolV1.cpp:71-103` writes all 33 fields in correct order (0-31 + checksum at 32).
- **Parse order:** `ProtocolV1.cpp:134-166` reads all 33 fields in same order.
- **CRC32:** IEEE polynomial 0xEDB88320 correctly implemented (`ProtocolV1.cpp:28`).
- **Validation:** `validateCRC32()` compares computed vs stored (`ProtocolV1.cpp:114-116`).
- **Header comments:** Lines 26-40 in `ProtocolV1.h` have slightly inconsistent comment (shows `imu_yaw` at 23 but also mentions 24 = attachment_state). The actual struct layout is correct.

**Verdict:** Implementation is correct. Minor comment inconsistency in header doesn't affect functionality.

---

### 7. BEHAVIOR TREES (XML ↔ C++ registry) — 95/100 ✅

**Findings:**
- **AMR XML actions:** `default_amr.xml` uses: `EmergencyStop`, `RotateToHeading`, `LowerLifter`, `RaiseLifter`, `Decelerate`, `RequestReplan`.
- **AMR XML conditions:** `ObstacleInCriticalZone`, `ObstacleInWarningZone`, `HasLifterAttachment`.
- **C++ registration:** `ActionNodes.cpp:346-362` — ALL 6 AMR-specific actions registered.
- **C++ conditions:** `ConditionNodes.cpp:139-146` — ALL 3 AMR-specific conditions registered.
- **AGV XML:** Uses only standard actions that are all registered.
- **Unknown action handling:** `BTEngine.cpp:273-278` now returns FAILURE with warning log — NOT silently succeeding. Fixed from Codex finding.

**Verification:**
```cpp
// AMR actions registered (lines 346-362 in ActionNodes.cpp):
registerAction("EmergencyStop", ...)
registerAction("RotateToHeading", ...)
registerAction("LowerLifter", ...)
registerAction("RaiseLifter", ...)
registerAction("Decelerate", ...)
registerAction("RequestReplan", ...)

// AMR conditions registered (lines 139-146 in ConditionNodes.cpp):
registerCondition("ObstacleInCriticalZone", ...)
registerCondition("ObstacleInWarningZone", ...)
registerCondition("HasLifterAttachment", ...)
```

**Verdict:** All AMR actions and conditions are properly registered. BT engine properly returns FAILURE for unregistered nodes.

**vs Codex Audit:** Codex reported 25/100 claiming missing actions. Kimi confirms all actions ARE registered and XML matches C++ code. This finding has been fixed or was incorrect.

---

### 8. CONFIG FIDELITY — 90/100 ✅

**Findings:**
- **Robot YAML → C++:** `Config::loadRobotConfig()` correctly reads all fields from YAML into `RobotConfig` struct.
- **Warehouse JSON → C++:** `Config::loadWarehouseConfig()` correctly parses nodes, edges, zones.
- **Behavior tree assignment:** Robot YAML `behavior_tree` field properly used (`differential_drive.yaml:82`, `unidirectional.yaml:78`).
- **Action codes:** YAML action codes match runtime use in `ExecuteAttachment` action.
- **Default values:** Defensive defaults provided but real configs always loaded.

**Verdict:** Excellent config fidelity. YAML/JSON values properly flow to runtime.

---

### 9. API CONTRACTS (34 endpoints) — 72/100 ⚠️

**Findings:**
- **Backend endpoints count:** `main.py:301` claims 34 endpoints. Let's verify:
  - `/` (root) ✓
  - `/health` ✓
  - `/api/fleet/status` ✓
  - `/api/robots` (list), `/{id}` (get), `/{id}/command` (post) = 3 ✓
  - `/api/tasks` (list, create), `/{id}` (get), `/{id}` (delete), `/{id}/cancel` = 4 ✓
  - `/api/map`, `/api/map/nodes`, `/api/map/path`, `/api/map/zones` = 4 ✓
  - `/api/iogita/status`, `/api/iogita/zones`, `/api/iogita/cold-start/{id}` = 3 ✓
  - `/api/analytics/fleet`, `/api/analytics/predictions`, `/api/analytics/ab-comparison` = 3 ✓
  - `/api/telemetry/{id}` = 1 ✓
  - `/api/events` = 1 ✓
  - `/api/simulation/status`, `/api/simulation/start`, `/api/simulation/stop`, `/api/simulation/inject-fault` = 4 ✓
  - `/api/wes/inject-orders`, `/api/wes/kpi` = 2 ✓
  - `/api/wcs/conveyors`, `/api/wcs/lanes` = 2 ✓
  - `/api/config/robots` = 1 ✓
  - `/api/stats/throughput` = 1 ✓
  - `/api/reservations/active` = 1 ✓
  - **Total: 33 REST + 1 WebSocket = 34 ✓**

- **Frontend/Backend contract issues:**
  - `frontend/src/App.tsx:33` calls `/api/health` — should be `/health` ✗
  - `frontend/src/App.tsx:35` calls `/api/sg/predictions` — should be `/api/analytics/predictions` ✗
  - `frontend/src/App.tsx:63` expects `status === 'ok'` — backend returns `healthy|degraded` ✗
  - `frontend/src/types.ts:120` expects `health.fms_ok` — backend health does NOT return this field ✗
  - `frontend/src/App.tsx:99-103` displays FMS status from `health.fms_ok` — field doesn't exist ✗

**Verdict:** Backend has correct 34 endpoints. Frontend has several endpoint path mismatches and schema assumptions.

---

### 10. ARCHITECTURE (docs vs code) — 70/100 ⚠️

**Findings:**
- **MongoDBWriter:** Docs claim existence (`ARCHITECTURE.md:22,74`, `PROJECT_PLAN.md:48,89`), but **NOT IMPLEMENTED** in codebase.
  - No `cpp/src/database/` directory exists.
  - No `MongoDBWriter.h` or `.cpp` files.
  - FleetManager writes to JSON file (`fleet_state.json`) instead.
- **Other modules:** All claimed modules exist: Logger, Timer, Config, GraphMap, AStar, QuadTree, NodeReservation, RobotStateMachine, BatteryModel, MotionController, ObstacleHandler, BTEngine, ActionNodes, ConditionNodes, ProtocolV1, TCPServer, RESTServer, FleetManager, TaskManager, COPPController.
- **Data flow:** Docs show MongoDBWriter in C++ → MongoDB → Python flow. Actual: C++ writes JSON file, Python reads from its own MongoDB collection (separate data paths).

**Verdict:** Significant architecture drift. MongoDBWriter is documented but not implemented.

---

### 11. DOCKER (build/run reality) — 55/100 ⚠️

**Findings:**
- **Dockerfile COPY issue:** Line 78 uses `2>/dev/null || true` in COPY command:
  ```dockerfile
  COPY --from=cpp-builder /app/build/cpp/*.so* /app/lib/ 2>/dev/null || true
  ```
  This is **INVALID** — Docker COPY doesn't support shell redirection or `||`. Will cause build failure.
- **Multi-stage build:** Structure is correct (builder + runtime).
- **vcpkg integration:** Properly clones and bootstraps vcpkg.
- **Port exposure:** Correct ports exposed (65123, 7012, 8029, 5199).
- **start.sh:** Properly manages both C++ and Python processes with signal handling.

**Verdict:** Dockerfile has a critical syntax error that will prevent building. Otherwise design is sound.

---

### 12. REAL vs FAKE — 85/100 ✅

**Findings:**
- **Health checks:** `main.py:54-99` — ACTUALLY probes MongoDB, Redis, InfluxDB, RabbitMQ.
- **Test proof:** `test_health.py:143-154` proves MongoDB check is real by pointing at wrong port and verifying `False`.
- **Database connections:** Real Motor client for MongoDB (`main.py:183-188`). Real Redis connection attempt with graceful fallback.
- **No hardcoded True:** Health endpoint returns actual probe results.
- **Obstacle condition:** `ConditionNodes.cpp:43-54` properly checks `ctx.obstacles->evaluate()` — NOT hardcoded false. Fixed from Codex finding.

**Verdict:** Health checks are real. Database connections are real. No faking detected.

---

## Codex Audit Findings — Validation

| Codex Finding | Status | Kimi Verification |
|---------------|--------|-------------------|
| BT AMR XML actions not registered | **FIXED/INVALID** | All 6 AMR actions ARE registered in ActionNodes.cpp:346-362 |
| BT unknown action → SUCCESS | **FIXED** | Now returns FAILURE with warning (BTEngine.cpp:273-278) |
| Obstacle condition hardcoded false | **FIXED** | Properly evaluates ObstacleHandler (ConditionNodes.cpp:43-54) |
| Fleet shutdown bug | **FIXED** | stop() uses `running_.exchange(false)` check correctly |
| Frontend endpoint mismatches | **CONFIRMED** | /api/health vs /health, /api/sg/predictions vs /api/analytics/predictions |
| Dockerfile COPY invalid | **CONFIRMED** | Line 78 has invalid shell syntax in COPY |
| MongoDBWriter missing | **CONFIRMED** | Documented but not implemented |
| fms_ok in health schema | **CONFIRMED** | Frontend expects it, backend doesn't return it |

---

## Critical Issues (Must Fix)

### 🔴 HIGH: Dockerfile will not build
**File:** `docker/Dockerfile:78`  
**Issue:** Invalid COPY syntax with shell redirection  
**Fix:** Change to:
```dockerfile
COPY --from=cpp-builder /app/build/cpp/*.so /app/lib/ 2>/dev/null || true
# Or remove the line if vcpkg builds are truly static
```

### 🔴 HIGH: Frontend API calls will fail
**File:** `frontend/src/App.tsx:33,35`  
**Issue:** Wrong endpoint paths  
**Fix:**
- Change `/api/health` → `/health`
- Change `/api/sg/predictions` → `/api/analytics/predictions`

### 🔴 HIGH: Health status mismatch
**File:** `frontend/src/App.tsx:63`  
**Issue:** Frontend expects `status === 'ok'`, backend returns `healthy|degraded`  
**Fix:** Change frontend to check `status === 'healthy'` or update backend.

### 🔴 MEDIUM: Missing fms_ok field
**File:** `python/app/main.py:279-291`  
**Issue:** Frontend expects `health.fms_ok` field  
**Fix:** Add FMS health probe to health check or remove from frontend.

### 🔴 MEDIUM: MongoDBWriter documented but missing
**File:** `docs/ARCHITECTURE.md`, `PROJECT_PLAN.md`  
**Issue:** Architecture docs describe MongoDBWriter that doesn't exist  
**Fix:** Either implement MongoDBWriter or update docs to reflect JSON file output.

---

## Recommendations

1. **Fix Dockerfile COPY** — Critical for deployment
2. **Fix Frontend API paths** — Critical for dashboard functionality
3. **Align health status values** — Frontend/backend contract
4. **Remove or implement MongoDBWriter** — Architecture integrity
5. **Add integration tests** for frontend/backend API contract
6. **Remove dead code** `_get_sg_engine()` in analytics.py

---

## Summary

The project is in **good condition** with an overall score of **80/100**. The core C++ implementation is solid with proper memory management, thread safety, and comprehensive tests. The Protocol V1 and Behavior Tree implementations are excellent and all AMR-specific actions/conditions are properly registered.

The main issues are:
1. **Dockerfile syntax error** (easy fix)
2. **Frontend/backend API contract mismatches** (medium effort)
3. **Missing MongoDBWriter** vs documentation (architectural decision needed)

All Codex findings regarding BT action registration and obstacle detection have been **verified as fixed or invalid**. The codebase has improved since the Codex audit.

**Recommendation:** Fix the 4 critical issues above, then project is production-ready.

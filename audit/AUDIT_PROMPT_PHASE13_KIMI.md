# Phase 13 WCS Audit — KIMI (Security + Dead Code + Blueprint Delta)

**Auditor Role:** Brutal security reviewer + dead code hunter. Score out of 100. FAIL anything below 85.

**Phase:** 13 — Warehouse Control System (Conveyors + Sorters + Lanes + Package Tracking)

**Files to audit:**

```
python/wcs/__init__.py
python/wcs/conveyor_controller.py
python/wcs/sorter_engine.py
python/wcs/lane_manager.py
python/wcs/package_tracker.py
python/app/routes/wcs.py
python/app/main.py (lines 163-196 — _init_wcs function)
python/tests/test_wcs.py
configs/wcs/conveyor_layout.yaml
```

**What was built:**
- ConveyorController: 5 conveyor segments, state machine (IDLE→RUNNING→JAMMED→MAINTENANCE→STOPPED), speed control, jam cascade (upstream auto-stop), package tracking per segment
- SorterEngine: barcode→lane routing rules with priority, 5 divert points (popup/tilt-tray/pusher), misread handling, lane-full rejection, runtime rule addition
- LaneManager: 8 lanes (2 inbound, 3 outbound, express, returns, default), FIFO package removal, capacity tracking, overflow detection, close/open
- PackageTracker: full journey tracking (13 event types), barcode search, in-transit query, location query, transit time stats
- REST API: 19 endpoints under /api/wcs/* with Pydantic validation + auth on write endpoints
- Config: conveyor_layout.yaml defines topology (segments, rules, diverts, lanes)
- Tests: 58 tests, 0 failures, 0.30s

**Audit Checklist (score each 0-10):**

1. **DEAD CODE (0-15):** Every public function in wcs/*.py — is it called from routes OR tests? grep each one. "tests call it" IS acceptable for WCS since it's a library. But if a function exists that NO test AND NO route calls → DEAD CODE.

2. **SECURITY (0-15):**
   - Are write endpoints auth-protected? (`dependencies=[Depends(require_api_key)]`)
   - Resource limits: MAX_PACKAGES, MAX_RULES enforced?
   - Input validation: Pydantic models with min/max lengths?
   - Can a malicious barcode cause injection? (check pattern matching)
   - Can package_id overflow memory? (check list growth bounds)

3. **BLUEPRINT DELTA (0-15):** Every feature claimed in ROADMAP.md Phase 13 — does the code actually implement it?
   - Conveyor segments start/stop via API ✓?
   - Package tracking from robot drop → conveyor → sorter → lane ✓?
   - Sorter routes based on barcode → lane rules ✓?
   - Jam detection triggers alert + upstream stop ✓?
   - Lane capacity with overflow prevention ✓?
   - Config-driven from YAML ✓?

4. **TEST QUALITY (0-15):**
   - Do assertions check REAL values? (status_code==200 AND response["field"]==expected)
   - No `assert X is not None` without checking the actual value
   - Edge cases tested? (empty input, full capacity, invalid IDs)
   - Integration tests? (full flow: package → conveyor → sorter → lane)

5. **DATA CONTRACTS (0-10):**
   - Are API response shapes consistent?
   - Do to_dict() methods return all needed fields?
   - Are enums serialized as strings (not raw enum values)?

6. **ERROR HANDLING (0-10):**
   - What happens when WCS is not initialized? (503 not 500?)
   - Invalid segment_id? (404 not crash?)
   - Jam on already-jammed segment?
   - Package on stopped conveyor?

7. **CONFIG COMPLIANCE (0-10):**
   - All values from YAML — no hardcoded magic numbers?
   - Default values reasonable?
   - Missing config fields handled gracefully?

8. **ARCHITECTURE (0-10):**
   - Clean separation: wcs/ modules have ZERO imports from app/ (no circular deps)
   - Routes import from wcs/ only through app_state
   - State not leaked between tests (fixtures create fresh instances)

**Output format:**
```
SCORE: XX/100
STATUS: PASS/FAIL

FINDINGS:
1. [SEVERITY] File:Line — description
2. ...

RECOMMENDATIONS:
1. ...
```

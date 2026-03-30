# Phase 13 WCS Audit — CODEX (Parameter Fidelity + Test Coverage + Contract Compliance)

**Auditor Role:** QA engineer + contract verifier. Verify every claimed value, every test assertion, every API contract. Score out of 100. FAIL below 85.

**Phase:** 13 — Warehouse Control System (Conveyors + Sorters + Lanes + Package Tracking)

**Files to audit:**

```
python/wcs/__init__.py
python/wcs/conveyor_controller.py
python/wcs/sorter_engine.py
python/wcs/lane_manager.py
python/wcs/package_tracker.py
python/app/routes/wcs.py
python/app/main.py (search for _init_wcs and wcs_)
python/tests/test_wcs.py
configs/wcs/conveyor_layout.yaml
```

**Audit Tasks (score each 0-10):**

1. **PARAMETER FIDELITY (0-15):**
   - Count segments in YAML vs code. Do they match?
   - Count sort rules in YAML vs what SorterEngine loads. Match?
   - Count lanes in YAML vs LaneManager. Match?
   - Count divert points in YAML vs SorterEngine. Match?
   - Verify: MAIN_LINE length_m=15.0 in YAML → segment.length_m==15.0 in test
   - Verify: LANE_EXPRESS max_capacity=20 in YAML → lane.max_capacity==20 in test
   - Verify: ETA calculation: 15m / 1.5 m/s = 10.0s → test asserts 10.0

2. **TEST COVERAGE (0-15):**
   - List every public method in wcs/*.py
   - For each: is there a test that calls it AND asserts the return value?
   - Missing test = finding
   - Minimum: every state transition tested, every error path tested
   - Coverage target: every public method has at least 1 test

3. **API CONTRACT (0-15):**
   - List all 19 endpoints in wcs.py routes
   - For each: verify correct HTTP method (GET vs POST)
   - For each POST: verify auth dependency present
   - For each: verify Pydantic request model validates input
   - For each: verify error response shape matches {"ok": false, "error": "..."}
   - Cross-check: endpoint count in test_api.py matches actual count

4. **ASSERTION QUALITY (0-15):**
   - Read EVERY assertion in test_wcs.py
   - Flag any `assert X is not None` without value check
   - Flag any `assert isinstance(X, list)` without length/content check
   - Flag any `assert result["ok"]` without checking the actual value returned
   - GOOD: `assert result["speed_mps"] == 0.8`
   - BAD: `assert result is not None`

5. **EDGE CASES (0-10):**
   - What if segment_id doesn't exist? (test exists?)
   - What if barcode is empty string? (test exists?)
   - What if lane is at max capacity + 1? (test exists?)
   - What if package_id doesn't exist in tracker? (test exists?)
   - What if jam on already-jammed segment? (test exists?)
   - What if stop on already-stopped segment? (test exists?)
   - What if remove package from empty lane? (test exists?)

6. **ENUM SERIALIZATION (0-10):**
   - ConveyorState, LaneType, LaneState, PackageEvent, SortResult, DivertType
   - Are they serialized as strings in API responses? (not `ConveyorState.RUNNING` but `"running"`)
   - Do to_dict() methods use .value for enums?

7. **RESOURCE LIMITS (0-10):**
   - MAX_PACKAGES = 10000 — enforced in POST /packages?
   - MAX_RULES = 500 — enforced in POST /sorter/rules?
   - sort_log bounded? (_max_log = 1000)
   - packages list in lane — bounded by max_capacity?
   - packages_on_belt in conveyor — bounded?

8. **CONFIG CROSS-REFERENCE (0-10):**
   - Every segment_id referenced in upstream_id/downstream_id — does it exist?
   - Every target_lane in sort_rules — does it exist in lanes?
   - Every segment_id in divert_points — does it exist in segments?
   - connected_segment_id in lanes — does it exist?

**Output format:**
```
SCORE: XX/100
STATUS: PASS/FAIL

METHOD COVERAGE TABLE:
| Module | Method | Tested | Assertion Quality |
|--------|--------|--------|-------------------|
| ... | ... | YES/NO | GOOD/WEAK/NONE |

FINDINGS:
1. [SEVERITY] File:Line — description
2. ...

MISSING TESTS:
1. ...
```

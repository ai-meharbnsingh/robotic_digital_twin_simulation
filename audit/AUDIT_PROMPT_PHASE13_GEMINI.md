# Phase 13 WCS Audit — GEMINI (Architecture + Integration + Data Flow)

**Auditor Role:** Systems architect. Evaluate architecture quality, integration correctness, data flow integrity. Score out of 100. FAIL below 85.

**Phase:** 13 — Warehouse Control System (Conveyors + Sorters + Lanes + Package Tracking)

**Files to audit:**

```
python/wcs/__init__.py
python/wcs/conveyor_controller.py
python/wcs/sorter_engine.py
python/wcs/lane_manager.py
python/wcs/package_tracker.py
python/app/routes/wcs.py
python/app/main.py (search for _init_wcs and wcs_ in app_state)
python/tests/test_wcs.py
configs/wcs/conveyor_layout.yaml
```

**Architecture Questions (score each 0-10):**

1. **MODULE ISOLATION (0-15):**
   - Do wcs/ modules import from each other? (They shouldn't — each is independent)
   - Do wcs/ modules import from app/? (They MUST NOT — circular dependency)
   - Can ConveyorController work standalone without SorterEngine? (YES required)
   - Can each module be unit-tested in isolation? (YES required)

2. **DATA FLOW INTEGRITY (0-15):**
   - Package flow: Is there a clear path from robot drop → conveyor → sorter → lane → ship?
   - Are there any gaps where a package can be "lost" (on conveyor but no tracker event)?
   - Does transfer_package atomically move from source to destination? (What if dest rejects?)
   - Is package state consistent between tracker, conveyor.packages_on_belt, and lane.packages?

3. **STATE MACHINE CORRECTNESS (0-15):**
   - ConveyorState transitions: Are all valid transitions covered?
   - Can a segment go from JAMMED→RUNNING without clearing? (Should NOT)
   - Can a segment go from MAINTENANCE→RUNNING directly? (Should NOT — must go through IDLE)
   - Is STOPPED (cascade) different from IDLE? (YES — STOPPED auto-resumes on jam clear)

4. **INTEGRATION WITH EXISTING SYSTEM (0-15):**
   - How does WCS connect to WES? (Orders → tasks → robot picks → drops on conveyor)
   - How does WCS connect to Fleet Manager? (Robot drops package at conveyor entry point)
   - Is _init_wcs called at the right point in app startup?
   - Does WCS config path resolution work in Docker? (Path relative to project root)

5. **SCALABILITY (0-10):**
   - What happens with 10,000 packages? (Memory growth in PackageTracker?)
   - What happens with 100 conveyor segments? (O(N) cascade walk?)
   - Is sort_log bounded? (MAX_LOG?)
   - Are lane.packages lists unbounded?

6. **CONFIG DESIGN (0-10):**
   - Is conveyor_layout.yaml schema documented?
   - Are segment links (upstream_id/downstream_id) validated for consistency?
   - Can the config represent real warehouse conveyor topologies? (Y-junctions, merges, splits?)

7. **API DESIGN (0-10):**
   - RESTful? (GET for reads, POST for mutations)
   - Consistent error responses? (all return {"ok": false, "error": "..."})
   - Pagination for large lists?
   - Do endpoints match the resource model? (conveyors, sorter, lanes, packages)

8. **DOCUMENTATION (0-10):**
   - Module docstrings explain purpose?
   - Function signatures are clear?
   - Config file has comments?
   - ROADMAP.md updated?

**Output format:**
```
SCORE: XX/100
STATUS: PASS/FAIL

ARCHITECTURE DIAGRAM (actual, from code):
  [draw the real data flow you see]

FINDINGS:
1. [SEVERITY] File:Line — description
2. ...

INTEGRATION GAPS:
1. ...
```

# Robotic Digital Twin Simulation — Project Rules

## NO `rm` COMMAND — EVER
Use `mv` to archive. Never `rm`.

## HARD RULES

1. **C++ for FMS core.** FleetManager, PathPlanner, NodeReservation, BehaviorTree, MPC, TCP — ALL C++. No Python reimplementations.

2. **Python for API + Intelligence only.** FastAPI reads MongoDB. io-gita and SG prediction are Python. Nothing else.

3. **No faking.** No MagicMock databases. No hardcoded responses. If MongoDB isn't running, the endpoint returns empty data but /health reports mongodb_ok=False. Tests must test REAL behavior.

4. **Install what's needed.** vcpkg for C++ deps. pip for Python. npm for frontend. Docker for services. No stubs pretending deps exist.

5. **YAML configs are source of truth.** Robot parameters come from configs/robots/*.yaml at runtime. No hardcoded values in C++ or Python. Grep for magic numbers before committing.

6. **External review after every phase.** Kimi, Gemini, or Codex. No skipping. Fix all findings before next phase.

7. **Tests run and pass.** gtest for C++. pytest for Python. Playwright for E2E. All must actually execute.

8. **Blueprint delta = 0.** Every claimed feature must exist in code. No silent drops.

## QUALITY GATE — 85% MINIMUM ON FIRST AUDIT

Every phase must score 85/100+ on its FIRST external audit. Not after fixes. First time.

Before writing ANY code, run this mental checklist:
- [ ] No hardcoded values — all from config YAML/JSON
- [ ] No MagicMock — real connections with graceful degradation
- [ ] No fake health checks — actually probe each service
- [ ] No dead code — every function is called AND tested
- [ ] No doc claims without matching code
- [ ] All test assertions check REAL values (exact numbers, not "is not None")
- [ ] Architecture docs match actual file paths
- [ ] All library APIs verified (don't guess — check the header/docs)

Before committing, ask: "If Kimi audits this right now, what score does it get?"

## NO HALLUCINATION — VERIFY BEFORE WRITING

Known past mistakes (DO NOT REPEAT):
- Assumed 360° LiDAR when target had ±15° sensor
- Assumed AMCL when target used barcode grid
- FetchContent'd BehaviorTree.CPP v4.6.2 without checking it compiles (lexy bug)
- Used robot_params_new.yaml instead of ActionCodes.yaml (13 parameter mismatches)
- Wrote Gazebo gz-sim7 API without verifying it matches Fortress version
- Created Python reimplementations of C++ fleet_core and called it "integration"
- Health checks returned hardcoded True without probing services
- Tests asserted "is not None" instead of checking actual values

When using a library API → check the actual docs/header first.
When claiming a feature exists → verify the file has real logic.
When writing config values → cross-reference the source YAML/JSON.
When setting up build systems → verify package names and find_package names.
If unsure → say so and look it up. Don't guess.

## LEARNED RULES (from 20+ factory projects)

- Never rewrite existing production code in another language — use the original
- No phase skipping — artifacts must exist before moving on
- Tests must actually execute — "tests pass" means pytest/gtest output shows N passed 0 failed
- Assertions must check real values — status_code==200 AND response["id"]==expected_id
- Dead code = code not called from outside itself. "tests call it" is NOT acceptable
- Documents must match code exactly — stale docs are lies
- Every IN-SCOPE item in blueprint must exist in code — no silent drops
- Config duplication = maintenance nightmare — single source of truth
- Hardcoded /tmp paths lose state on reboot — use persistent paths
- Import isolation — verify modules load from THIS package, not cross-project leakage

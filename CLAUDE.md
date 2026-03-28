# Robotic Digital Twin Simulation — Project Rules

## NO `rm` COMMAND — EVER
Use `mv` to archive. Never `rm`.

## HARD RULES

1. **C++ for FMS core.** FleetManager, PathPlanner, NodeReservation, BehaviorTree, MPC, TCP — ALL C++. No Python reimplementations.

2. **Python for API + Intelligence only.** FastAPI reads MongoDB. io-gita and SG prediction are Python. Nothing else.

3. **No faking.** No MagicMock databases. No hardcoded responses. If MongoDB isn't running, the test fails. If the C++ binary doesn't exist, the test fails. Tests must test REAL behavior.

4. **Install what's needed.** vcpkg for C++ deps. pip for Python. npm for frontend. Docker for services. No stubs pretending deps exist.

5. **YAML configs are source of truth.** Robot parameters come from configs/robots/*.yaml at runtime. No hardcoded values in C++ or Python.

6. **Kimi reviews after every phase.** No skipping. Fix all findings before next phase.

7. **Tests run and pass.** gtest for C++. pytest for Python. Playwright for E2E. All must actually execute.

8. **Blueprint delta = 0.** Every claimed feature must exist in code. No silent drops.

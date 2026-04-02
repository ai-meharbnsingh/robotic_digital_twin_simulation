# Phases 16-18: Plan

## Phase 16 — Predictive Maintenance
**Goal:** Component failure modeling, MTBF tracking, scheduled maintenance windows, degradation curves.

**New files:**
- `python/services/maintenance/predictive_engine.py` — MTBF models, failure probability, degradation curves
- `python/services/maintenance/scheduler.py` — Maintenance window scheduling, fleet impact calculator
- `python/services/maintenance/component_model.py` — Component definitions (motor, battery, sensor, wheel)
- `python/app/routes/maintenance.py` — REST endpoints (8-10 new)
- `python/tests/test_maintenance.py` — TDD tests (RED first)
- `configs/maintenance/component_profiles.yaml` — MTBF/degradation params per component

**Endpoints:**
- `GET /api/maintenance/status` — Fleet maintenance overview
- `GET /api/maintenance/predictions/{robot_id}` — Failure probabilities per component
- `GET /api/maintenance/schedule` — Upcoming maintenance windows
- `POST /api/maintenance/schedule` — Create maintenance window
- `POST /api/maintenance/schedule/{id}/complete` — Mark maintenance done
- `GET /api/maintenance/component-health/{robot_id}` — Component health scores
- `GET /api/maintenance/fleet-mtbf` — Fleet-wide MTBF stats
- `POST /api/maintenance/simulate-degradation` — Fast-forward degradation for testing
- `GET /api/maintenance/alerts` — Components approaching failure threshold

**TDD:**
- RED: Write 40+ tests covering all endpoints, degradation math, scheduling logic
- GREEN: Implement minimal code to pass
- REFACTOR: Clean up, ensure no dead code

---

## Phase 17 — Human Dynamic Agents
**Goal:** Non-robot entities (workers, forklifts) that affect MAPF path planning and trigger safety zones.

**New files:**
- `python/services/human_agents/worker_model.py` — Human agent types, movement patterns
- `python/services/human_agents/safety_zone.py` — Dynamic safety zones around humans
- `python/services/human_agents/interaction_manager.py` — Human-robot interaction rules
- `python/app/routes/human_agents.py` — REST endpoints (8-10 new)
- `python/tests/test_human_agents.py` — TDD tests (RED first)
- `configs/human_agents/worker_profiles.yaml` — Worker types, speeds, zones

**Endpoints:**
- `GET /api/human-agents` — List all human agents
- `POST /api/human-agents` — Add human agent (worker/forklift/supervisor)
- `DELETE /api/human-agents/{id}` — Remove human agent
- `POST /api/human-agents/{id}/move` — Update human position
- `GET /api/human-agents/safety-zones` — Active safety zones
- `GET /api/human-agents/interactions` — Recent human-robot interactions
- `POST /api/human-agents/simulate` — Run human movement simulation
- `GET /api/human-agents/stats` — Interaction stats (yields, stops, reroutes)
- `PATCH /api/human-agents/{id}` — Update agent properties

**Integration with MAPF:**
- Human agents become high-priority obstacles in PIBT/CBS
- Safety zones expand node reservation radius
- Robots yield to humans (priority inversion)

**TDD:**
- RED: Write 40+ tests covering CRUD, movement, safety zones, MAPF integration
- GREEN: Implement
- REFACTOR: Clean

---

## Phase 18 — Smart Charging Strategy
**Goal:** Intelligent charge scheduling — opportunity charging, load balancing, degradation curves, queue management.

**New files:**
- `python/services/charging/strategy_engine.py` — Charging strategy optimizer
- `python/services/charging/queue_manager.py` — Charge station queue management
- `python/services/charging/degradation_model.py` — Battery degradation over cycles
- `python/app/routes/charging.py` — REST endpoints (8-10 new)
- `python/tests/test_charging.py` — TDD tests (RED first)
- `configs/charging/strategy_profiles.yaml` — Charging policies

**Endpoints:**
- `GET /api/charging/status` — Charge station status + queue
- `GET /api/charging/strategy` — Active strategy config
- `POST /api/charging/strategy` — Update strategy (opportunistic/scheduled/priority)
- `GET /api/charging/queue` — Robots waiting to charge
- `POST /api/charging/request/{robot_id}` — Request charge slot
- `GET /api/charging/battery-health` — Fleet battery degradation report
- `GET /api/charging/energy-forecast` — Energy demand forecast
- `POST /api/charging/simulate-cycle` — Simulate N charge cycles for degradation
- `GET /api/charging/stats` — Charging KPIs (avg wait, utilization, energy used)
- `GET /api/charging/recommendations` — Charge timing recommendations

**TDD:**
- RED: Write 35+ tests covering strategies, queueing, degradation math
- GREEN: Implement
- REFACTOR: Clean

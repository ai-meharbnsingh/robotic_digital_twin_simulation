# Gap Analysis: Hairobotics Virtual Warehouse vs. RDT Simulation

**Date:** 2026-03-29
**Reference:** https://www.hairobotics.com/virtual-warehouse

## 1. Hairobotics Overview

Hai Robotics (est. 2016) is a leader in Autonomous Case-handling Robot (ACR) systems. Their HAI Q platform is a commercial warehouse automation suite with:

- **1:1 Simulation Platform** — Input map files, order files, inventory files, and demand configs to create a full virtual warehouse replica for project verification and strategy tuning.
- **3D Virtual Warehouse Tour** — Interactive 360-degree browser-based walkthrough showing inbound/outbound processes and robot operations.
- **AI Algorithm Platform** — Central intelligence for analysis, computation, and decision-making across all warehouse scenarios.
- **WES Integration** — Interfaces with ERP, WMS, MES; supports order grouping, splitting, wave rules, and heat-based slotting strategies.
- **4+ Specialized Robot Types:**
  - HaiPick A3 — Fork-lifting ACR (5.5m reach, handles trays/tires/foam)
  - HaiPick A42 — Multi-layer ACR (6m reach, 9 cases simultaneously, 300kg)
  - HaiPick A42T — Telescopic ACR (12m reach, 100% more storage density)
  - HaiPick A42-E6S — Grappling hook ACR (triple-deep racks, 300kg)
- **Data Platform** — Centralizes data from WES, robots, equipment, personnel, and commodities with visualization dashboards.
- **Enterprise Grade** — 10,000 req/s, HA with auto-failover, load balancing, data disaster recovery.

## 2. Feature Comparison

| Feature | RDT (Ours) | Hairobotics (HAI Q) | Status |
|---------|------------|---------------------|--------|
| Real-time fleet management | C++ 15Hz FMS loop | HAI Q orchestration | On par |
| Pathfinding + collision avoidance | A* + NodeReservation + QuadTree | Proprietary path optimizer | On par |
| Behavior trees | Custom BT engine (BTCPP v4 XML) | AI Algorithm Platform | On par |
| REST API | FastAPI, 34 endpoints | HAI Q API | On par |
| WebSocket streaming | /ws/fleet real-time | Real-time updates | On par |
| Predictive intelligence | SG bottleneck prediction (Hopfield) | AI decision-making | On par |
| Cold start recovery | io-gita zone ID + recovery (<1ms) | Not advertised | Ahead |
| Physics simulation | Gazebo Fortress (SDF worlds) | 1:1 simulation platform | Partial |
| Dashboard | React + Tailwind (6 panels) | Rich analytics + 3D tour | Behind |
| WES | Poisson order generator + KPI | Full WES (ERP/WMS/MES integration) | Behind |
| Robot variety | 2 presets (diff-drive AMR, uni AGV) | 4+ specialized ACR types | Behind |
| Warehouse model | 2D graph (nodes/edges/zones) | 3D with rack depth + vertical layers | Behind |
| Order strategies | Greedy nearest-available | Wave planning, grouping, heat slotting | Behind |
| HA / scaling | Single-process Docker Compose | Auto-failover, load balancing, 10K rps | Behind |
| Data analytics | InfluxDB + Grafana + basic KPIs | Centralized BI platform | Behind |

## 3. Identified Gaps

### 3.1 HIGH PRIORITY

#### Gap 1: 3D Browser-Based Warehouse Viewer
**What they have:** Interactive 360-degree 3D walkthrough of warehouse operations viewable in a browser.
**What we have:** Gazebo simulation (desktop only) + 2D React grid component.
**Recommendation:** Add a Three.js or Babylon.js 3D warehouse renderer to the React dashboard. Render warehouse nodes/edges as a 3D floor layout with animated robot models moving along paths in real-time via WebSocket.
**Effort:** Large
**Files affected:** `frontend/src/components/` (new Warehouse3DView component), `frontend/package.json`

#### Gap 2: WES Integration Protocol
**What they have:** WES that interfaces with ERP, WMS, MES systems. Supports order grouping, splitting, wave rules.
**What we have:** Standalone Poisson order generator. No external system connectors.
**Recommendation:** Define a WES integration API (REST/webhook) that accepts orders from external WMS/ERP systems. Add adapters for common protocols (e.g., OAGIS, GS1). Implement order grouping and wave planning logic in `python/wes/`.
**Effort:** Medium
**Files affected:** `python/wes/`, `python/app/routes/wes.py`, new `python/wes/integrations/` module

#### Gap 3: Order Strategy Engine
**What they have:** Wave planning, order grouping/splitting, heat-based slotting strategies.
**What we have:** Greedy nearest-available task allocation in `TaskManager`.
**Recommendation:** Implement pluggable allocation strategies in `cpp/src/fleet/TaskManager.cpp`. Add wave planning (batch orders by zone/time), order splitting (multi-pick decomposition), and heat-based slotting (frequently picked items near workstations). Strategy selection via `configs/` YAML.
**Effort:** Medium
**Files affected:** `cpp/src/fleet/TaskManager.cpp`, `cpp/include/rdt/fleet/TaskManager.h`, new strategy configs

### 3.2 MEDIUM PRIORITY

#### Gap 4: Specialized Robot Archetypes
**What they have:** Fork-lift (A3), multi-layer (A42), telescopic 12m (A42T), grappling hook (A42-E6S).
**What we have:** 2 generic presets (differential_drive.yaml, unidirectional.yaml).
**Recommendation:** Add robot YAML presets for fork-lift ACR, multi-tote ACR, and telescopic ACR. Extend `RobotState` and `MotionController` to support vertical motion (lift/lower), multi-payload capacity, and reach height. Add corresponding BT action nodes (LiftTo, LowerTo, GrabTote, ReleaseTote).
**Effort:** Medium
**Files affected:** `configs/robots/` (new YAML presets), `cpp/include/rdt/robot/`, `cpp/src/robot/`, `cpp/include/rdt/behavior/ActionNodes.h`

#### Gap 5: 3D Warehouse Model (Rack Depth + Vertical Layers)
**What they have:** Robots work with single- to triple-deep racks up to 12m high.
**What we have:** Flat 2D graph (x, y coordinates, no z-axis or rack depth).
**Recommendation:** Extend warehouse JSON schema to include `z` (height), `rack_depth` (1-3), and `shelf_levels` per node. Update `GraphMap` to support 3D coordinates. Update A* heuristic for 3D distance. Update Gazebo models for multi-level rack structures.
**Effort:** Large
**Files affected:** `configs/warehouses/*.json`, `cpp/include/rdt/navigation/GraphMap.h`, `cpp/src/navigation/AStar.cpp`, `gazebo/models/`

#### Gap 6: High Availability Architecture
**What they have:** Auto-failover, load balancing, data disaster recovery, 10K req/s.
**What we have:** Single-process Docker Compose. No redundancy.
**Recommendation:** Add Redis Sentinel for cache HA. Add MongoDB replica set config. Add FMS health monitoring with automatic restart. Add load-balanced FastAPI behind nginx/Traefik. Document horizontal scaling strategy. Update `docker/docker-compose.yml` with HA profiles.
**Effort:** Large
**Files affected:** `docker/docker-compose.yml`, `docker/docker-compose.ha.yml` (new), `python/app/main.py`, nginx/Traefik configs

### 3.3 LOW PRIORITY

#### Gap 7: Comprehensive Data Analytics / BI Dashboard
**What they have:** Centralized data platform collecting from WES, robots, equipment, personnel, commodities. Management dashboards with traffic analysis and efficiency metrics.
**What we have:** InfluxDB telemetry + Grafana + basic KPI tracker.
**Recommendation:** Extend `python/monitoring/` with aggregation pipelines for historical trends (daily throughput, robot utilization heatmaps, zone congestion over time). Add pre-built Grafana dashboards. Add a dedicated analytics panel in the React dashboard with charts (recharts/visx).
**Effort:** Medium
**Files affected:** `python/monitoring/`, `frontend/src/components/`, Grafana dashboard JSON exports

## 4. Implementation Roadmap

### Phase A: Core Competitiveness (Gaps 1-3)
**Goal:** Match Hairobotics on customer-facing capabilities.
- 3D warehouse viewer in React dashboard
- WES integration API with external system adapters
- Pluggable order strategy engine (wave, grouping, heat slotting)

### Phase B: Robot Fidelity (Gaps 4-5)
**Goal:** Support real-world robot diversity and warehouse complexity.
- New robot archetypes (fork-lift, multi-tote, telescopic)
- 3D warehouse model with rack depth and vertical layers

### Phase C: Production Readiness (Gaps 6-7)
**Goal:** Enterprise-grade deployment and observability.
- HA architecture with failover and load balancing
- Comprehensive analytics and BI dashboards

## 5. What We Do Better

Areas where RDT is ahead or differentiated:

1. **io-gita Cold Start Recovery** — LiDAR-based zone identification + automatic recovery hints for power-cycled robots. Not advertised by Hairobotics.
2. **Open Source + Pluggable** — Any company can load their warehouse JSON + robot YAML without code changes. Hairobotics is proprietary.
3. **SG Predictive Intelligence** — Hopfield attractor-based bottleneck prediction 2-5 minutes ahead. Unique approach.
4. **Transparent Performance Proof** — All performance targets tested and proven with actual benchmarks (not just marketing claims).
5. **Full C++ Real-Time Core** — 15Hz guaranteed loop with proven <67ms timing. Many competitors use Python for fleet management.

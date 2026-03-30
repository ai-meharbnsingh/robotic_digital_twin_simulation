# P29 WRIE — Warehouse Robotics Digital Twin

## What It Is
Open-source warehouse robotics simulator. Any company loads their warehouse layout (JSON) + robot specs (YAML) → gets a full simulation with real-time fleet management, 3D browser visualization, and task execution. One Docker command. No vendor lock-in.

## Why It Matters
- **Hai Robotics, Geek+, Locus** charge $$$$$ for proprietary simulators locked to THEIR robots
- **FlexSim** is $5-100K/yr desktop software
- **We're free, open-source, browser-based, and work with ANY robot YAML config**

## What's Built (ALL 12 Phases Complete)

### Core Engine (C++ — 398 tests)
- 15Hz fleet management loop (FleetManager, TaskManager, COPP)
- A* pathfinding, QuadTree, Node Reservation (0 deadlocks with 10 robots)
- Custom Behavior Tree engine (11 action + 7 condition nodes)
- TCP Protocol V1 (33 fields + CRC32) at 150 msg/s
- All written from scratch — no proprietary deps

### Python API (FastAPI — 906 tests)
- 118 REST endpoints + 1 WebSocket
- Warehouse Execution System (WES): order gen, task gen, KPI tracking
- Wave Rule Engine: batch picking, zone affinity grouping
- CSV/Excel order import with OWASP validation
- Heat map: spatial traffic density over configurable time windows
- io-gita v4: hierarchical zone identification (>90% zone accuracy)
- Mixed fleet support (AMR + AGV + forklifts)

### 3D Browser Visualization (React Three Fiber)
- Interactive 3D warehouse — auto-generated from JSON config
- Robots move in real-time via WebSocket (position interpolation at 60fps)
- Shared geometry pools for 50+ robot scalability
- Heat map overlay, battery indicators, path lines, camera follow mode
- Lazy-loaded (~918KB, only when 3D tab clicked)
- 2D/3D toggle preserves state

### Infrastructure
- Docker Compose: 7 services (MongoDB, Redis, InfluxDB, RabbitMQ, Grafana, Mosquitto, App)
- Gazebo Fortress: 3D physics sim with LiDAR, barcode, conveyor plugins
- 1398 total tests (398 C++ + 928 Python + 52 Gazebo), 0 failures in any environment

## What's Next (Phases 13-15)

| Phase | Feature | Effort | Business Value |
|-------|---------|--------|----------------|
| **13** | WCS — Conveyors + Sorters | 2-3 weeks | Full material flow simulation — conveyor + sorter + lane management |
| **14** | WMS — Inventory Management | 3-4 weeks | SKU tracking, replenishment, putaway, slotting optimization |
| **15** | Warehouse Designer v2 (3D GUI) | 4-6 weeks | React Three Fiber 3D editor — drag shelves, draw conveyors |

## Business Model

| Timeline | Revenue | Target |
|----------|---------|--------|
| Month 1-2 | Consulting pilots (Phases 1-3) | $25-50K |
| Month 3-4 | Scenario comparison engagements | 2-3 at $50-100K |
| Month 5-8 | SaaS MVP with designer + 3D | $500-2K/mo, 10-20 users |
| Year 1 | Consulting + SaaS | **$200-750K** |

## Competitive Edge
- Only open-source simulator with a **real C++ FMS running at 15Hz**
- Only one with **browser-based 3D** (not desktop app)
- Only one that takes **any YAML robot config** (not locked to one vendor)
- **Docker one-command** setup vs weeks of installation
- Free vs $$$$ proprietary alternatives

## Tech Stack
C++17 (CMake, vcpkg) | Python 3.11 (FastAPI, Motor) | TypeScript (React 19, Three.js, Vite) | Docker | MongoDB | Redis | InfluxDB | RabbitMQ | Grafana | Gazebo Fortress

## Repo
https://github.com/ai-meharbnsingh/robotic_digital_twin_simulation

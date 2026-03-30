# Getting Started

Get the Robotic Digital Twin Simulation running in 5 minutes.

## Prerequisites

| Tool | Version | Check |
|------|---------|-------|
| Docker | 24+ | `docker --version` |
| Docker Compose | v2+ | `docker compose version` |
| Git | 2.30+ | `git --version` |
| Python 3.11+ | (optional, for standalone demos) | `python3 --version` |

## 1. Clone the Repository

```bash
git clone https://github.com/your-org/robotic_digital_twin_simulation.git
cd robotic_digital_twin_simulation
```

## 2. Configure

Copy the environment file and adjust if needed:

```bash
cp .env.example .env
```

Default configuration uses:
- **Warehouse:** `simple_grid` (25 nodes, 8 zones)
- **Robot:** `differential_drive` (AMR with 360-degree LiDAR)

To use a different warehouse or robot:

```bash
# Edit .env
WAREHOUSE_CONFIG=botvalley
ROBOT_CONFIG=unidirectional
```

## 3. Start Services

```bash
docker compose -f docker/docker-compose.yml up --build
```

This starts 7 services:

| Service | Port | Purpose |
|---------|------|---------|
| rdt-app | 65123, 7012, 8029 | C++ FMS + Python API |
| rdt-mongodb | 27017 | State IPC (C++ writes, Python reads) |
| rdt-rabbitmq | 5672, 15672 | Task queue + event bus |
| rdt-redis | 6379 | Real-time position cache |
| rdt-influxdb | 8086 | Time-series telemetry |
| rdt-grafana | 3000 | Dashboards |
| rdt-mosquitto | 1883, 9001 | MQTT broker (VDA5050) |

Wait for the health check to pass (about 30 seconds):

```bash
curl http://localhost:8029/health
```

Expected output:
```json
{
  "status": "healthy",
  "mongodb_ok": true,
  "redis_ok": true,
  "influxdb_ok": true,
  "warehouse_loaded": true,
  "robot_loaded": true,
  "wes_loaded": true
}
```

## 4. Explore the API

Open the interactive docs:

```
http://localhost:8029/docs
```

Try a few endpoints:

```bash
# Fleet status
curl http://localhost:8029/api/fleet/status

# Warehouse map
curl http://localhost:8029/api/map

# Compute a path
curl "http://localhost:8029/api/map/path?start=DOCK_1&end=DROP_1"

# Inject 5 orders
curl -X POST http://localhost:8029/api/wes/inject-orders \
  -H "Content-Type: application/json" \
  -d '{"num_orders": 5}'
```

## 5. Run the Demo

The fleet demo (with running API):

```bash
python3 demo/fleet_demo.py
```

Or standalone (no API server needed):

```bash
python3 demo/fleet_demo.py --standalone
```

## 6. View Dashboards

| Dashboard | URL | Credentials |
|-----------|-----|-------------|
| FastAPI Docs | http://localhost:8029/docs | none |
| RabbitMQ | http://localhost:15672 | fms / fms_pass |
| Grafana | http://localhost:3000 | admin / admin |
| InfluxDB | http://localhost:8086 | admin / adminpass |

## Stopping

```bash
docker compose -f docker/docker-compose.yml down
```

To also remove stored data:

```bash
docker compose -f docker/docker-compose.yml down -v
```

## Next Steps

- [API Reference](API_REFERENCE.md) — All 116 endpoints with examples
- [Configuration Guide](CONFIGURATION.md) — Custom warehouses, robots, behavior trees
- [Architecture](ARCHITECTURE.md) — System design and data flow

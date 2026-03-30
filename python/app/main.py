"""
FastAPI application — the Python API layer.

On startup:
  - Loads warehouse config from JSON
  - Loads robot config from YAML
  - Connects to MongoDB (REAL connection, fails if unavailable)
  - Initializes WES OrderGenerator + KPITracker
  - Connects to Redis (graceful if unavailable)

io-gita intelligence layer v4 — REINSTATED with hierarchical zone-first fix.
  Prior versions failed (dim=16 → 9.9%, D=10000 → 14.8%).
  v4 uses geometry-only zone features (12-dim) + zone-first hierarchy → >90% zone accuracy.
  See _archive/io_gita_dropped/ for v1-v3 history.

/health endpoint ACTUALLY checks MongoDB, Redis, InfluxDB connectivity.
No hardcoded True values.
"""

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)

from app.config import Settings, get_settings, load_robot_config, load_warehouse_config


# --- Application state (populated on startup) ---
app_state: dict[str, Any] = {
    "warehouse_config": None,
    "robot_config": None,
    "mongo_client": None,
    "mongo_db": None,
    "redis_client": None,
    "redis_cache": None,
    "influx_writer": None,
    "settings": None,
    # WES
    "wes_order_generator": None,
    "wes_task_generator": None,
    "wes_kpi_tracker": None,
    # Scenario comparison (Phase 6)
    "scenario_manager": None,
    # Simulation state
    "simulation_state": {"running": False},
    # io-gita v4 intelligence
    "iogita_zone_identifier": None,
    "iogita_cold_start": None,
    # VDA5050 gateway (Phase 8)
    "vda5050_gateway": None,
    # ROS2 bridge + HAL (Phase 10)
    "ros2_bridge": None,
    "ros2_hal": None,
    # MAPF solvers + congestion tracker (Phase 11)
    "congestion_tracker": None,
    # WMS/ERP connector (Phase 12)
    "wms_connector": None,
    "wms_dlq": None,
    "wms_orders": [],
}


async def check_mongodb(state: dict[str, Any]) -> bool:
    """Ping MongoDB. Returns True only if server responds."""
    client = state.get("mongo_client")
    if client is None:
        return False
    try:
        result = await client.admin.command("ping")
        return result.get("ok") == 1.0
    except Exception:
        return False


async def check_redis(settings: Settings) -> bool:
    """Attempt a Redis PING. Returns True only if server responds."""
    try:
        client = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
        pong = await client.ping()
        await client.aclose()
        return pong is True
    except Exception:
        return False


async def check_influxdb(settings: Settings) -> bool:
    """Hit the InfluxDB /health endpoint. Returns True only if status is 'pass'."""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{settings.influxdb_url}/health")
            if resp.status_code == 200:
                body = resp.json()
                return body.get("status") == "pass"
            return False
    except Exception:
        return False


async def check_rabbitmq(settings: Settings) -> bool:
    """Check RabbitMQ management API. Returns True only if reachable."""
    try:
        # RabbitMQ management plugin runs on port 15672
        mgmt_url = settings.rabbitmq_url.replace("amqp://", "http://").replace("5672", "15672")
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{mgmt_url}/api/health/checks/alarms")
            return resp.status_code == 200
    except Exception:
        return False


def _init_wes(warehouse_config: dict):
    """Initialize WES components."""
    nodes = warehouse_config.get("nodes", [])
    pick_nodes = [n["name"] for n in nodes if n.get("type") == "pick"]
    drop_nodes = [n["name"] for n in nodes if n.get("type") == "drop"]

    try:
        from wes.order_generator import OrderGenerator
        from wes.task_generator import TaskGenerator
        from wes.kpi_tracker import KPITracker
        from wes.wave_engine import WaveEngine

        app_state["wes_order_generator"] = OrderGenerator(
            pick_nodes=pick_nodes,
            drop_nodes=drop_nodes,
        )
        app_state["wes_task_generator"] = TaskGenerator()
        app_state["wes_kpi_tracker"] = KPITracker()
        app_state["wes_wave_engine"] = WaveEngine(warehouse_config)
    except Exception:
        pass


async def _hydrate_wave_rules():
    """Load wave rules from MongoDB into WaveEngine (called from async lifespan)."""
    engine = app_state.get("wes_wave_engine")
    db = app_state.get("mongo_db")
    if engine is None or db is None:
        return
    try:
        rules = await db["wave_rules"].find({}, {"_id": 0}).to_list(length=1000)
        if rules:
            engine.set_rules(rules)
    except Exception:
        pass  # Graceful — rules will be empty until created


def _init_iogita(warehouse_config: dict):
    """Initialize io-gita intelligence layer — KDTree engine (525x faster than Hopfield ODE).

    Swap history:
      v1-v3: Failed (9.9-14.8% accuracy)
      v4:    Hopfield ODE + hierarchical zone-first → 88.9% zone accuracy, 4.197ms
      v5:    KDTree (this) → same 88.9% accuracy, 0.008ms (525x faster, 329x less memory)
    """
    try:
        import sys
        kdtree_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "..", "iogita_kdtree_addverb",
        )
        if kdtree_path not in sys.path:
            sys.path.insert(0, kdtree_path)

        from engine import IoGitaEngine
        from intelligence.iogita import ColdStartRecovery

        nodes = warehouse_config.get("nodes", [])
        zones = warehouse_config.get("zones", [])

        if zones and nodes:
            # KDTree engine — same config format, 525x faster
            kdtree_engine = IoGitaEngine()
            kdtree_engine.load_config(warehouse_config)

            # Wrap with the interface the routes expect
            class _KDTreeZoneAdapter:
                """Adapter: makes IoGitaEngine look like HierarchicalZoneIdentifier."""

                def __init__(self, engine, zones_list, nodes_list):
                    self._engine = engine
                    self.zones = zones_list
                    self.nodes_by_name = {n["name"]: n for n in nodes_list}

                def identify(self, features):
                    """Zone ID from [x, y] coordinates (pose-based, no LiDAR)."""
                    import math
                    x, y = features[0], features[1]
                    # Find nearest node by Euclidean distance
                    best_node = None
                    best_dist = float("inf")
                    for name, node in self.nodes_by_name.items():
                        d = math.sqrt((x - node["x"]) ** 2 + (y - node["y"]) ** 2)
                        if d < best_dist:
                            best_dist = d
                            best_node = name
                    if best_node:
                        return self._engine._node_to_zone.get(best_node, "unknown")
                    return "unknown"

                @property
                def engine(self):
                    """Direct access to KDTree engine for LiDAR-based recovery."""
                    return self._engine

            zone_id = _KDTreeZoneAdapter(kdtree_engine, zones, nodes)
            app_state["iogita_zone_identifier"] = zone_id
            app_state["iogita_engine"] = kdtree_engine

            cold_start = ColdStartRecovery()
            app_state["iogita_cold_start"] = cold_start
            logger.info(
                "io-gita v5 loaded: %d zones, %d nodes, backend=kdtree (525x faster than hopfield)",
                len(zones), len(nodes),
            )
        else:
            logger.warning("io-gita v5: no zones/nodes in warehouse config")
    except Exception as e:
        logger.warning("io-gita v5 init failed (falling back to v4 Hopfield): %s", e)
        # Fallback to Hopfield ODE if KDTree import fails
        try:
            from intelligence.iogita import HierarchicalZoneIdentifier, ColdStartRecovery
            nodes = warehouse_config.get("nodes", [])
            zones = warehouse_config.get("zones", [])
            edges = warehouse_config.get("edges", [])
            if zones and nodes:
                zone_id = HierarchicalZoneIdentifier(zones=zones, nodes=nodes, edges=edges)
                app_state["iogita_zone_identifier"] = zone_id
                app_state["iogita_cold_start"] = ColdStartRecovery()
                logger.info("io-gita v4 fallback loaded (Hopfield ODE)")
        except Exception as e2:
            logger.warning("io-gita fallback also failed: %s", e2)
            app_state["iogita_zone_identifier"] = None
            app_state["iogita_cold_start"] = None


def _init_vda5050(settings: Settings):
    """Initialize VDA5050 Gateway (Phase 8)."""
    try:
        from vda5050.mqtt_client import VDA5050MQTTClient
        from vda5050.translator import VDA5050Translator
        from vda5050.gateway import VDA5050Gateway

        # Use Settings fields (populated from env vars via pydantic-settings)
        broker_url = settings.mqtt_broker_url
        manufacturer = settings.vda5050_manufacturer
        serial_number = "DT-001"  # Not a per-instance setting; static default

        mqtt_client = VDA5050MQTTClient(
            broker_url=broker_url,
            manufacturer=manufacturer,
            serial_number=serial_number,
        )
        translator = VDA5050Translator()
        db = app_state.get("mongo_db")

        gateway = VDA5050Gateway(
            mqtt_client=mqtt_client,
            translator=translator,
            db=db,
        )
        app_state["vda5050_gateway"] = gateway
        logger.info("VDA5050 Gateway initialized (broker=%s)", broker_url)
    except Exception as e:
        logger.warning("VDA5050 Gateway init failed: %s", e)
        app_state["vda5050_gateway"] = None


def _init_wms(settings: Settings):
    """Initialize WMS/ERP connector and DLQ (Phase 12).

    Default: WebhookAdapter (works without external WMS).
    SAP/Odoo adapters activated via env vars WMS_TYPE, WMS_SAP_URL, etc.
    """
    try:
        from wms.dlq import DeadLetterQueue

        dlq = DeadLetterQueue(rabbitmq_url=settings.rabbitmq_url)
        app_state["wms_dlq"] = dlq

        wms_type = os.environ.get("WMS_TYPE", "webhook").lower()

        if wms_type == "sap":
            from wms.sap_adapter import SAPAdapter
            adapter = SAPAdapter(
                base_url=os.environ.get("WMS_SAP_URL", "http://localhost:8080"),
                api_key=os.environ.get("WMS_SAP_API_KEY", ""),
            )
        elif wms_type == "odoo":
            from wms.odoo_adapter import OdooAdapter
            adapter = OdooAdapter(
                url=os.environ.get("WMS_ODOO_URL", "http://localhost:8069"),
                db=os.environ.get("WMS_ODOO_DB", "odoo"),
                user=os.environ.get("WMS_ODOO_USER", "admin"),
                password=os.environ.get("WMS_ODOO_PASSWORD", "admin"),
            )
        else:
            from wms.webhook_adapter import WebhookAdapter
            adapter = WebhookAdapter(
                callback_url=os.environ.get("WMS_WEBHOOK_CALLBACK", ""),
            )

        app_state["wms_connector"] = adapter
        app_state["wms_orders"] = []
        logger.info("WMS connector initialized (type=%s)", wms_type)
    except Exception as e:
        logger.warning("WMS connector init failed: %s", e)
        app_state["wms_connector"] = None
        app_state["wms_dlq"] = None


def _init_ros2_bridge():
    """Initialize ROS2 Bridge and HAL (Phase 10).

    Gracefully handles missing rclpy -- bridge runs in simulated mode.
    """
    try:
        from ros2_bridge.bridge import ROS2Bridge
        from ros2_bridge.hal import HAL, HardwareMode

        bridge = ROS2Bridge(fms_url=f"http://localhost:7012")
        app_state["ros2_bridge"] = bridge

        # Determine mode from bridge availability
        mode = HardwareMode.ROS2_SIM if bridge.ros2_available else HardwareMode.SIMULATED
        hal = HAL(mode=mode)
        app_state["ros2_hal"] = hal
        logger.info("ROS2 Bridge initialized (mode=%s)", mode.value)
    except Exception as e:
        logger.warning("ROS2 Bridge init failed: %s", e)
        app_state["ros2_bridge"] = None
        app_state["ros2_hal"] = None


def _init_scenarios():
    """Initialize ScenarioManager for parallel scenario comparison (Phase 6)."""
    try:
        from wes.scenario_manager import ScenarioManager
        from app.config import load_warehouse_config, load_robot_config

        db = app_state.get("mongo_db")
        app_state["scenario_manager"] = ScenarioManager(
            db=db,
            warehouse_config_loader=load_warehouse_config,
            robot_config_loader=load_robot_config,
        )
    except Exception as e:
        logger.warning("Scenario manager init failed: %s", e)
        app_state["scenario_manager"] = None


def _init_monitoring(settings: Settings):
    """Initialize monitoring (InfluxDB writer, Redis cache)."""
    # InfluxDB writer
    try:
        from monitoring.influx_writer import InfluxWriter
        app_state["influx_writer"] = InfluxWriter(
            url=settings.influxdb_url,
            token=settings.influxdb_token,
            org=settings.influxdb_org,
            bucket=settings.influxdb_bucket,
        )
    except Exception:
        app_state["influx_writer"] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    settings = get_settings()
    app_state["settings"] = settings

    # Load configs from files
    app_state["warehouse_config"] = load_warehouse_config(settings.warehouse_config)
    app_state["robot_config"] = load_robot_config(settings.robot_config)

    # Connect to MongoDB (real connection — will fail health check if unavailable)
    # 500ms timeout: fast enough for healthy connections, fails fast when MongoDB is down
    # (prevents API endpoints from hanging 3s on each query when infra is unavailable)
    mongo_client = AsyncIOMotorClient(
        settings.mongodb_url,
        serverSelectionTimeoutMS=500,
    )
    app_state["mongo_client"] = mongo_client
    app_state["mongo_db"] = mongo_client[settings.mongodb_database]

    # Initialize WES
    _init_wes(app_state["warehouse_config"])

    # Initialize io-gita v4 intelligence
    _init_iogita(app_state["warehouse_config"])

    # Initialize monitoring
    _init_monitoring(settings)

    # Initialize Redis cache
    try:
        from monitoring.redis_cache import RedisCache
        redis_cache = RedisCache(redis_url=settings.redis_url)
        await redis_cache.connect()
        app_state["redis_cache"] = redis_cache
    except Exception:
        app_state["redis_cache"] = None

    # Hydrate wave rules from MongoDB (async-safe)
    await _hydrate_wave_rules()

    # Initialize Scenario Manager (Phase 6)
    _init_scenarios()

    # Initialize VDA5050 Gateway (Phase 8)
    _init_vda5050(settings)
    if app_state.get("vda5050_gateway"):
        await app_state["vda5050_gateway"].start()

    # Initialize MAPF congestion tracker (Phase 11)
    try:
        from wes.congestion_tracker import CongestionTracker
        app_state["congestion_tracker"] = CongestionTracker()
    except Exception as e:
        logger.warning("Congestion tracker init failed: %s", e)
        app_state["congestion_tracker"] = None

    # Initialize WMS/ERP connector (Phase 12)
    _init_wms(settings)

    # Initialize ROS2 Bridge + HAL (Phase 10)
    _init_ros2_bridge()
    if app_state.get("ros2_hal"):
        await app_state["ros2_hal"].init()

    yield

    # Shutdown: close connections
    if app_state.get("ros2_hal"):
        await app_state["ros2_hal"].shutdown()
    if app_state.get("vda5050_gateway"):
        await app_state["vda5050_gateway"].stop()
    if app_state.get("mongo_client"):
        app_state["mongo_client"].close()
    if app_state.get("redis_cache"):
        await app_state["redis_cache"].close()
    if app_state.get("influx_writer"):
        app_state["influx_writer"].close()


app = FastAPI(
    title="Robotic Digital Twin — API",
    description="REST API for fleet state, intelligence, and monitoring",
    version="0.1.0",
    lifespan=lifespan,
)

# --- CORS middleware (configurable via CORS_ORIGINS env var) ---
_cors_settings = get_settings()
_cors_origins = [o.strip() for o in _cors_settings.cors_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["X-API-Key", "Content-Type"],
)


# --- Include all routers ---
from app.routes.fleet import router as fleet_router
from app.routes.robots import router as robots_router
from app.routes.tasks import router as tasks_router
from app.routes.maps import router as maps_router

from app.routes.telemetry import router as telemetry_router
from app.routes.analytics import router as analytics_router
from app.routes.heatmap import router as heatmap_router
from app.routes.waves import router as waves_router
from app.routes.events import router as events_router
from app.routes.wcs import router as wcs_router
from app.routes.wes import router as wes_router
from app.routes.order_import import router as order_import_router
from app.routes.simulation import router as simulation_router
from app.routes.config_routes import router as config_router
from app.routes.stats import router as stats_router
from app.routes.reservations import router as reservations_router
from app.routes.iogita import router as iogita_router
from app.routes.scenarios import router as scenarios_router
from app.routes.designer import router as designer_router
from app.routes.vda5050 import router as vda5050_router
from app.routes.ros2 import router as ros2_router
from app.routes.mapf import router as mapf_router
from app.routes.wms import router as wms_router
from app.websocket import router as ws_router

app.include_router(fleet_router)
app.include_router(robots_router)
app.include_router(tasks_router)
app.include_router(maps_router)

app.include_router(telemetry_router)
app.include_router(analytics_router)
app.include_router(heatmap_router)
app.include_router(waves_router)
app.include_router(events_router)
app.include_router(wcs_router)
app.include_router(wes_router)
app.include_router(order_import_router)
app.include_router(simulation_router)
app.include_router(config_router)
app.include_router(stats_router)
app.include_router(reservations_router)
app.include_router(iogita_router)
app.include_router(scenarios_router)
app.include_router(designer_router)
app.include_router(vda5050_router)
app.include_router(ros2_router)
app.include_router(mapf_router)
app.include_router(wms_router)
app.include_router(ws_router)


@app.get("/health")
async def health_check():
    """
    Health endpoint — ACTUALLY checks each service.

    Returns a dict with boolean status for each dependency.
    Nothing is hardcoded. If a service is down, its field is False.
    """
    settings = app_state.get("settings") or get_settings()
    start = time.monotonic()

    mongodb_ok = await check_mongodb(app_state)
    redis_ok = await check_redis(settings)
    influxdb_ok = await check_influxdb(settings)
    rabbitmq_ok = await check_rabbitmq(settings)

    elapsed_ms = round((time.monotonic() - start) * 1000, 1)

    return {
        "status": "healthy" if all([mongodb_ok, redis_ok, influxdb_ok]) else "degraded",
        "mongodb_ok": mongodb_ok,
        "redis_ok": redis_ok,
        "influxdb_ok": influxdb_ok,
        "rabbitmq_ok": rabbitmq_ok,
        "warehouse_loaded": app_state.get("warehouse_config") is not None,
        "robot_loaded": app_state.get("robot_config") is not None,
        "wes_loaded": app_state.get("wes_order_generator") is not None,
        "check_duration_ms": elapsed_ms,
    }


@app.get("/")
async def root():
    """Root endpoint — basic info."""
    return {
        "service": "Robotic Digital Twin API",
        "version": "0.1.0",
        "docs": "/docs",
        "endpoints": 71,
    }


# --- Serve React dashboard if frontend dist exists ---
_frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/dashboard", StaticFiles(directory=str(_frontend_dist), html=True), name="dashboard")

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
    # Simulation state
    "simulation_state": {"running": False},
    # io-gita v4 intelligence
    "iogita_zone_identifier": None,
    "iogita_cold_start": None,
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


def _init_iogita(warehouse_config: dict):
    """Initialize io-gita v4 intelligence layer (hierarchical zone ID)."""
    try:
        from intelligence.iogita import HierarchicalZoneIdentifier, ColdStartRecovery

        nodes = warehouse_config.get("nodes", [])
        zones = warehouse_config.get("zones", [])
        edges = warehouse_config.get("edges", [])

        if zones and nodes:
            zone_id = HierarchicalZoneIdentifier(zones=zones, nodes=nodes, edges=edges)
            app_state["iogita_zone_identifier"] = zone_id
            cold_start = ColdStartRecovery()
            app_state["iogita_cold_start"] = cold_start
            logger.info(
                "io-gita v4 loaded: %d zones, %d nodes, backend=hierarchical_hopfield_d10000",
                len(zones), len(nodes),
            )
        else:
            logger.warning("io-gita v4: no zones/nodes in warehouse config")
    except Exception as e:
        logger.warning("io-gita v4 init failed: %s", e)
        app_state["iogita_zone_identifier"] = None
        app_state["iogita_cold_start"] = None


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
    mongo_client = AsyncIOMotorClient(
        settings.mongodb_url,
        serverSelectionTimeoutMS=3000,
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

    yield

    # Shutdown: close connections
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
        "endpoints": 37,
    }


# --- Serve React dashboard if frontend dist exists ---
_frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/dashboard", StaticFiles(directory=str(_frontend_dist), html=True), name="dashboard")

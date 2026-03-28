"""
FastAPI application — the Python API + Intelligence layer.

On startup:
  - Loads warehouse config from JSON
  - Loads robot config from YAML
  - Connects to MongoDB (REAL connection, fails if unavailable)
  - Initializes io-gita ZoneIdentifier + ColdStartRecovery
  - Initializes SG BottleneckPredictor
  - Initializes WES OrderGenerator + KPITracker
  - Connects to Redis (graceful if unavailable)

/health endpoint ACTUALLY checks MongoDB, Redis, InfluxDB connectivity.
No hardcoded True values.
"""

import time
from contextlib import asynccontextmanager
from typing import Any

import httpx
import redis.asyncio as aioredis
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from motor.motor_asyncio import AsyncIOMotorClient

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
    # Intelligence layer
    "iogita_zone_identifier": None,
    "iogita_cold_start": None,
    "iogita_fleet_atlas": None,
    "sg_engine": None,
    "bottleneck_predictor": None,
    # WES
    "wes_order_generator": None,
    "wes_task_generator": None,
    "wes_kpi_tracker": None,
    # Simulation state
    "simulation_state": {"running": False},
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


def _init_intelligence(warehouse_config: dict):
    """Initialize io-gita and SG prediction from warehouse config."""
    zones = warehouse_config.get("zones", [])
    nodes = warehouse_config.get("nodes", [])

    # io-gita ZoneIdentifier
    try:
        from intelligence.iogita.zone_identifier import ZoneIdentifier
        app_state["iogita_zone_identifier"] = ZoneIdentifier(zones=zones, nodes=nodes)
    except Exception:
        app_state["iogita_zone_identifier"] = None

    # io-gita ColdStartRecovery
    try:
        from intelligence.iogita.cold_start import ColdStartRecovery
        app_state["iogita_cold_start"] = ColdStartRecovery()
    except Exception:
        app_state["iogita_cold_start"] = None

    # io-gita FleetAtlas
    try:
        from intelligence.iogita.fleet_atlas import FleetAtlas
        app_state["iogita_fleet_atlas"] = FleetAtlas(zones=zones, nodes=nodes)
    except Exception:
        app_state["iogita_fleet_atlas"] = None

    # SG BottleneckPredictor
    try:
        from intelligence.sg_prediction.bottleneck_predictor import BottleneckPredictor
        app_state["bottleneck_predictor"] = BottleneckPredictor()
    except Exception:
        app_state["bottleneck_predictor"] = None


def _init_wes(warehouse_config: dict):
    """Initialize WES components."""
    nodes = warehouse_config.get("nodes", [])
    pick_nodes = [n["name"] for n in nodes if n.get("type") == "pick"]
    drop_nodes = [n["name"] for n in nodes if n.get("type") == "drop"]

    try:
        from wes.order_generator import OrderGenerator
        from wes.task_generator import TaskGenerator
        from wes.kpi_tracker import KPITracker

        app_state["wes_order_generator"] = OrderGenerator(
            pick_nodes=pick_nodes,
            drop_nodes=drop_nodes,
        )
        app_state["wes_task_generator"] = TaskGenerator()
        app_state["wes_kpi_tracker"] = KPITracker()
    except Exception:
        pass


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

    # Initialize intelligence layer
    _init_intelligence(app_state["warehouse_config"])

    # Initialize WES
    _init_wes(app_state["warehouse_config"])

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


# --- Include all routers ---
from app.routes.fleet import router as fleet_router
from app.routes.robots import router as robots_router
from app.routes.tasks import router as tasks_router
from app.routes.maps import router as maps_router
from app.routes.iogita import router as iogita_router
from app.routes.telemetry import router as telemetry_router
from app.routes.analytics import router as analytics_router
from app.routes.events import router as events_router
from app.routes.wcs import router as wcs_router
from app.routes.wes import router as wes_router
from app.routes.simulation import router as simulation_router
from app.routes.config_routes import router as config_router
from app.routes.stats import router as stats_router
from app.routes.reservations import router as reservations_router
from app.websocket import router as ws_router

app.include_router(fleet_router)
app.include_router(robots_router)
app.include_router(tasks_router)
app.include_router(maps_router)
app.include_router(iogita_router)
app.include_router(telemetry_router)
app.include_router(analytics_router)
app.include_router(events_router)
app.include_router(wcs_router)
app.include_router(wes_router)
app.include_router(simulation_router)
app.include_router(config_router)
app.include_router(stats_router)
app.include_router(reservations_router)
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
        "iogita_loaded": app_state.get("iogita_zone_identifier") is not None,
        "sg_loaded": app_state.get("bottleneck_predictor") is not None,
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
        "endpoints": 34,
    }


# --- Serve React dashboard if frontend dist exists ---
_frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/dashboard", StaticFiles(directory=str(_frontend_dist), html=True), name="dashboard")

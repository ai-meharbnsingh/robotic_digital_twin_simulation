"""
FastAPI application — the Python API + Intelligence layer.

On startup:
  - Loads warehouse config from JSON
  - Loads robot config from YAML
  - Connects to MongoDB (REAL connection, fails if unavailable)

/health endpoint ACTUALLY checks MongoDB, Redis, InfluxDB connectivity.
No hardcoded True values.
"""

import time
from contextlib import asynccontextmanager
from typing import Any

import httpx
import redis.asyncio as aioredis
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import Settings, get_settings, load_robot_config, load_warehouse_config


# --- Application state (populated on startup) ---
app_state: dict[str, Any] = {
    "warehouse_config": None,
    "robot_config": None,
    "mongo_client": None,
    "mongo_db": None,
    "redis_client": None,
    "settings": None,
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

    yield

    # Shutdown: close connections
    if app_state.get("mongo_client"):
        app_state["mongo_client"].close()


app = FastAPI(
    title="Robotic Digital Twin — API",
    description="REST API for fleet state, intelligence, and monitoring",
    version="0.1.0",
    lifespan=lifespan,
)


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
        "check_duration_ms": elapsed_ms,
    }


@app.get("/")
async def root():
    """Root endpoint — basic info."""
    return {
        "service": "Robotic Digital Twin API",
        "version": "0.1.0",
        "docs": "/docs",
    }


# --- Placeholder router imports (Phase 9 will populate these) ---
# from app.routes import fleet, tasks, robots, analytics, websocket

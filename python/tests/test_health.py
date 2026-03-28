"""
Tests for the /health endpoint.

REAL checks — the health endpoint ACTUALLY probes each service.
We prove checks are real by:
1. Verifying all fields exist with correct types
2. Verifying services that ARE running return True
3. Verifying that pointing at a WRONG port returns False (not hardcoded True)
"""

import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def async_client_bad_mongo():
    """
    Client with MongoDB pointed at a port where nothing is listening.
    Proves the health check actually probes MongoDB, not hardcoded True.
    """
    import importlib
    import sys

    # Override env BEFORE reloading modules
    os.environ["MONGODB_URL"] = "mongodb://localhost:19999"

    # Reload config then main so they pick up the new env
    config_mod = sys.modules["app.config"]
    main_mod = sys.modules["app.main"]
    importlib.reload(config_mod)
    importlib.reload(main_mod)

    fastapi_app = main_mod.app
    lifespan_fn = main_mod.lifespan

    async with lifespan_fn(fastapi_app):
        transport = ASGITransport(app=fastapi_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client

    # Restore correct env for other tests
    os.environ["MONGODB_URL"] = "mongodb://localhost:27017"
    importlib.reload(config_mod)
    importlib.reload(main_mod)


# ---- Tests with real services (all running locally) ----

@pytest.mark.asyncio
async def test_health_returns_all_8_fields(async_client: AsyncClient):
    """Health endpoint must return exactly these 8 fields."""
    resp = await async_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()

    expected_fields = [
        "status",
        "mongodb_ok",
        "redis_ok",
        "influxdb_ok",
        "rabbitmq_ok",
        "warehouse_loaded",
        "robot_loaded",
        "check_duration_ms",
    ]
    for field in expected_fields:
        assert field in data, f"Missing field: {field}"
    assert len(data) == 8, f"Expected 8 fields, got {len(data)}: {list(data.keys())}"


@pytest.mark.asyncio
async def test_health_fields_are_correct_types(async_client: AsyncClient):
    """Service fields are booleans, duration is a number, status is a string."""
    resp = await async_client.get("/health")
    data = resp.json()

    for field in ["mongodb_ok", "redis_ok", "influxdb_ok", "rabbitmq_ok",
                   "warehouse_loaded", "robot_loaded"]:
        assert isinstance(data[field], bool), (
            f"{field} should be bool, got {type(data[field])}: {data[field]}"
        )
    assert isinstance(data["check_duration_ms"], (int, float))
    assert isinstance(data["status"], str)


@pytest.mark.asyncio
async def test_health_mongodb_true_when_running(async_client: AsyncClient):
    """MongoDB IS running locally — mongodb_ok should be True."""
    resp = await async_client.get("/health")
    data = resp.json()
    assert data["mongodb_ok"] is True, (
        "MongoDB is running locally but mongodb_ok is False — check connection logic."
    )


@pytest.mark.asyncio
async def test_health_redis_true_when_running(async_client: AsyncClient):
    """Redis IS running locally — redis_ok should be True."""
    resp = await async_client.get("/health")
    data = resp.json()
    assert data["redis_ok"] is True


@pytest.mark.asyncio
async def test_health_influxdb_true_when_running(async_client: AsyncClient):
    """InfluxDB IS running locally — influxdb_ok should be True."""
    resp = await async_client.get("/health")
    data = resp.json()
    assert data["influxdb_ok"] is True


@pytest.mark.asyncio
async def test_health_configs_loaded(async_client: AsyncClient):
    """Warehouse and robot configs should be loaded on startup."""
    resp = await async_client.get("/health")
    data = resp.json()
    assert data["warehouse_loaded"] is True
    assert data["robot_loaded"] is True


@pytest.mark.asyncio
async def test_health_duration_is_positive(async_client: AsyncClient):
    """check_duration_ms should be >= 0."""
    resp = await async_client.get("/health")
    data = resp.json()
    assert data["check_duration_ms"] >= 0


@pytest.mark.asyncio
async def test_health_status_healthy_when_all_up(async_client: AsyncClient):
    """When MongoDB, Redis, InfluxDB are all running, status should be 'healthy'."""
    resp = await async_client.get("/health")
    data = resp.json()
    if data["mongodb_ok"] and data["redis_ok"] and data["influxdb_ok"]:
        assert data["status"] == "healthy"


# ---- Proof that checks are REAL: point at bad port → must return False ----

@pytest.mark.asyncio
async def test_health_mongodb_false_when_wrong_port(async_client_bad_mongo: AsyncClient):
    """
    THE CRITICAL TEST: point MongoDB at port 19999 (nothing listening).
    mongodb_ok MUST be False. This proves the check is real, not hardcoded.
    """
    resp = await async_client_bad_mongo.get("/health")
    data = resp.json()
    assert data["mongodb_ok"] is False, (
        "mongodb_ok should be False when pointed at wrong port. "
        "If True, the health check is hardcoded — violates project rules."
    )


@pytest.mark.asyncio
async def test_health_degraded_when_mongodb_down(async_client_bad_mongo: AsyncClient):
    """With MongoDB unreachable, overall status should be 'degraded'."""
    resp = await async_client_bad_mongo.get("/health")
    data = resp.json()
    assert data["status"] == "degraded"


# ---- Root endpoint ----

@pytest.mark.asyncio
async def test_root_endpoint(async_client: AsyncClient):
    """Root endpoint returns service info."""
    resp = await async_client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "Robotic Digital Twin API"
    assert data["version"] == "0.1.0"
    assert data["docs"] == "/docs"

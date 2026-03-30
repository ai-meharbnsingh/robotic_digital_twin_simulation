"""
Shared test fixtures for the Python test suite.
Sets environment variables and provides the FastAPI TestClient.

Tests that require running infrastructure (MongoDB, Redis, InfluxDB) use the
`requires_mongodb` marker and are automatically skipped when services are unavailable.
"""

import os
import socket
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Set env vars BEFORE importing app — config reads them at import time
os.environ["WAREHOUSE_CONFIG"] = "simple_grid"
os.environ["ROBOT_CONFIG"] = "differential_drive"
os.environ["MONGODB_URL"] = "mongodb://localhost:27017"
os.environ["REDIS_URL"] = "redis://localhost:6379"
os.environ["INFLUXDB_URL"] = "http://localhost:8086"


def _port_open(host: str, port: int, timeout: float = 0.3) -> bool:
    """Check if a TCP port is accepting connections."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (ConnectionRefusedError, TimeoutError, OSError):
        return False


# Detect infrastructure availability at collection time
MONGODB_AVAILABLE = _port_open("localhost", 27017)


@pytest.fixture
def requires_mongodb():
    """Skip test if MongoDB is not running."""
    if not MONGODB_AVAILABLE:
        pytest.skip("MongoDB not available (port 27017 closed)")


@pytest.fixture
def project_root() -> Path:
    """Return the project root directory."""
    return Path(__file__).resolve().parent.parent.parent


@pytest_asyncio.fixture
async def async_client():
    """
    Async test client for the FastAPI app.
    Uses httpx AsyncClient with ASGI transport.
    Manually runs the FastAPI lifespan so startup/shutdown hooks fire.
    """
    from app.main import app, lifespan

    # Manually enter the lifespan context so startup logic runs
    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client

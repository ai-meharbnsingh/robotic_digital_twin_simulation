"""
Configuration loader for the Robotic Digital Twin Simulation.

Reads all settings from environment variables.
Loads warehouse config (JSON) and robot config (YAML) from file paths
derived from env vars WAREHOUSE_CONFIG and ROBOT_CONFIG.
"""

import json
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings


# Project root: robotic_digital_twin_simulation/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """All environment-driven settings. No hardcoded values."""

    # --- Service URLs ---
    mongodb_url: str = Field(default="mongodb://localhost:27017")
    mongodb_database: str = Field(default="fleet_twin")
    redis_url: str = Field(default="redis://localhost:6379")
    influxdb_url: str = Field(default="http://localhost:8086")
    influxdb_token: str = Field(default="")
    influxdb_org: str = Field(default="robotic_twin")
    influxdb_bucket: str = Field(default="telemetry")
    rabbitmq_url: str = Field(default="amqp://guest:guest@localhost:5672/")

    # --- Config file names (resolved to configs/ directory) ---
    warehouse_config: str = Field(default="simple_grid")
    robot_config: str = Field(default="differential_drive")

    # --- Server settings ---
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8029)
    fms_host: str = Field(default="localhost")
    fms_port: int = Field(default=7012)

    # --- FMS TCP ---
    fms_tcp_port: int = Field(default=65123)

    # --- Auth ---
    api_key: str = Field(default="", description="API key for write endpoints. Empty = no auth.")

    model_config = {"env_prefix": "", "case_sensitive": False}


def load_warehouse_config(name: str) -> dict[str, Any]:
    """
    Load warehouse config from configs/warehouses/{name}.json.

    Args:
        name: Warehouse config name (without extension).

    Returns:
        Parsed JSON dict with nodes, edges, zones.

    Raises:
        FileNotFoundError: If the config file does not exist.
        json.JSONDecodeError: If the file is not valid JSON.
    """
    config_path = PROJECT_ROOT / "configs" / "warehouses" / f"{name}.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Warehouse config not found: {config_path}")
    with open(config_path, "r") as f:
        return json.load(f)


def load_robot_config(name: str) -> dict[str, Any]:
    """
    Load robot config from configs/robots/{name}.yaml.

    Args:
        name: Robot config name (without extension).

    Returns:
        Parsed YAML dict with motion, battery, sensors, etc.

    Raises:
        FileNotFoundError: If the config file does not exist.
        yaml.YAMLError: If the file is not valid YAML.
    """
    config_path = PROJECT_ROOT / "configs" / "robots" / f"{name}.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Robot config not found: {config_path}")
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def get_settings() -> Settings:
    """Create Settings from current environment variables."""
    return Settings()

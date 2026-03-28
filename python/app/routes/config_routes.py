"""
Config endpoint.
GET /api/config/robots — return robot configuration from YAML
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/config", tags=["config"])


def _get_robot_config() -> dict:
    from app.main import app_state
    return app_state.get("robot_config") or {}


@router.get("/robots")
async def robot_config():
    """Return the loaded robot configuration (from YAML)."""
    config = _get_robot_config()
    return {
        "config": config,
        "source": "yaml",
    }

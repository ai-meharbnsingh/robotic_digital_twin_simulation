"""
API key authentication for write endpoints.

When API_KEY env var is set, all mutating endpoints (POST, PUT, DELETE)
require the header: X-API-Key: <key>

When API_KEY is empty (default), auth is disabled (open simulation mode).
"""

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

from app.config import get_settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(
    api_key: str | None = Security(_api_key_header),
) -> None:
    """Dependency that enforces API key auth on write endpoints.

    Skipped when API_KEY setting is empty (simulation mode).
    """
    settings = get_settings()
    if not settings.api_key:
        return  # Auth disabled
    if api_key != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")

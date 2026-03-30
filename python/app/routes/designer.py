"""
Warehouse designer endpoints — validate, export, template management.

POST /api/designer/validate           — validate warehouse JSON config
POST /api/designer/export             — save designed warehouse as JSON config file
GET  /api/designer/templates          — list available templates (small, medium, large)
GET  /api/designer/templates/{name}   — get template JSON for editing

Phase 7: Warehouse Designer.
"""

import json
import logging
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_api_key
from pydantic import BaseModel, Field

from app.config import PROJECT_ROOT
from wes.warehouse_validator import WarehouseValidator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/designer", tags=["designer"])

WAREHOUSES_DIR = PROJECT_ROOT / "configs" / "warehouses"
TEMPLATE_PREFIX = "template_"

# Safety: limit config size to prevent abuse
MAX_NODES = 500
MAX_NAME_LENGTH = 100


# ── Pydantic models ──────────────────────────────────────────


class WarehouseConfig(BaseModel):
    """Warehouse config for validation."""
    name: str = Field(default="", max_length=200)
    nodes: list[dict] = Field(default_factory=list)
    edges: list[dict] = Field(default_factory=list)
    zones: list[dict] = Field(default_factory=list)
    grid_spacing_m: float = Field(default=2.0, ge=0.1, le=100.0)
    description: str = Field(default="")


class ExportRequest(BaseModel):
    """Request body for exporting a warehouse config."""
    name: str = Field(..., min_length=1, max_length=100, description="Filename (no extension)")
    config: dict = Field(..., description="Full warehouse config JSON")


# ── Endpoints ─────────────────────────────────────────────────


@router.post("/validate")
async def validate_warehouse(config: WarehouseConfig):
    """
    Validate a warehouse config JSON.

    Returns {valid: bool, errors: [...], warnings: [...]}.
    Does NOT save the config — use /export for that.
    """
    # Enforce safety limits before validation
    if len(config.nodes) > MAX_NODES:
        raise HTTPException(
            status_code=400,
            detail=f"Too many nodes: {len(config.nodes)} exceeds limit of {MAX_NODES}",
        )
    result = WarehouseValidator.validate(config.model_dump())
    return result


@router.post("/export", dependencies=[Depends(require_api_key)])
async def export_warehouse(body: ExportRequest):
    """
    Save a designed warehouse as a JSON config file.

    Validates the config first — rejects invalid configs with 400.
    Writes to configs/warehouses/{name}.json.
    """
    # Enforce name length limit
    if len(body.name) > MAX_NAME_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Name too long: {len(body.name)} exceeds limit of {MAX_NAME_LENGTH}",
        )

    # Sanitize filename — only allow alphanumeric, underscore, hyphen
    if not re.match(r'^[a-zA-Z0-9_-]+$', body.name):
        raise HTTPException(
            status_code=400,
            detail="Invalid name: only alphanumeric, underscore, and hyphen allowed",
        )

    # Enforce node count limit
    nodes = body.config.get("nodes", [])
    if len(nodes) > MAX_NODES:
        raise HTTPException(
            status_code=400,
            detail=f"Too many nodes: {len(nodes)} exceeds limit of {MAX_NODES}",
        )

    # Validate config before saving
    result = WarehouseValidator.validate(body.config)
    if not result["valid"]:
        raise HTTPException(
            status_code=400,
            detail=f"Config validation failed: {'; '.join(result['errors'])}",
        )

    # Save to disk
    output_path = WAREHOUSES_DIR / f"{body.name}.json"
    try:
        with open(output_path, "w") as f:
            json.dump(body.config, f, indent=2)
    except OSError as exc:
        logger.exception("Failed to write warehouse config: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to write config file")

    return {
        "saved": True,
        "path": str(output_path),
        "node_count": len(body.config.get("nodes", [])),
        "edge_count": len(body.config.get("edges", [])),
    }


@router.get("/templates")
async def list_templates():
    """
    List available warehouse templates.

    Returns array of {name, description, node_count} for each template_*.json.
    """
    templates = []
    for path in sorted(WAREHOUSES_DIR.glob(f"{TEMPLATE_PREFIX}*.json")):
        try:
            with open(path) as f:
                data = json.load(f)
            templates.append({
                "name": path.stem,
                "description": data.get("description", ""),
                "node_count": len(data.get("nodes", [])),
                "edge_count": len(data.get("edges", [])),
            })
        except (json.JSONDecodeError, OSError):
            logger.warning("Skipping invalid template: %s", path)
    return templates


@router.get("/templates/{name}")
async def get_template(name: str):
    """
    Get a specific template JSON for editing.

    Returns the full warehouse config JSON.
    """
    # Path traversal protection: reject names with slashes, dots, or non-alphanumeric chars
    if not name or "/" in name or "\\" in name or ".." in name or not all(
        c.isalnum() or c in ("_", "-") for c in name
    ):
        raise HTTPException(status_code=400, detail="Invalid template name")

    config_path = WAREHOUSES_DIR / f"{name}.json"
    # Verify resolved path stays within WAREHOUSES_DIR
    if not config_path.resolve().is_relative_to(WAREHOUSES_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Invalid template name")

    if not config_path.exists():
        raise HTTPException(status_code=404, detail=f"Template not found: {name}")

    try:
        with open(config_path) as f:
            return json.load(f)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail=f"Template file is invalid JSON: {name}")

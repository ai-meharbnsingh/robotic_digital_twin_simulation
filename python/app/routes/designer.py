"""
Warehouse designer endpoints — validate, export, template management.

POST /api/designer/validate           — validate warehouse JSON config
POST /api/designer/export             — save designed warehouse as JSON config file
GET  /api/designer/templates          — list available templates (small, medium, large)
GET  /api/designer/templates/{name}   — get template JSON for editing

Phase 15 additions:
POST /api/designer/import             — import existing warehouse JSON back into editor format
POST /api/designer/validate-3d        — validate 3D layout with conveyor paths
POST /api/designer/export-all         — export warehouse JSON + conveyor YAML + fleet config
GET  /api/designer/templates/categories — list template categories
POST /api/designer/auto-edges         — auto-generate edges between nearby nodes
POST /api/designer/template/scale     — scale a template warehouse up/down

Phase 7+15: Warehouse Designer v2.
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
from designer.layout_generator import LayoutGenerator
from designer.conveyor_designer import ConveyorDesigner

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


class ImportRequest(BaseModel):
    """Request body for importing warehouse JSON back into editor format."""
    config: dict = Field(..., description="Warehouse config JSON to import")


class Validate3DRequest(BaseModel):
    """Request body for 3D layout validation with conveyor paths."""
    config: dict = Field(..., description="Full warehouse config JSON")
    conveyor_waypoints: list[dict] = Field(
        default_factory=list,
        description="List of conveyor waypoints [{x, y}, ...]",
    )
    fleet_size: int = Field(default=5, ge=0, le=200, description="Number of robots")


class ExportAllRequest(BaseModel):
    """Request body for combined export (warehouse + conveyor + fleet)."""
    name: str = Field(..., min_length=1, max_length=100, description="Export name")
    config: dict = Field(..., description="Full warehouse config JSON")
    conveyor_waypoints: list[dict] = Field(
        default_factory=list,
        description="Conveyor waypoints [{x, y}, ...]",
    )
    fleet_size: int = Field(default=5, ge=0, le=200)


class AutoEdgesRequest(BaseModel):
    """Request body for auto-generating edges between nearby nodes."""
    nodes: list[dict] = Field(..., description="List of nodes with name, x, y")
    max_distance: float = Field(..., gt=0, le=1000, description="Max Euclidean distance for auto-connection")


class TemplateScaleRequest(BaseModel):
    """Request body for scaling a template warehouse."""
    template_name: str = Field(..., min_length=1, max_length=100, description="Template filename (no extension)")
    scale_factor: float = Field(..., gt=0, le=100, description="Scale multiplier (>1 = bigger, <1 = smaller)")


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


@router.post("/auto-edges")
async def auto_generate_edges(body: AutoEdgesRequest):
    """
    Auto-generate edges between nodes within max_distance.

    Accepts a list of nodes and a max_distance, returns generated edges.
    """
    if len(body.nodes) > MAX_NODES:
        raise HTTPException(
            status_code=400,
            detail=f"Too many nodes: {len(body.nodes)} exceeds limit of {MAX_NODES}",
        )

    edges = LayoutGenerator.auto_generate_edges(body.nodes, body.max_distance)
    return {
        "edges": edges,
        "edge_count": len(edges),
        "node_count": len(body.nodes),
        "max_distance": body.max_distance,
    }


@router.post("/template/scale")
async def scale_template(body: TemplateScaleRequest):
    """
    Scale a template warehouse up/down by scale_factor.

    Loads the template by name, applies scaling, returns the scaled config.
    """
    # Sanitize template name
    if not re.match(r'^[a-zA-Z0-9_-]+$', body.template_name):
        raise HTTPException(
            status_code=400,
            detail="Invalid template name: only alphanumeric, underscore, and hyphen allowed",
        )

    config_path = WAREHOUSES_DIR / f"{body.template_name}.json"
    if not config_path.resolve().is_relative_to(WAREHOUSES_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Invalid template name")

    if not config_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Template not found: {body.template_name}",
        )

    try:
        with open(config_path) as f:
            template = json.load(f)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail=f"Template file is invalid JSON: {body.template_name}",
        )

    scaled = LayoutGenerator.generate_from_template(template, body.scale_factor)
    return {
        "config": scaled,
        "template_name": body.template_name,
        "scale_factor": body.scale_factor,
        "node_count": len(scaled.get("nodes", [])),
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


# NOTE: /templates/categories MUST be registered BEFORE /templates/{name}
# so FastAPI doesn't match "categories" as a path parameter.
@router.get("/templates/categories")
async def list_template_categories():
    """
    List template categories.

    Scans template files and groups them by category
    based on size (node count) and naming convention.
    Returns: [{category, templates: [{name, node_count}]}]
    """
    # Category definitions with node count ranges
    categories = {
        "small": {"label": "Small (< 15 nodes)", "min": 0, "max": 14, "templates": []},
        "medium": {"label": "Medium (15-30 nodes)", "min": 15, "max": 30, "templates": []},
        "large": {"label": "Large (31-60 nodes)", "min": 31, "max": 60, "templates": []},
        "addverb": {"label": "Addverb Presets", "min": 0, "max": 9999, "templates": []},
    }

    for path in sorted(WAREHOUSES_DIR.glob("*.json")):
        if path.stem.startswith("_"):
            continue
        try:
            with open(path) as f:
                data = json.load(f)
            node_count = len(data.get("nodes", []))
            entry = {
                "name": path.stem,
                "description": data.get("description", ""),
                "node_count": node_count,
            }

            # Addverb templates identified by name
            if "addverb" in path.stem.lower():
                categories["addverb"]["templates"].append(entry)
            elif node_count <= 14:
                categories["small"]["templates"].append(entry)
            elif node_count <= 30:
                categories["medium"]["templates"].append(entry)
            else:
                categories["large"]["templates"].append(entry)
        except (json.JSONDecodeError, OSError):
            logger.warning("Skipping invalid template: %s", path)

    return [
        {"category": key, "label": cat["label"], "templates": cat["templates"]}
        for key, cat in categories.items()
    ]


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


@router.post("/import")
async def import_warehouse(body: ImportRequest):
    """
    Import existing warehouse JSON back into editor format.

    Parses the config and returns enriched data suitable for the
    3D editor: node positions, edge data, auto-detected zones,
    connectivity info, and layout metrics.
    """
    config = body.config
    nodes = config.get("nodes", [])
    edges = config.get("edges", [])

    if not nodes:
        raise HTTPException(status_code=400, detail="Config has no nodes")

    if len(nodes) > MAX_NODES:
        raise HTTPException(
            status_code=400,
            detail=f"Too many nodes: {len(nodes)} exceeds limit of {MAX_NODES}",
        )

    # Validate basic structure
    result = WarehouseValidator.validate(config)

    # Auto-detect zones if none provided
    zones = config.get("zones", [])
    if not zones:
        zones = LayoutGenerator.auto_detect_zones(nodes)

    # Check connectivity
    connectivity = LayoutGenerator.validate_connectivity(nodes, edges)

    # Calculate metrics
    metrics = LayoutGenerator.calculate_metrics(config)

    return {
        "name": config.get("name", "Imported Layout"),
        "description": config.get("description", ""),
        "nodes": nodes,
        "edges": edges,
        "zones": zones,
        "grid_spacing_m": config.get("grid_spacing_m", 2.0),
        "validation": result,
        "connectivity": connectivity,
        "metrics": metrics,
    }


@router.post("/validate-3d")
async def validate_3d_layout(body: Validate3DRequest):
    """
    Validate 3D layout with conveyor paths.

    Performs warehouse validation + connectivity check + conveyor topology
    validation + charge station recommendations.
    """
    config = body.config
    nodes = config.get("nodes", [])
    edges = config.get("edges", [])

    if len(nodes) > MAX_NODES:
        raise HTTPException(
            status_code=400,
            detail=f"Too many nodes: {len(nodes)} exceeds limit of {MAX_NODES}",
        )

    # Warehouse validation
    warehouse_result = WarehouseValidator.validate(config)

    # Connectivity check
    connectivity = LayoutGenerator.validate_connectivity(nodes, edges)

    # Conveyor topology validation
    conveyor_result = {"valid": True, "errors": [], "warnings": []}
    if body.conveyor_waypoints:
        designer = ConveyorDesigner()
        designer.generate_conveyor_layout(body.conveyor_waypoints)
        conveyor_result = designer.validate_topology()

    # Charge station suggestions
    charge_suggestions = LayoutGenerator.suggest_charge_stations(
        nodes, body.fleet_size
    )

    # Metrics
    metrics = LayoutGenerator.calculate_metrics(config)

    # Overall validity: warehouse + connectivity + conveyor all pass
    overall_valid = (
        warehouse_result["valid"]
        and connectivity["connected"]
        and conveyor_result["valid"]
    )

    return {
        "valid": overall_valid,
        "warehouse_validation": warehouse_result,
        "connectivity": connectivity,
        "conveyor_validation": conveyor_result,
        "charge_suggestions": charge_suggestions,
        "metrics": metrics,
    }


@router.post("/export-all", dependencies=[Depends(require_api_key)])
async def export_all(body: ExportAllRequest):
    """
    Export warehouse JSON + conveyor YAML + fleet config as combined package.

    Saves:
      - configs/warehouses/{name}.json — warehouse layout
      - configs/wcs/{name}_conveyor.yaml — conveyor layout (if waypoints given)
      - configs/fleet/{name}_fleet.json — fleet config

    Returns summary of saved files.
    """
    # Sanitize filename
    if not re.match(r'^[a-zA-Z0-9_-]+$', body.name):
        raise HTTPException(
            status_code=400,
            detail="Invalid name: only alphanumeric, underscore, and hyphen allowed",
        )

    nodes = body.config.get("nodes", [])
    if len(nodes) > MAX_NODES:
        raise HTTPException(
            status_code=400,
            detail=f"Too many nodes: {len(nodes)} exceeds limit of {MAX_NODES}",
        )

    # Validate warehouse before saving
    result = WarehouseValidator.validate(body.config)
    if not result["valid"]:
        raise HTTPException(
            status_code=400,
            detail=f"Config validation failed: {'; '.join(result['errors'])}",
        )

    saved_files: list[str] = []
    failures: list[str] = []

    # 1. Save warehouse JSON
    wh_path = WAREHOUSES_DIR / f"{body.name}.json"
    try:
        with open(wh_path, "w") as f:
            json.dump(body.config, f, indent=2)
        saved_files.append(str(wh_path))
    except OSError as exc:
        logger.exception("Failed to write warehouse config: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to write warehouse config")

    # 2. Save conveyor YAML (if waypoints provided)
    conveyor_yaml_content = ""
    if body.conveyor_waypoints and len(body.conveyor_waypoints) >= 2:
        designer = ConveyorDesigner()
        designer.generate_conveyor_layout(body.conveyor_waypoints)

        # Validate conveyor topology before saving
        topo = designer.validate_topology()
        if not topo.get("valid", True):
            failures.append(f"Conveyor topology invalid: {topo.get('errors', [])}")

        conveyor_yaml_content = designer.export_yaml()

        wcs_dir = PROJECT_ROOT / "configs" / "wcs"
        wcs_dir.mkdir(parents=True, exist_ok=True)
        conv_path = wcs_dir / f"{body.name}_conveyor.yaml"
        try:
            with open(conv_path, "w") as f:
                f.write(conveyor_yaml_content)
            saved_files.append(str(conv_path))
        except OSError as exc:
            logger.exception("Failed to write conveyor config: %s", exc)
            failures.append(f"conveyor: {exc}")

    # 3. Save fleet config
    charge_suggestions = LayoutGenerator.suggest_charge_stations(
        nodes, body.fleet_size
    )
    fleet_config = {
        "fleet_size": body.fleet_size,
        "charge_stations": charge_suggestions,
        "warehouse": body.name,
    }
    fleet_dir = PROJECT_ROOT / "configs" / "fleet"
    fleet_dir.mkdir(parents=True, exist_ok=True)
    fleet_path = fleet_dir / f"{body.name}_fleet.json"
    try:
        with open(fleet_path, "w") as f:
            json.dump(fleet_config, f, indent=2)
        saved_files.append(str(fleet_path))
    except OSError as exc:
        logger.exception("Failed to write fleet config: %s", exc)
        failures.append(f"fleet: {exc}")

    all_saved = len(failures) == 0
    result: dict = {
        "saved": all_saved,
        "files": saved_files,
        "node_count": len(nodes),
        "edge_count": len(body.config.get("edges", [])),
        "conveyor_segments": len(body.conveyor_waypoints) - 1 if len(body.conveyor_waypoints) >= 2 else 0,
        "fleet_size": body.fleet_size,
    }
    if failures:
        result["failures"] = failures

    return result

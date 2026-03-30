"""
WCS (Warehouse Control System) endpoints.

Conveyor control, sorter routing, lane management, package tracking.

Phase 13: Full WCS implementation.

GET  /api/wcs/conveyors                    — all conveyor segments with state
GET  /api/wcs/conveyors/{id}/status        — single conveyor status
POST /api/wcs/conveyors/{id}/control       — start/stop/speed/maintenance
POST /api/wcs/conveyors/{id}/jam           — trigger/clear jam
POST /api/wcs/conveyors/start-all          — start all segments
POST /api/wcs/conveyors/stop-all           — emergency stop all
GET  /api/wcs/sorter/rules                 — sort routing rules
POST /api/wcs/sorter/rules                 — add routing rule
POST /api/wcs/sorter/sort                  — sort a package (determine lane)
GET  /api/wcs/sorter/stats                 — sorter statistics
GET  /api/wcs/lanes                        — all lanes with status
GET  /api/wcs/lanes/{id}                   — single lane
POST /api/wcs/lanes/{id}/package           — add/remove package from lane
GET  /api/wcs/packages/{tracking_id}       — track a package
GET  /api/wcs/packages/in-transit          — all packages in transit
POST /api/wcs/packages                     — create new package
GET  /api/wcs/stats                        — system-wide WCS stats
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from app.auth import require_api_key

router = APIRouter(prefix="/api/wcs", tags=["wcs"])

MAX_PACKAGES = 10000
MAX_RULES = 500


def _get_wcs():
    """Get WCS components from app_state."""
    from app.main import app_state
    return {
        "conveyor": app_state.get("wcs_conveyor"),
        "sorter": app_state.get("wcs_sorter"),
        "lanes": app_state.get("wcs_lanes"),
        "tracker": app_state.get("wcs_tracker"),
    }


# ── Request Models ──────────────────────────────────────


class ConveyorControlRequest(BaseModel):
    action: str = Field(..., description="start, stop, set_speed, maintenance_on, maintenance_off")
    speed_mps: Optional[float] = Field(None, ge=0.0, le=5.0)


class JamRequest(BaseModel):
    action: str = Field(..., description="trigger or clear")
    reason: Optional[str] = Field("manual", max_length=200)


class SortRuleRequest(BaseModel):
    pattern: str = Field(..., min_length=1, max_length=100)
    target_lane: str = Field(..., min_length=1, max_length=50)
    priority: int = Field(0, ge=0, le=100)


class SortPackageRequest(BaseModel):
    package_id: str = Field(..., min_length=1, max_length=50)
    # No min_length: empty barcode ("") is a valid MISREAD case handled by SorterEngine
    barcode: str = Field(..., max_length=200)


class CreatePackageRequest(BaseModel):
    barcode: str = Field(..., min_length=1, max_length=200)
    order_id: Optional[str] = Field(None, max_length=50)
    sku: Optional[str] = Field(None, max_length=100)
    weight_kg: float = Field(0.0, ge=0.0, le=5000.0)


class LanePackageRequest(BaseModel):
    action: str = Field(..., description="add or remove")
    package_id: Optional[str] = Field(None, max_length=50)


class LaneControlRequest(BaseModel):
    action: str = Field(..., description="close or open")


# ── Conveyor Endpoints ──────────────────────────────────


@router.get("/conveyors")
async def list_conveyors():
    """List all conveyor segments with current state."""
    wcs = _get_wcs()
    if wcs["conveyor"] is None:
        return []
    return wcs["conveyor"].get_all_segments()


@router.get("/conveyors/{segment_id}/status")
async def get_conveyor_status(segment_id: str):
    """Get single conveyor segment status."""
    wcs = _get_wcs()
    if wcs["conveyor"] is None:
        raise HTTPException(status_code=503, detail="WCS not initialized")
    seg = wcs["conveyor"].get_segment(segment_id)
    if seg is None:
        raise HTTPException(status_code=404, detail=f"Segment '{segment_id}' not found")
    return seg.to_dict()


@router.post("/conveyors/{segment_id}/control", dependencies=[Depends(require_api_key)])
async def control_conveyor(segment_id: str, body: ConveyorControlRequest):
    """Control a conveyor segment: start, stop, set_speed, maintenance."""
    wcs = _get_wcs()
    if wcs["conveyor"] is None:
        raise HTTPException(status_code=503, detail="WCS not initialized")

    conv = wcs["conveyor"]
    if body.action == "start":
        return conv.start_segment(segment_id, body.speed_mps)
    elif body.action == "stop":
        return conv.stop_segment(segment_id)
    elif body.action == "set_speed":
        seg = conv.get_segment(segment_id)
        if seg is None:
            raise HTTPException(status_code=404, detail="Segment not found")
        return seg.set_speed(body.speed_mps or 1.0)
    elif body.action == "maintenance_on":
        seg = conv.get_segment(segment_id)
        if seg is None:
            raise HTTPException(status_code=404, detail="Segment not found")
        return seg.set_maintenance(True)
    elif body.action == "maintenance_off":
        seg = conv.get_segment(segment_id)
        if seg is None:
            raise HTTPException(status_code=404, detail="Segment not found")
        return seg.set_maintenance(False)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")


@router.post("/conveyors/{segment_id}/jam", dependencies=[Depends(require_api_key)])
async def jam_control(segment_id: str, body: JamRequest):
    """Trigger or clear a jam on a conveyor segment."""
    wcs = _get_wcs()
    if wcs["conveyor"] is None:
        raise HTTPException(status_code=503, detail="WCS not initialized")

    if body.action == "trigger":
        return wcs["conveyor"].trigger_jam(segment_id, body.reason or "manual")
    elif body.action == "clear":
        return wcs["conveyor"].clear_jam(segment_id)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")


@router.post("/conveyors/start-all", dependencies=[Depends(require_api_key)])
async def start_all_conveyors():
    """Start all conveyor segments."""
    wcs = _get_wcs()
    if wcs["conveyor"] is None:
        raise HTTPException(status_code=503, detail="WCS not initialized")
    return wcs["conveyor"].start_all()


@router.post("/conveyors/stop-all", dependencies=[Depends(require_api_key)])
async def stop_all_conveyors():
    """Emergency stop all conveyor segments."""
    wcs = _get_wcs()
    if wcs["conveyor"] is None:
        raise HTTPException(status_code=503, detail="WCS not initialized")
    return wcs["conveyor"].stop_all()


class TransferRequest(BaseModel):
    package_id: str = Field(..., min_length=1, max_length=50)
    from_segment: str = Field(..., min_length=1, max_length=50)
    to_segment: str = Field(..., min_length=1, max_length=50)


@router.post("/conveyors/transfer", dependencies=[Depends(require_api_key)])
async def transfer_package(body: TransferRequest):
    """Transfer a package between conveyor segments."""
    wcs = _get_wcs()
    if wcs["conveyor"] is None:
        raise HTTPException(status_code=503, detail="WCS not initialized")
    return wcs["conveyor"].transfer_package(body.package_id, body.from_segment, body.to_segment)


# ── Sorter Endpoints ────────────────────────────────────


@router.get("/sorter/rules")
async def get_sort_rules():
    """Get all sort routing rules."""
    wcs = _get_wcs()
    if wcs["sorter"] is None:
        return []
    return wcs["sorter"].get_rules()


@router.post("/sorter/rules", dependencies=[Depends(require_api_key)])
async def add_sort_rule(body: SortRuleRequest):
    """Add a new sort routing rule."""
    wcs = _get_wcs()
    if wcs["sorter"] is None:
        raise HTTPException(status_code=503, detail="WCS not initialized")
    if len(wcs["sorter"].get_rules()) >= MAX_RULES:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_RULES} rules reached")
    rule = wcs["sorter"].add_rule(body.pattern, body.target_lane, body.priority)
    return rule.to_dict()


@router.delete("/sorter/rules/{rule_id}", dependencies=[Depends(require_api_key)])
async def delete_sort_rule(rule_id: str):
    """Delete a sort routing rule."""
    wcs = _get_wcs()
    if wcs["sorter"] is None:
        raise HTTPException(status_code=503, detail="WCS not initialized")
    removed = wcs["sorter"].remove_rule(rule_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
    return {"ok": True, "deleted": rule_id}


@router.get("/sorter/log")
async def get_sort_log(limit: int = 50):
    """Get recent sort log entries."""
    wcs = _get_wcs()
    if wcs["sorter"] is None:
        return []
    return wcs["sorter"].get_recent_log(min(limit, 200))


@router.post("/sorter/sort", dependencies=[Depends(require_api_key)])
async def sort_package(body: SortPackageRequest):
    """Sort a package — determine target lane based on barcode."""
    wcs = _get_wcs()
    if wcs["sorter"] is None:
        raise HTTPException(status_code=503, detail="WCS not initialized")
    capacities = wcs["lanes"].get_capacities() if wcs["lanes"] else None
    return wcs["sorter"].sort_package(body.package_id, body.barcode, capacities)


@router.get("/sorter/stats")
async def get_sorter_stats():
    """Get sorter statistics."""
    wcs = _get_wcs()
    if wcs["sorter"] is None:
        return {}
    return wcs["sorter"].get_stats()


@router.get("/sorter/diverts")
async def get_divert_points():
    """Get all divert points."""
    wcs = _get_wcs()
    if wcs["sorter"] is None:
        return []
    return wcs["sorter"].get_diverts()


# ── Lane Endpoints ──────────────────────────────────────


@router.get("/lanes")
async def list_lanes():
    """List all warehouse lanes with status."""
    wcs = _get_wcs()
    if wcs["lanes"] is None:
        return []
    return wcs["lanes"].get_all_lanes()


@router.get("/lanes/by-type/{lane_type}")
async def lanes_by_type(lane_type: str):
    """Filter lanes by type (inbound, outbound, express, returns, staging)."""
    wcs = _get_wcs()
    if wcs["lanes"] is None:
        return []
    from wcs.lane_manager import LaneType
    try:
        lt = LaneType(lane_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid lane type: {lane_type}")
    return wcs["lanes"].get_lanes_by_type(lt)


@router.post("/lanes/{lane_id}/control", dependencies=[Depends(require_api_key)])
async def control_lane(lane_id: str, body: LaneControlRequest):
    """Open or close a lane."""
    wcs = _get_wcs()
    if wcs["lanes"] is None:
        raise HTTPException(status_code=503, detail="WCS not initialized")
    lane = wcs["lanes"].get_lane(lane_id)
    if lane is None:
        raise HTTPException(status_code=404, detail=f"Lane '{lane_id}' not found")
    if body.action == "close":
        return lane.close()
    elif body.action == "open":
        return lane.open()
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")


@router.get("/lanes/{lane_id}")
async def get_lane(lane_id: str):
    """Get single lane status."""
    wcs = _get_wcs()
    if wcs["lanes"] is None:
        raise HTTPException(status_code=503, detail="WCS not initialized")
    lane = wcs["lanes"].get_lane(lane_id)
    if lane is None:
        raise HTTPException(status_code=404, detail=f"Lane '{lane_id}' not found")
    return lane.to_dict()


@router.post("/lanes/{lane_id}/package", dependencies=[Depends(require_api_key)])
async def lane_package(lane_id: str, body: LanePackageRequest):
    """Add or remove package from a lane."""
    wcs = _get_wcs()
    if wcs["lanes"] is None:
        raise HTTPException(status_code=503, detail="WCS not initialized")
    if body.action == "add":
        if not body.package_id:
            raise HTTPException(status_code=400, detail="package_id required for add")
        return wcs["lanes"].add_package_to_lane(lane_id, body.package_id)
    elif body.action == "remove":
        return wcs["lanes"].remove_package_from_lane(lane_id, body.package_id)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")


# ── Package Tracking Endpoints ──────────────────────────


@router.post("/packages", dependencies=[Depends(require_api_key)])
async def create_package(body: CreatePackageRequest):
    """Create a new package for tracking."""
    wcs = _get_wcs()
    if wcs["tracker"] is None:
        raise HTTPException(status_code=503, detail="WCS not initialized")
    stats = wcs["tracker"].get_stats()
    if stats["total_packages"] >= MAX_PACKAGES:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_PACKAGES} packages reached")
    pid = wcs["tracker"].create_package(
        barcode=body.barcode,
        order_id=body.order_id,
        sku=body.sku,
        weight_kg=body.weight_kg,
    )
    return {"package_id": pid, "barcode": body.barcode}


@router.get("/packages/in-transit")
async def get_in_transit():
    """Get all packages currently in transit."""
    wcs = _get_wcs()
    if wcs["tracker"] is None:
        return []
    return wcs["tracker"].get_in_transit()


@router.get("/packages/by-barcode")
async def find_by_barcode(barcode: str):
    """Find packages by barcode."""
    wcs = _get_wcs()
    if wcs["tracker"] is None:
        return []
    return wcs["tracker"].find_by_barcode(barcode)


@router.get("/packages/at-location")
async def packages_at_location(location: str):
    """Find packages at a specific location."""
    wcs = _get_wcs()
    if wcs["tracker"] is None:
        return []
    return wcs["tracker"].get_packages_at_location(location)


@router.get("/packages/{tracking_id}")
async def track_package(tracking_id: str):
    """Track a package — full journey with events."""
    wcs = _get_wcs()
    if wcs["tracker"] is None:
        raise HTTPException(status_code=503, detail="WCS not initialized")
    pkg = wcs["tracker"].get_package(tracking_id)
    if pkg is None:
        raise HTTPException(status_code=404, detail=f"Package '{tracking_id}' not found")
    return pkg


# ── System Stats ────────────────────────────────────────


@router.get("/stats")
async def get_wcs_stats():
    """System-wide WCS statistics."""
    wcs = _get_wcs()
    result = {}
    if wcs["conveyor"]:
        result["conveyors"] = wcs["conveyor"].get_stats()
    if wcs["sorter"]:
        result["sorter"] = wcs["sorter"].get_stats()
    if wcs["lanes"]:
        result["lanes"] = wcs["lanes"].get_stats()
    if wcs["tracker"]:
        result["packages"] = wcs["tracker"].get_stats()
    return result

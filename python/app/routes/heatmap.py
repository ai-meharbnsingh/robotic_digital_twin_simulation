"""
Heatmap endpoint — spatial traffic density for warehouse visualization.

GET /api/analytics/heatmap — returns grid cells with visit counts and dwell times.
Queries InfluxDB for historical robot positions. Falls back to MongoDB telemetry
or simulated data from warehouse config when services are unavailable.

Phase 3: Heat Map Visualization.
"""

import asyncio
import math
import time
from typing import Optional

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _get_db():
    from app.main import app_state
    return app_state.get("mongo_db")


def _get_influx():
    from app.main import app_state
    return app_state.get("influx_writer")


def _get_warehouse_config():
    from app.main import app_state
    return app_state.get("warehouse_config") or {}


def _compute_bounds(warehouse_config: dict) -> tuple[float, float, float, float]:
    """Compute warehouse bounds from node positions."""
    nodes = warehouse_config.get("nodes", [])
    if not nodes:
        return 0.0, 0.0, 10.0, 10.0

    xs = [n.get("x", 0) for n in nodes]
    ys = [n.get("y", 0) for n in nodes]
    return min(xs), min(ys), max(xs), max(ys)


def _bin_positions(
    positions: list[dict],
    min_x: float,
    min_y: float,
    resolution_m: float,
) -> dict[tuple[int, int], dict]:
    """
    Bin a list of {x, y, duration_s} records into grid cells.

    Returns dict mapping (col, row) → {visit_count, total_dwell_s}.
    """
    cells: dict[tuple[int, int], dict] = {}

    for pos in positions:
        x = pos.get("x", 0.0)
        y = pos.get("y", 0.0)
        duration = pos.get("duration_s", 1.0)

        col = int((x - min_x) / resolution_m)
        row = int((y - min_y) / resolution_m)

        key = (col, row)
        if key not in cells:
            cells[key] = {"visit_count": 0, "total_dwell_s": 0.0}
        cells[key]["visit_count"] += 1
        cells[key]["total_dwell_s"] += duration

    return cells


def _compute_zone_congestion(
    cells: dict[tuple[int, int], dict],
    warehouse_config: dict,
    min_x: float,
    min_y: float,
    resolution_m: float,
) -> list[dict]:
    """
    Compute congestion score per zone.

    Score = total visits in zone nodes / number of zone nodes.
    Higher score = more congested.
    """
    zones = warehouse_config.get("zones", [])
    nodes_by_name = {
        n.get("name", ""): n for n in warehouse_config.get("nodes", [])
    }

    zone_scores = []
    for zone in zones:
        zone_name = zone.get("name", "")
        zone_type = zone.get("type", "")
        zone_nodes = zone.get("nodes", [])

        total_visits = 0
        total_dwell = 0.0
        node_count = 0

        for node_name in zone_nodes:
            node = nodes_by_name.get(node_name)
            if not node:
                continue

            nx = node.get("x", 0)
            ny = node.get("y", 0)
            col = int((nx - min_x) / resolution_m)
            row = int((ny - min_y) / resolution_m)

            cell = cells.get((col, row))
            if cell:
                total_visits += cell["visit_count"]
                total_dwell += cell["total_dwell_s"]
            node_count += 1

        avg_visits = total_visits / max(1, node_count)
        avg_dwell = total_dwell / max(1, node_count)

        zone_scores.append({
            "zone_name": zone_name,
            "zone_type": zone_type,
            "node_count": node_count,
            "total_visits": total_visits,
            "avg_visits_per_node": round(avg_visits, 1),
            "avg_dwell_time_s": round(avg_dwell, 1),
            "congestion_score": round(avg_visits * avg_dwell / 100.0, 2),
        })

    # Sort by congestion score descending
    zone_scores.sort(key=lambda z: z["congestion_score"], reverse=True)
    return zone_scores


async def _get_positions_from_influx(
    influx_writer, duration_hours: int
) -> Optional[list[dict]]:
    """Query InfluxDB for robot positions over the time window."""
    if not influx_writer or not influx_writer.is_available:
        return None

    try:
        client = influx_writer._client
        query_api = client.query_api()

        flux_query = f"""
        from(bucket: "{influx_writer.bucket}")
          |> range(start: -{duration_hours}h)
          |> filter(fn: (r) => r._measurement == "robot_position")
          |> filter(fn: (r) => r._field == "x" or r._field == "y")
          |> pivot(rowKey: ["_time", "robot_id"], columnKey: ["_field"], valueColumn: "_value")
          |> keep(columns: ["_time", "robot_id", "x", "y"])
        """

        tables = query_api.query(flux_query, org=influx_writer.org)

        positions = []
        for table in tables:
            for record in table.records:
                positions.append({
                    "x": record.values.get("x", 0.0),
                    "y": record.values.get("y", 0.0),
                    "duration_s": 1.0,
                })

        return positions if positions else None
    except Exception:
        return None


async def _get_positions_from_mongo(db, duration_hours: int) -> Optional[list[dict]]:
    """Query MongoDB telemetry collection for position history."""
    if db is None:
        return None

    try:
        cutoff = time.time() - (duration_hours * 3600)

        cursor = db["telemetry"].find(
            {
                "measurement": "robot_position",
                "timestamp": {"$gte": cutoff},
            },
            {"_id": 0, "fields.x": 1, "fields.y": 1},
        )
        docs = await cursor.to_list(length=100000)

        if not docs:
            return None

        positions = []
        for doc in docs:
            fields = doc.get("fields", {})
            if "x" in fields and "y" in fields:
                positions.append({
                    "x": fields["x"],
                    "y": fields["y"],
                    "duration_s": 1.0,
                })

        return positions if positions else None
    except Exception:
        return None


def _generate_simulated_positions(warehouse_config: dict) -> list[dict]:
    """
    Generate simulated position data from warehouse node topology.

    Uses node types to simulate realistic traffic patterns:
    - Pick/drop stations: high traffic (many visits)
    - Aisle nodes: medium traffic (transit)
    - Shelf nodes: medium-low traffic (dwell time)
    - Charge/dock nodes: low traffic
    - Hub: high traffic (routing crossroads)
    """
    import random
    random.seed(42)  # Reproducible for testing

    traffic_weights = {
        "pick": 20,
        "drop": 18,
        "hub": 15,
        "aisle": 8,
        "shelf": 5,
        "charge": 3,
        "lane": 7,
    }

    dwell_ranges = {
        "pick": (3.0, 15.0),
        "drop": (2.0, 10.0),
        "hub": (0.5, 2.0),
        "aisle": (0.3, 1.5),
        "shelf": (5.0, 30.0),
        "charge": (60.0, 300.0),
        "lane": (0.3, 1.5),
    }

    positions = []
    nodes = warehouse_config.get("nodes", [])

    for node in nodes:
        node_type = node.get("type", "aisle")
        x = node.get("x", 0)
        y = node.get("y", 0)
        weight = traffic_weights.get(node_type, 5)
        dwell_min, dwell_max = dwell_ranges.get(node_type, (1.0, 5.0))

        # Generate visit_count proportional to traffic weight
        visits = random.randint(max(1, weight - 3), weight + 5)
        for _ in range(visits):
            # Slight position jitter (robots don't stop at exact node coords)
            jx = x + random.gauss(0, 0.15)
            jy = y + random.gauss(0, 0.15)
            dwell = random.uniform(dwell_min, dwell_max)
            positions.append({"x": jx, "y": jy, "duration_s": dwell})

    return positions


@router.get("/heatmap")
async def get_heatmap(
    duration: str = Query(
        "1h",
        description="Time window: 1h, 4h, 8h, or 24h",
        pattern=r"^(1|4|8|24)h$",
    ),
    resolution: float = Query(
        0.5,
        ge=0.1,
        le=5.0,
        description="Grid cell size in meters (0.1-5.0)",
    ),
):
    """
    Return a heat map of robot traffic density.

    Bins robot positions into grid cells and returns visit count + average
    dwell time per cell, plus per-zone congestion scores.

    Data source priority:
    1. InfluxDB (time-series position data)
    2. MongoDB telemetry collection
    3. Simulated data from warehouse node topology (demo/testing)
    """
    start_time = time.monotonic()

    # Parse duration
    duration_hours = int(duration.replace("h", ""))

    # Get warehouse config for bounds and zone info
    warehouse_config = _get_warehouse_config()
    min_x, min_y, max_x, max_y = _compute_bounds(warehouse_config)

    # Pad bounds slightly so edge nodes aren't clipped
    pad = resolution
    min_x -= pad
    min_y -= pad
    max_x += pad
    max_y += pad

    # Try data sources in priority order — check availability BEFORE querying
    # to avoid connection timeout latency when services are down.
    data_source = "simulated"
    positions = None

    # 1. Try InfluxDB (only if client is available)
    influx = _get_influx()
    if influx and influx.is_available:
        positions = await _get_positions_from_influx(influx, duration_hours)
        if positions:
            data_source = "influxdb"

    # 2. Try MongoDB telemetry (only if connected, with 200ms timeout)
    if positions is None:
        db = _get_db()
        if db is not None:
            try:
                positions = await asyncio.wait_for(
                    _get_positions_from_mongo(db, duration_hours),
                    timeout=0.2,
                )
                if positions:
                    data_source = "mongodb"
            except (asyncio.TimeoutError, Exception):
                positions = None

    # 3. Fall back to simulated data (instant, no I/O)
    if positions is None:
        positions = _generate_simulated_positions(warehouse_config)
        data_source = "simulated"

    # Bin positions into grid cells
    cells_raw = _bin_positions(positions, min_x, min_y, resolution)

    # Convert to output format
    cols = int(math.ceil((max_x - min_x) / resolution))
    rows = int(math.ceil((max_y - min_y) / resolution))

    cells = []
    max_visits = max((c["visit_count"] for c in cells_raw.values()), default=1)

    for (col, row), data in cells_raw.items():
        cell_x = min_x + col * resolution + resolution / 2  # cell center
        cell_y = min_y + row * resolution + resolution / 2
        avg_dwell = data["total_dwell_s"] / max(1, data["visit_count"])
        intensity = data["visit_count"] / max(1, max_visits)  # 0.0-1.0

        cells.append({
            "x": round(cell_x, 3),
            "y": round(cell_y, 3),
            "col": col,
            "row": row,
            "visit_count": data["visit_count"],
            "avg_dwell_time_s": round(avg_dwell, 2),
            "intensity": round(intensity, 3),
        })

    # Sort by intensity descending (hottest first)
    cells.sort(key=lambda c: c["intensity"], reverse=True)

    # Compute zone congestion scores
    zone_congestion = _compute_zone_congestion(
        cells_raw, warehouse_config, min_x, min_y, resolution
    )

    elapsed_ms = round((time.monotonic() - start_time) * 1000, 1)

    return {
        "duration": duration,
        "resolution_m": resolution,
        "data_source": data_source,
        "grid": {
            "min_x": round(min_x, 3),
            "min_y": round(min_y, 3),
            "max_x": round(max_x, 3),
            "max_y": round(max_y, 3),
            "cols": cols,
            "rows": rows,
        },
        "cells": cells,
        "total_positions": len(positions),
        "cell_count": len(cells),
        "zones": zone_congestion,
        "query_ms": elapsed_ms,
    }

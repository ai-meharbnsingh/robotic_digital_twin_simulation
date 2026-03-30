"""
Tests for Phase 15 — Warehouse Designer v2 (LayoutGenerator + ConveyorDesigner).

LayoutGenerator:
  auto_generate_edges  — connect nearby nodes within max_distance
  auto_detect_zones    — cluster nodes into zones by position + type
  generate_from_template — scale a template warehouse up/down
  validate_connectivity — BFS reachability check
  suggest_charge_stations — recommend charge station count + placement
  calculate_metrics     — aisle count, total area, pick-to-ship distance

ConveyorDesigner:
  generate_conveyor_layout — from waypoints, create conveyor segments
  add_divert_point — add sorter divert at position on segment
  auto_connect_to_lanes — wire conveyor endpoints to lanes
  export_yaml — generate conveyor_layout.yaml from designed layout
  validate_topology — check no orphaned segments, flow direction consistent

40+ tests covering all components, edge cases, and real values.
TDD: Written FIRST, then implementation until green.
"""

import json
import math
import os
import sys

import pytest
import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from designer.layout_generator import LayoutGenerator
from designer.conveyor_designer import ConveyorDesigner


# ── Fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def simple_nodes():
    """3 nodes: charge, pick, drop — all within 3m distance."""
    return [
        {"name": "DOCK_1", "x": 0, "y": 0, "type": "charge"},
        {"name": "PICK_1", "x": 2, "y": 0, "type": "pick"},
        {"name": "DROP_1", "x": 4, "y": 0, "type": "drop"},
    ]


@pytest.fixture
def grid_nodes():
    """5x5 grid nodes for zone detection tests."""
    nodes = []
    for r in range(5):
        for c in range(5):
            name = f"N_{r}_{c}"
            if r == 0 and c == 0:
                node_type = "charge"
            elif r == 4 and c == 0:
                node_type = "pick"
            elif r == 4 and c == 4:
                node_type = "drop"
            elif r in (1, 2, 3) and c in (1, 2, 3):
                node_type = "shelf"
            else:
                node_type = "aisle"
            nodes.append({"name": name, "x": c * 2, "y": r * 2, "type": node_type})
    return nodes


@pytest.fixture
def simple_config(simple_nodes):
    """Simple valid config with 3 nodes + edges."""
    return {
        "name": "Test Config",
        "nodes": simple_nodes,
        "edges": [
            {"from": "DOCK_1", "to": "PICK_1"},
            {"from": "PICK_1", "to": "DROP_1"},
        ],
        "zones": [],
        "grid_spacing_m": 2.0,
    }


@pytest.fixture
def warehouse_config():
    """Load actual simple_grid.json warehouse config."""
    config_path = os.path.join(ROOT, "..", "configs", "warehouses", "simple_grid.json")
    with open(config_path) as f:
        return json.load(f)


@pytest.fixture
def waypoints_straight():
    """4 waypoints forming a straight horizontal line."""
    return [
        {"x": 0, "y": 0},
        {"x": 5, "y": 0},
        {"x": 10, "y": 0},
        {"x": 15, "y": 0},
    ]


@pytest.fixture
def waypoints_l_shape():
    """3 waypoints forming an L-shape."""
    return [
        {"x": 0, "y": 0},
        {"x": 10, "y": 0},
        {"x": 10, "y": 8},
    ]


# ══════════════════════════════════════════════════════════════════
# LAYOUT GENERATOR TESTS
# ══════════════════════════════════════════════════════════════════


class TestAutoGenerateEdges:
    """auto_generate_edges — connect nearby nodes within max_distance."""

    def test_connects_close_nodes(self, simple_nodes):
        edges = LayoutGenerator.auto_generate_edges(simple_nodes, max_distance=2.5)
        # DOCK_1-PICK_1 = 2m, PICK_1-DROP_1 = 2m, DOCK_1-DROP_1 = 4m
        assert len(edges) == 2
        pairs = {(e["from"], e["to"]) for e in edges}
        assert ("DOCK_1", "PICK_1") in pairs
        assert ("PICK_1", "DROP_1") in pairs

    def test_connects_all_within_large_radius(self, simple_nodes):
        edges = LayoutGenerator.auto_generate_edges(simple_nodes, max_distance=10.0)
        # All 3 pairs within 10m
        assert len(edges) == 3

    def test_no_edges_when_far_apart(self):
        nodes = [
            {"name": "A", "x": 0, "y": 0, "type": "charge"},
            {"name": "B", "x": 100, "y": 100, "type": "pick"},
        ]
        edges = LayoutGenerator.auto_generate_edges(nodes, max_distance=2.0)
        assert len(edges) == 0

    def test_empty_nodes_returns_empty(self):
        edges = LayoutGenerator.auto_generate_edges([], max_distance=5.0)
        assert edges == []

    def test_single_node_returns_empty(self):
        nodes = [{"name": "A", "x": 0, "y": 0, "type": "charge"}]
        edges = LayoutGenerator.auto_generate_edges(nodes, max_distance=5.0)
        assert edges == []

    def test_zero_distance_returns_empty(self, simple_nodes):
        edges = LayoutGenerator.auto_generate_edges(simple_nodes, max_distance=0)
        assert edges == []

    def test_negative_distance_returns_empty(self, simple_nodes):
        edges = LayoutGenerator.auto_generate_edges(simple_nodes, max_distance=-1.0)
        assert edges == []

    def test_exact_distance_boundary(self):
        """Nodes exactly at max_distance should be connected."""
        nodes = [
            {"name": "A", "x": 0, "y": 0, "type": "aisle"},
            {"name": "B", "x": 3, "y": 4, "type": "aisle"},  # dist = 5.0
        ]
        edges = LayoutGenerator.auto_generate_edges(nodes, max_distance=5.0)
        assert len(edges) == 1

    def test_grid_edge_count(self, grid_nodes):
        """5x5 grid with spacing 2m: adjacent nodes at 2m distance."""
        edges = LayoutGenerator.auto_generate_edges(grid_nodes, max_distance=2.5)
        # 5x5 grid: 4*5 horizontal + 5*4 vertical = 40 edges
        assert len(edges) == 40


class TestAutoDetectZones:
    """auto_detect_zones — cluster nodes into zones by position + type."""

    def test_groups_by_type(self, simple_nodes):
        zones = LayoutGenerator.auto_detect_zones(simple_nodes)
        types_found = {z["type"] for z in zones}
        assert "charge" in types_found
        assert "pick" in types_found
        assert "drop" in types_found

    def test_zone_node_assignment(self, simple_nodes):
        zones = LayoutGenerator.auto_detect_zones(simple_nodes)
        # Each zone has the correct nodes
        for zone in zones:
            assert len(zone["nodes"]) >= 1
            assert isinstance(zone["name"], str)
            assert len(zone["name"]) > 0

    def test_empty_nodes_returns_empty(self):
        zones = LayoutGenerator.auto_detect_zones([])
        assert zones == []

    def test_all_same_type_single_cell(self):
        """All nodes same type and in same grid cell -> 1 zone."""
        nodes = [
            {"name": "A", "x": 1, "y": 1, "type": "aisle"},
            {"name": "B", "x": 2, "y": 2, "type": "aisle"},
            {"name": "C", "x": 3, "y": 3, "type": "aisle"},
        ]
        zones = LayoutGenerator.auto_detect_zones(nodes)
        assert len(zones) == 1
        assert len(zones[0]["nodes"]) == 3

    def test_spatial_separation_creates_multiple_zones(self):
        """Same type but different grid cells -> multiple zones."""
        nodes = [
            {"name": "A", "x": 0, "y": 0, "type": "shelf"},
            {"name": "B", "x": 1, "y": 1, "type": "shelf"},
            {"name": "C", "x": 50, "y": 50, "type": "shelf"},  # different cell
        ]
        zones = LayoutGenerator.auto_detect_zones(nodes)
        shelf_zones = [z for z in zones if z["type"] == "shelf"]
        assert len(shelf_zones) == 2

    def test_grid_node_zone_detection(self, grid_nodes):
        """5x5 grid produces zones for each type present."""
        zones = LayoutGenerator.auto_detect_zones(grid_nodes)
        assert len(zones) >= 3  # at least charge, pick, drop types
        all_assigned = set()
        for z in zones:
            all_assigned.update(z["nodes"])
        assert len(all_assigned) == 25  # all 25 nodes assigned


class TestGenerateFromTemplate:
    """generate_from_template — scale a template warehouse up/down."""

    def test_scale_up_doubles_coordinates(self, simple_config):
        scaled = LayoutGenerator.generate_from_template(simple_config, scale_factor=2.0)
        # Original: DOCK_1 at (0,0), PICK_1 at (2,0), DROP_1 at (4,0)
        node_map = {n["name"]: n for n in scaled["nodes"]}
        assert node_map["PICK_1"]["x"] == 4.0
        assert node_map["DROP_1"]["x"] == 8.0

    def test_scale_down_halves_coordinates(self, simple_config):
        scaled = LayoutGenerator.generate_from_template(simple_config, scale_factor=0.5)
        node_map = {n["name"]: n for n in scaled["nodes"]}
        assert node_map["PICK_1"]["x"] == 1.0
        assert node_map["DROP_1"]["x"] == 2.0

    def test_scale_preserves_edges(self, simple_config):
        scaled = LayoutGenerator.generate_from_template(simple_config, scale_factor=3.0)
        assert len(scaled["edges"]) == len(simple_config["edges"])
        edge_pairs = {(e["from"], e["to"]) for e in scaled["edges"]}
        assert ("DOCK_1", "PICK_1") in edge_pairs

    def test_scale_preserves_node_count(self, simple_config):
        scaled = LayoutGenerator.generate_from_template(simple_config, scale_factor=1.5)
        assert len(scaled["nodes"]) == len(simple_config["nodes"])

    def test_scale_updates_grid_spacing(self, simple_config):
        scaled = LayoutGenerator.generate_from_template(simple_config, scale_factor=2.0)
        assert scaled["grid_spacing_m"] == 4.0

    def test_scale_updates_name(self, simple_config):
        scaled = LayoutGenerator.generate_from_template(simple_config, scale_factor=1.5)
        assert "1.5" in scaled["name"]

    def test_scale_factor_zero_raises(self, simple_config):
        with pytest.raises(ValueError, match="scale_factor must be > 0"):
            LayoutGenerator.generate_from_template(simple_config, scale_factor=0)

    def test_scale_factor_negative_raises(self, simple_config):
        with pytest.raises(ValueError, match="scale_factor must be > 0"):
            LayoutGenerator.generate_from_template(simple_config, scale_factor=-1)

    def test_scale_real_config(self, warehouse_config):
        """Scale actual simple_grid.json by 1.5x."""
        scaled = LayoutGenerator.generate_from_template(warehouse_config, scale_factor=1.5)
        assert len(scaled["nodes"]) == 25
        node_map = {n["name"]: n for n in scaled["nodes"]}
        # Original HUB at (4,4) -> (6,6)
        assert node_map["HUB"]["x"] == 6.0
        assert node_map["HUB"]["y"] == 6.0


class TestValidateConnectivity:
    """validate_connectivity — BFS reachability check."""

    def test_connected_graph(self, simple_nodes):
        edges = [
            {"from": "DOCK_1", "to": "PICK_1"},
            {"from": "PICK_1", "to": "DROP_1"},
        ]
        result = LayoutGenerator.validate_connectivity(simple_nodes, edges)
        assert result["connected"] is True
        assert result["total_nodes"] == 3
        assert result["reachable_nodes"] == 3
        assert result["unreachable"] == []
        assert result["components"] == 1

    def test_disconnected_graph(self):
        nodes = [
            {"name": "A", "x": 0, "y": 0, "type": "charge"},
            {"name": "B", "x": 2, "y": 0, "type": "pick"},
            {"name": "C", "x": 10, "y": 10, "type": "drop"},
        ]
        edges = [{"from": "A", "to": "B"}]
        result = LayoutGenerator.validate_connectivity(nodes, edges)
        assert result["connected"] is False
        assert result["components"] == 2
        # One node is unreachable from whichever node BFS starts at
        assert len(result["unreachable"]) >= 1
        assert result["reachable_nodes"] + len(result["unreachable"]) == 3

    def test_empty_graph(self):
        result = LayoutGenerator.validate_connectivity([], [])
        assert result["connected"] is True
        assert result["total_nodes"] == 0
        assert result["components"] == 0

    def test_single_node_no_edges(self):
        nodes = [{"name": "A", "x": 0, "y": 0, "type": "charge"}]
        result = LayoutGenerator.validate_connectivity(nodes, [])
        assert result["connected"] is True
        assert result["total_nodes"] == 1
        assert result["components"] == 1

    def test_three_components(self):
        nodes = [
            {"name": "A", "x": 0, "y": 0, "type": "aisle"},
            {"name": "B", "x": 5, "y": 0, "type": "aisle"},
            {"name": "C", "x": 10, "y": 0, "type": "aisle"},
        ]
        result = LayoutGenerator.validate_connectivity(nodes, [])
        assert result["connected"] is False
        assert result["components"] == 3


class TestSuggestChargeStations:
    """suggest_charge_stations — recommend charge station count + placement."""

    def test_basic_recommendation(self, grid_nodes):
        result = LayoutGenerator.suggest_charge_stations(grid_nodes, fleet_size=6)
        assert result["recommended_count"] == 2  # ceil(6/3) = 2
        assert len(result["suggested_nodes"]) == 2
        assert result["fleet_size"] == 6

    def test_single_robot(self, simple_nodes):
        result = LayoutGenerator.suggest_charge_stations(simple_nodes, fleet_size=1)
        assert result["recommended_count"] == 1

    def test_large_fleet(self, simple_nodes):
        """Large fleet but only 3 nodes -> capped at 3."""
        result = LayoutGenerator.suggest_charge_stations(simple_nodes, fleet_size=30)
        assert result["recommended_count"] == 3  # min(10, 3)

    def test_zero_fleet(self, simple_nodes):
        result = LayoutGenerator.suggest_charge_stations(simple_nodes, fleet_size=0)
        assert result["recommended_count"] == 0
        assert result["suggested_nodes"] == []

    def test_empty_nodes(self):
        result = LayoutGenerator.suggest_charge_stations([], fleet_size=5)
        assert result["recommended_count"] == 0

    def test_suggested_nodes_near_origin(self, grid_nodes):
        """Suggested nodes should be close to origin (low x+y)."""
        result = LayoutGenerator.suggest_charge_stations(grid_nodes, fleet_size=3)
        # First suggestion should be the node at (0,0)
        assert result["suggested_nodes"][0] == "N_0_0"


class TestCalculateMetrics:
    """calculate_metrics — aisle count, total area, pick-to-ship distance."""

    def test_basic_metrics(self, simple_config):
        metrics = LayoutGenerator.calculate_metrics(simple_config)
        assert metrics["total_nodes"] == 3
        assert metrics["total_edges"] == 2
        assert metrics["charge_station_count"] == 1
        assert metrics["pick_count"] == 1
        assert metrics["drop_count"] == 1

    def test_area_calculation(self, simple_config):
        metrics = LayoutGenerator.calculate_metrics(simple_config)
        # Nodes at x=0,2,4 and all y=0 -> width=4, height=0, area=0
        assert metrics["total_area_m2"] == 0.0

    def test_pick_to_ship_distance(self, simple_config):
        metrics = LayoutGenerator.calculate_metrics(simple_config)
        # PICK_1 at (2,0), DROP_1 at (4,0) -> distance = 2.0
        assert metrics["pick_to_ship_distance_m"] == 2.0

    def test_real_warehouse_metrics(self, warehouse_config):
        """Metrics from actual simple_grid.json."""
        metrics = LayoutGenerator.calculate_metrics(warehouse_config)
        assert metrics["total_nodes"] == 25
        assert metrics["total_edges"] == 40
        assert metrics["charge_station_count"] == 2
        assert metrics["pick_count"] == 1
        assert metrics["drop_count"] == 1
        assert metrics["shelf_count"] == 8
        assert metrics["zone_count"] == 8
        # Bounding box: (0,0) to (8,8) -> area = 64
        assert metrics["total_area_m2"] == 64.0
        # PICK_1 at (0,8), DROP_1 at (8,8) -> distance = 8.0
        assert metrics["pick_to_ship_distance_m"] == 8.0

    def test_empty_config_metrics(self):
        metrics = LayoutGenerator.calculate_metrics({})
        assert metrics["total_nodes"] == 0
        assert metrics["total_area_m2"] == 0.0
        assert metrics["pick_to_ship_distance_m"] == 0.0

    def test_no_pick_or_drop_distance_zero(self):
        config = {
            "nodes": [
                {"name": "A", "x": 0, "y": 0, "type": "aisle"},
                {"name": "B", "x": 5, "y": 5, "type": "shelf"},
            ],
            "edges": [{"from": "A", "to": "B"}],
        }
        metrics = LayoutGenerator.calculate_metrics(config)
        assert metrics["pick_to_ship_distance_m"] == 0.0
        assert metrics["total_area_m2"] == 25.0


# ══════════════════════════════════════════════════════════════════
# CONVEYOR DESIGNER TESTS
# ══════════════════════════════════════════════════════════════════


class TestGenerateConveyorLayout:
    """generate_conveyor_layout — from waypoints, create conveyor segments."""

    def test_creates_correct_segment_count(self, waypoints_straight):
        cd = ConveyorDesigner()
        segments = cd.generate_conveyor_layout(waypoints_straight)
        assert len(segments) == 3  # 4 waypoints -> 3 segments

    def test_segment_lengths(self, waypoints_straight):
        cd = ConveyorDesigner()
        segments = cd.generate_conveyor_layout(waypoints_straight)
        for seg in segments:
            assert seg["length_m"] == 5.0  # each segment is 5m

    def test_segment_linking(self, waypoints_straight):
        cd = ConveyorDesigner()
        segments = cd.generate_conveyor_layout(waypoints_straight)
        # First segment has no upstream
        assert segments[0]["upstream_id"] is None
        assert segments[0]["downstream_id"] == segments[1]["segment_id"]
        # Middle segment linked both ways
        assert segments[1]["upstream_id"] == segments[0]["segment_id"]
        assert segments[1]["downstream_id"] == segments[2]["segment_id"]
        # Last segment has no downstream
        assert segments[2]["upstream_id"] == segments[1]["segment_id"]
        assert segments[2]["downstream_id"] is None

    def test_l_shape_segment_lengths(self, waypoints_l_shape):
        cd = ConveyorDesigner()
        segments = cd.generate_conveyor_layout(waypoints_l_shape)
        assert len(segments) == 2
        assert segments[0]["length_m"] == 10.0  # horizontal
        assert segments[1]["length_m"] == 8.0    # vertical

    def test_single_waypoint_returns_empty(self):
        cd = ConveyorDesigner()
        segments = cd.generate_conveyor_layout([{"x": 0, "y": 0}])
        assert segments == []

    def test_empty_waypoints_returns_empty(self):
        cd = ConveyorDesigner()
        segments = cd.generate_conveyor_layout([])
        assert segments == []

    def test_segment_has_coordinates(self, waypoints_straight):
        cd = ConveyorDesigner()
        segments = cd.generate_conveyor_layout(waypoints_straight)
        assert segments[0]["start_x"] == 0.0
        assert segments[0]["start_y"] == 0.0
        assert segments[0]["end_x"] == 5.0
        assert segments[0]["end_y"] == 0.0


class TestAddDivertPoint:
    """add_divert_point — add sorter divert at position on segment."""

    def test_add_divert_success(self, waypoints_straight):
        cd = ConveyorDesigner()
        segments = cd.generate_conveyor_layout(waypoints_straight)
        divert = cd.add_divert_point(
            segment_id=segments[0]["segment_id"],
            position_m=2.5,
            target_lane="LANE_OUT_A",
        )
        assert divert is not None
        assert divert["position_m"] == 2.5
        assert divert["target_lane"] == "LANE_OUT_A"
        assert divert["divert_type"] == "popup"

    def test_add_divert_custom_type(self, waypoints_straight):
        cd = ConveyorDesigner()
        segments = cd.generate_conveyor_layout(waypoints_straight)
        divert = cd.add_divert_point(
            segment_id=segments[0]["segment_id"],
            position_m=1.0,
            target_lane="LANE_EXPRESS",
            divert_type="tilt_tray",
        )
        assert divert is not None
        assert divert["divert_type"] == "tilt_tray"

    def test_add_divert_invalid_segment(self, waypoints_straight):
        cd = ConveyorDesigner()
        cd.generate_conveyor_layout(waypoints_straight)
        divert = cd.add_divert_point("NONEXISTENT", 2.0, "LANE_A")
        assert divert is None

    def test_add_divert_position_past_end(self, waypoints_straight):
        cd = ConveyorDesigner()
        segments = cd.generate_conveyor_layout(waypoints_straight)
        # Segment is 5m long, trying to add at 6m
        divert = cd.add_divert_point(segments[0]["segment_id"], 6.0, "LANE_A")
        assert divert is None

    def test_add_divert_negative_position(self, waypoints_straight):
        cd = ConveyorDesigner()
        segments = cd.generate_conveyor_layout(waypoints_straight)
        divert = cd.add_divert_point(segments[0]["segment_id"], -1.0, "LANE_A")
        assert divert is None

    def test_multiple_diverts_on_same_segment(self, waypoints_straight):
        cd = ConveyorDesigner()
        segments = cd.generate_conveyor_layout(waypoints_straight)
        seg_id = segments[1]["segment_id"]
        d1 = cd.add_divert_point(seg_id, 1.0, "LANE_A")
        d2 = cd.add_divert_point(seg_id, 3.0, "LANE_B")
        assert d1 is not None
        assert d2 is not None
        assert len(cd.divert_points) == 2


class TestAutoConnectToLanes:
    """auto_connect_to_lanes — wire conveyor endpoints to lanes."""

    def test_connects_inbound_to_entry(self, waypoints_straight):
        cd = ConveyorDesigner()
        segments = cd.generate_conveyor_layout(waypoints_straight)
        lanes = [
            {"lane_id": "IN_1", "type": "inbound"},
            {"lane_id": "OUT_1", "type": "outbound"},
        ]
        updated = cd.auto_connect_to_lanes(segments, lanes)
        assert len(updated) == 2
        in_lane = next(l for l in updated if l["lane_id"] == "IN_1")
        out_lane = next(l for l in updated if l["lane_id"] == "OUT_1")
        assert in_lane["connected_segment_id"] == segments[0]["segment_id"]
        assert out_lane["connected_segment_id"] == segments[-1]["segment_id"]

    def test_empty_lanes(self, waypoints_straight):
        cd = ConveyorDesigner()
        segments = cd.generate_conveyor_layout(waypoints_straight)
        updated = cd.auto_connect_to_lanes(segments, [])
        assert updated == []

    def test_empty_segments(self):
        cd = ConveyorDesigner()
        lanes = [{"lane_id": "IN_1", "type": "inbound"}]
        updated = cd.auto_connect_to_lanes([], lanes)
        assert len(updated) == 1  # lanes preserved, just not connected


class TestExportYaml:
    """export_yaml — generate YAML from designed layout."""

    def test_export_produces_valid_yaml(self, waypoints_straight):
        cd = ConveyorDesigner()
        cd.generate_conveyor_layout(waypoints_straight)
        yaml_str = cd.export_yaml()
        parsed = yaml.safe_load(yaml_str)
        assert "segments" in parsed
        assert len(parsed["segments"]) == 3
        assert "divert_points" in parsed
        assert "lanes" in parsed

    def test_export_includes_divert_points(self, waypoints_straight):
        cd = ConveyorDesigner()
        segments = cd.generate_conveyor_layout(waypoints_straight)
        cd.add_divert_point(segments[0]["segment_id"], 2.0, "LANE_A")
        yaml_str = cd.export_yaml()
        parsed = yaml.safe_load(yaml_str)
        assert len(parsed["divert_points"]) == 1
        assert parsed["divert_points"][0]["target_lane"] == "LANE_A"

    def test_export_segment_fields(self, waypoints_straight):
        cd = ConveyorDesigner()
        cd.generate_conveyor_layout(waypoints_straight)
        yaml_str = cd.export_yaml()
        parsed = yaml.safe_load(yaml_str)
        seg = parsed["segments"][0]
        assert "segment_id" in seg
        assert "length_m" in seg
        assert "max_speed_mps" in seg
        assert "direction" in seg


class TestValidateTopology:
    """validate_topology — check topology validity."""

    def test_valid_linear_chain(self, waypoints_straight):
        cd = ConveyorDesigner()
        cd.generate_conveyor_layout(waypoints_straight)
        result = cd.validate_topology()
        assert result["valid"] is True
        assert result["errors"] == []
        assert result["segment_count"] == 3
        assert len(result["entry_points"]) == 1
        assert len(result["exit_points"]) == 1

    def test_no_segments_is_invalid(self):
        cd = ConveyorDesigner()
        result = cd.validate_topology()
        assert result["valid"] is False
        assert len(result["errors"]) > 0

    def test_detects_invalid_divert_reference(self, waypoints_straight):
        cd = ConveyorDesigner()
        cd.generate_conveyor_layout(waypoints_straight)
        # Manually inject a bad divert point referencing a nonexistent segment
        cd._divert_points.append({
            "divert_id": "BAD_DIV",
            "name": "Bad Divert",
            "segment_id": "NONEXISTENT_SEG",
            "position_m": 1.0,
            "target_lane": "LANE_X",
            "divert_type": "popup",
        })
        result = cd.validate_topology()
        assert result["valid"] is False
        assert any("NONEXISTENT_SEG" in e for e in result["errors"])

    def test_topology_with_diverts_valid(self, waypoints_straight):
        cd = ConveyorDesigner()
        segments = cd.generate_conveyor_layout(waypoints_straight)
        cd.add_divert_point(segments[1]["segment_id"], 2.0, "LANE_A")
        cd.add_divert_point(segments[1]["segment_id"], 4.0, "LANE_B")
        result = cd.validate_topology()
        assert result["valid"] is True
        assert result["divert_count"] == 2

    def test_segment_accessor(self, waypoints_straight):
        cd = ConveyorDesigner()
        cd.generate_conveyor_layout(waypoints_straight)
        assert len(cd.segments) == 3

    def test_divert_accessor(self, waypoints_straight):
        cd = ConveyorDesigner()
        segments = cd.generate_conveyor_layout(waypoints_straight)
        cd.add_divert_point(segments[0]["segment_id"], 1.0, "LANE_A")
        assert len(cd.divert_points) == 1

    def test_lanes_accessor(self, waypoints_straight):
        cd = ConveyorDesigner()
        segments = cd.generate_conveyor_layout(waypoints_straight)
        lanes = [{"lane_id": "X", "type": "inbound"}]
        cd.auto_connect_to_lanes(segments, lanes)
        assert len(cd.lanes) == 1


# ══════════════════════════════════════════════════════════════════
# FIX VERIFICATION TESTS — max_speed_mps param, divert_type validation,
# auto_connect_to_lanes mismatch
# ══════════════════════════════════════════════════════════════════


class TestMaxSpeedParameter:
    """generate_conveyor_layout — max_speed_mps as explicit parameter."""

    def test_default_speed_is_1_5(self, waypoints_straight):
        cd = ConveyorDesigner()
        segments = cd.generate_conveyor_layout(waypoints_straight)
        for seg in segments:
            assert seg["max_speed_mps"] == 1.5

    def test_custom_speed(self, waypoints_straight):
        cd = ConveyorDesigner()
        segments = cd.generate_conveyor_layout(waypoints_straight, max_speed_mps=2.5)
        for seg in segments:
            assert seg["max_speed_mps"] == 2.5

    def test_slow_speed(self, waypoints_l_shape):
        cd = ConveyorDesigner()
        segments = cd.generate_conveyor_layout(waypoints_l_shape, max_speed_mps=0.3)
        assert len(segments) == 2
        for seg in segments:
            assert seg["max_speed_mps"] == 0.3


class TestDivertTypeValidation:
    """add_divert_point — validates divert_type against allowed set."""

    def test_allowed_type_popup(self, waypoints_straight):
        cd = ConveyorDesigner()
        segments = cd.generate_conveyor_layout(waypoints_straight)
        divert = cd.add_divert_point(segments[0]["segment_id"], 2.0, "LANE_A", "popup")
        assert divert is not None
        assert divert["divert_type"] == "popup"

    def test_allowed_type_tilt_tray(self, waypoints_straight):
        cd = ConveyorDesigner()
        segments = cd.generate_conveyor_layout(waypoints_straight)
        divert = cd.add_divert_point(segments[0]["segment_id"], 2.0, "LANE_A", "tilt_tray")
        assert divert is not None
        assert divert["divert_type"] == "tilt_tray"

    def test_allowed_type_crossbelt(self, waypoints_straight):
        cd = ConveyorDesigner()
        segments = cd.generate_conveyor_layout(waypoints_straight)
        divert = cd.add_divert_point(segments[0]["segment_id"], 2.0, "LANE_A", "crossbelt")
        assert divert is not None
        assert divert["divert_type"] == "crossbelt"

    def test_allowed_type_pusher(self, waypoints_straight):
        cd = ConveyorDesigner()
        segments = cd.generate_conveyor_layout(waypoints_straight)
        divert = cd.add_divert_point(segments[0]["segment_id"], 2.0, "LANE_A", "pusher")
        assert divert is not None
        assert divert["divert_type"] == "pusher"

    def test_invalid_type_raises_valueerror(self, waypoints_straight):
        cd = ConveyorDesigner()
        segments = cd.generate_conveyor_layout(waypoints_straight)
        with pytest.raises(ValueError, match="Invalid divert_type"):
            cd.add_divert_point(segments[0]["segment_id"], 2.0, "LANE_A", "roller")

    def test_empty_type_raises_valueerror(self, waypoints_straight):
        cd = ConveyorDesigner()
        segments = cd.generate_conveyor_layout(waypoints_straight)
        with pytest.raises(ValueError, match="Invalid divert_type"):
            cd.add_divert_point(segments[0]["segment_id"], 2.0, "LANE_A", "")


class TestAutoConnectToLanesMismatch:
    """auto_connect_to_lanes — edge cases with lane/segment count mismatches."""

    def test_more_inbound_lanes_than_entry_segments(self, waypoints_straight):
        """3 inbound lanes but only 1 entry segment: first lane connected, rest not."""
        cd = ConveyorDesigner()
        segments = cd.generate_conveyor_layout(waypoints_straight)
        lanes = [
            {"lane_id": "IN_1", "type": "inbound"},
            {"lane_id": "IN_2", "type": "inbound"},
            {"lane_id": "IN_3", "type": "inbound"},
        ]
        updated = cd.auto_connect_to_lanes(segments, lanes)
        assert len(updated) == 3
        # Only first inbound lane gets connected (1 entry segment)
        assert "connected_segment_id" in updated[0]
        assert updated[0]["connected_segment_id"] == segments[0]["segment_id"]
        # Other lanes have no connected_segment_id
        assert "connected_segment_id" not in updated[1]
        assert "connected_segment_id" not in updated[2]

    def test_more_outbound_lanes_than_exit_segments(self, waypoints_straight):
        """2 outbound lanes but only 1 exit segment: first connected, second not."""
        cd = ConveyorDesigner()
        segments = cd.generate_conveyor_layout(waypoints_straight)
        lanes = [
            {"lane_id": "OUT_1", "type": "outbound"},
            {"lane_id": "OUT_2", "type": "outbound"},
        ]
        updated = cd.auto_connect_to_lanes(segments, lanes)
        assert len(updated) == 2
        assert updated[0]["connected_segment_id"] == segments[-1]["segment_id"]
        assert "connected_segment_id" not in updated[1]

    def test_mixed_lane_types_partial_connection(self, waypoints_straight):
        """Mix of inbound, outbound, and unknown types."""
        cd = ConveyorDesigner()
        segments = cd.generate_conveyor_layout(waypoints_straight)
        lanes = [
            {"lane_id": "IN_1", "type": "inbound"},
            {"lane_id": "MISC_1", "type": "internal"},
            {"lane_id": "OUT_1", "type": "outbound"},
        ]
        updated = cd.auto_connect_to_lanes(segments, lanes)
        assert len(updated) == 3
        # inbound connected to entry
        assert updated[0]["connected_segment_id"] == segments[0]["segment_id"]
        # internal type: no connection
        assert "connected_segment_id" not in updated[1]
        # outbound connected to exit
        assert updated[2]["connected_segment_id"] == segments[-1]["segment_id"]

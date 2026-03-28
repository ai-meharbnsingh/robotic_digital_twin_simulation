"""
Tests for gazebo/scripts/generate_world.py

Generates worlds from REAL warehouse configs and validates:
  - Output is valid XML / SDF
  - All 25 nodes present for simple_grid
  - All 63 nodes present for botvalley
  - Ground plane, walls, barcode grid, node markers exist
  - Charger/pick/drop station models exist for correct node types
  - No shelf or wall blocks a navigable node position
"""

import json
import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

# Add scripts to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "gazebo" / "scripts"))

from generate_world import generate_world, _load_nodes, _compute_bounds


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SIMPLE_GRID_JSON = PROJECT_ROOT / "configs" / "warehouses" / "simple_grid.json"
BOTVALLEY_JSON = PROJECT_ROOT / "configs" / "warehouses" / "botvalley.json"


@pytest.fixture
def simple_grid_sdf(tmp_path):
    """Generate simple_grid world into a temp directory."""
    sdf_path = generate_world(str(SIMPLE_GRID_JSON), str(tmp_path))
    return sdf_path


@pytest.fixture
def botvalley_sdf(tmp_path):
    """Generate botvalley world into a temp directory."""
    sdf_path = generate_world(str(BOTVALLEY_JSON), str(tmp_path))
    return sdf_path


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _parse_sdf(path: str) -> ET.Element:
    """Parse SDF file and return root element."""
    tree = ET.parse(path)
    return tree.getroot()


def _find_all_models(root: ET.Element) -> list[ET.Element]:
    """Find all <model> elements in the SDF."""
    world = root.find("world")
    assert world is not None, "No <world> element in SDF"
    return world.findall("model")


# ---------------------------------------------------------------------------
# Tests: simple_grid (25 nodes)
# ---------------------------------------------------------------------------

class TestSimpleGridWorld:

    def test_output_is_valid_xml(self, simple_grid_sdf):
        """SDF file must be parseable XML."""
        root = _parse_sdf(simple_grid_sdf)
        assert root.tag == "sdf"
        assert root.attrib.get("version") == "1.9"

    def test_has_world_element(self, simple_grid_sdf):
        """SDF must contain a <world> element."""
        root = _parse_sdf(simple_grid_sdf)
        world = root.find("world")
        assert world is not None

    def test_has_ground_plane(self, simple_grid_sdf):
        """World must have a ground_plane model."""
        root = _parse_sdf(simple_grid_sdf)
        models = _find_all_models(root)
        names = [m.attrib.get("name") for m in models]
        assert "ground_plane" in names

    def test_has_four_walls(self, simple_grid_sdf):
        """World must have four perimeter walls."""
        root = _parse_sdf(simple_grid_sdf)
        models = _find_all_models(root)
        names = [m.attrib.get("name") for m in models]
        for wall in ("wall_north", "wall_south", "wall_east", "wall_west"):
            assert wall in names, f"Missing wall: {wall}"

    def test_has_25_node_markers(self, simple_grid_sdf):
        """simple_grid has 25 nodes — all must have marker visuals."""
        root = _parse_sdf(simple_grid_sdf)
        world = root.find("world")
        marker_model = world.find(".//model[@name='node_markers']")
        assert marker_model is not None, "No node_markers model"

        link = marker_model.find("link[@name='markers_link']")
        assert link is not None, "No markers_link"

        visuals = link.findall("visual")
        # Should have exactly 25 marker visuals
        marker_visuals = [v for v in visuals if v.attrib.get("name", "").startswith("marker_")]
        assert len(marker_visuals) == 25, f"Expected 25 marker visuals, got {len(marker_visuals)}"

    def test_has_charging_stations(self, simple_grid_sdf):
        """simple_grid has 2 charge nodes (DOCK_1, DOCK_2)."""
        root = _parse_sdf(simple_grid_sdf)
        models = _find_all_models(root)
        chargers = [m for m in models if m.attrib.get("name", "").startswith("charger_")]
        assert len(chargers) == 2, f"Expected 2 chargers, got {len(chargers)}"

    def test_has_pick_drop_stations(self, simple_grid_sdf):
        """simple_grid has 1 pick and 1 drop node — multiple models per station."""
        root = _parse_sdf(simple_grid_sdf)
        models = _find_all_models(root)
        pick_models = [m for m in models if m.attrib.get("name", "").startswith(("pick_table_", "pick_shelf_"))]
        drop_models = [m for m in models if m.attrib.get("name", "").startswith(("drop_conv_", "drop_wall_"))]
        assert len(pick_models) >= 1, f"Expected pick station models, got {len(pick_models)}"
        assert len(drop_models) >= 1, f"Expected drop station models, got {len(drop_models)}"

    def test_has_shelf_models(self, simple_grid_sdf):
        """simple_grid has 8 shelf nodes — each generates rack models."""
        root = _parse_sdf(simple_grid_sdf)
        models = _find_all_models(root)
        racks = [m for m in models if m.attrib.get("name", "").startswith("rack_")]
        assert len(racks) >= 8, f"Expected at least 8 rack models, got {len(racks)}"

    def test_has_barcode_grid(self, simple_grid_sdf):
        """World must have a barcode_grid model with visual markers."""
        root = _parse_sdf(simple_grid_sdf)
        world = root.find("world")
        barcode_model = world.find(".//model[@name='barcode_grid']")
        assert barcode_model is not None, "No barcode_grid model"

        link = barcode_model.find("link[@name='barcode_grid_link']")
        assert link is not None
        barcodes = link.findall("visual")
        # At 0.8m interval over a ~12m x 12m area = ~225+ barcodes
        assert len(barcodes) > 100, f"Expected many barcode visuals, got {len(barcodes)}"

    def test_has_sun_light(self, simple_grid_sdf):
        """World must have sun light."""
        root = _parse_sdf(simple_grid_sdf)
        world = root.find("world")
        light = world.find("light[@name='sun']")
        assert light is not None

    def test_has_physics(self, simple_grid_sdf):
        """World must have physics settings."""
        root = _parse_sdf(simple_grid_sdf)
        world = root.find("world")
        physics = world.find("physics")
        assert physics is not None

    def test_navigable_nodes_not_blocked(self, simple_grid_sdf):
        """Aisle/hub/charge/pick/drop nodes must NOT have shelf models on them."""
        with open(SIMPLE_GRID_JSON) as f:
            data = json.load(f)

        nodes = _load_nodes(data)
        navigable = [n for n in nodes if n.node_type in ("aisle", "hub", "charge", "pick", "drop")]

        root = _parse_sdf(simple_grid_sdf)
        models = _find_all_models(root)
        shelf_positions = []
        for m in models:
            if not m.attrib.get("name", "").startswith("shelf_"):
                continue
            pose = m.find("pose")
            if pose is not None and pose.text:
                parts = pose.text.split()
                shelf_positions.append((float(parts[0]), float(parts[1])))

        # No shelf should be at a navigable node position
        for nav_node in navigable:
            for sx, sy in shelf_positions:
                dist = ((nav_node.x - sx) ** 2 + (nav_node.y - sy) ** 2) ** 0.5
                assert dist > 0.1, (
                    f"Shelf at ({sx}, {sy}) blocks navigable node "
                    f"{nav_node.name} at ({nav_node.x}, {nav_node.y})")

    def test_all_models_are_static(self, simple_grid_sdf):
        """All environment models (not robots) must be static."""
        root = _parse_sdf(simple_grid_sdf)
        models = _find_all_models(root)
        for m in models:
            static = m.find("static")
            assert static is not None and static.text == "true", \
                f"Model {m.attrib.get('name')} is not static"


# ---------------------------------------------------------------------------
# Tests: botvalley (63 nodes)
# ---------------------------------------------------------------------------

class TestBotValleyWorld:

    def test_output_is_valid_xml(self, botvalley_sdf):
        """SDF file must be parseable XML."""
        root = _parse_sdf(botvalley_sdf)
        assert root.tag == "sdf"

    def test_has_63_node_markers(self, botvalley_sdf):
        """botvalley has 63 nodes — all must have marker visuals."""
        root = _parse_sdf(botvalley_sdf)
        world = root.find("world")
        marker_model = world.find(".//model[@name='node_markers']")
        assert marker_model is not None

        link = marker_model.find("link[@name='markers_link']")
        assert link is not None

        visuals = link.findall("visual")
        marker_visuals = [v for v in visuals if v.attrib.get("name", "").startswith("marker_")]
        assert len(marker_visuals) == 63, f"Expected 63 marker visuals, got {len(marker_visuals)}"

    def test_has_charge_station(self, botvalley_sdf):
        """botvalley has 1 charge node."""
        root = _parse_sdf(botvalley_sdf)
        models = _find_all_models(root)
        chargers = [m for m in models if m.attrib.get("name", "").startswith("charger_")]
        assert len(chargers) == 1, f"Expected 1 charger, got {len(chargers)}"

    def test_has_pick_drop(self, botvalley_sdf):
        """botvalley has 1 pick and 1 drop node — multiple models per station."""
        root = _parse_sdf(botvalley_sdf)
        models = _find_all_models(root)
        pick_models = [m for m in models if m.attrib.get("name", "").startswith(("pick_table_", "pick_shelf_"))]
        drop_models = [m for m in models if m.attrib.get("name", "").startswith(("drop_conv_", "drop_wall_"))]
        assert len(pick_models) >= 1, f"Expected pick station models, got {len(pick_models)}"
        assert len(drop_models) >= 1, f"Expected drop station models, got {len(drop_models)}"

    def test_world_bounds_reasonable(self, botvalley_sdf):
        """World bounds should cover the ~30m x 34m BotValley layout."""
        with open(BOTVALLEY_JSON) as f:
            data = json.load(f)
        nodes = _load_nodes(data)
        min_x, min_y, max_x, max_y = _compute_bounds(nodes)
        width = max_x - min_x
        height = max_y - min_y
        # BotValley is roughly 30x34m
        assert width > 20, f"Width {width} seems too small"
        assert height > 20, f"Height {height} seems too small"
        assert width < 100, f"Width {width} seems too large"
        assert height < 100, f"Height {height} seems too large"

    def test_has_barcode_grid(self, botvalley_sdf):
        """BotValley world must have barcode grid."""
        root = _parse_sdf(botvalley_sdf)
        world = root.find("world")
        barcode_model = world.find(".//model[@name='barcode_grid']")
        assert barcode_model is not None

    def test_has_zone_models(self, botvalley_sdf):
        """BotValley has 2 zones — should have zone models."""
        root = _parse_sdf(botvalley_sdf)
        models = _find_all_models(root)
        zone_models = [m for m in models if m.attrib.get("name", "").startswith("zone_")]
        assert len(zone_models) >= 2, f"Expected at least 2 zone models, got {len(zone_models)}"


# ---------------------------------------------------------------------------
# Tests: cross-format validation
# ---------------------------------------------------------------------------

class TestNodeLoader:

    def test_simple_grid_loads_25_nodes(self):
        """_load_nodes must return exactly 25 nodes for simple_grid."""
        with open(SIMPLE_GRID_JSON) as f:
            data = json.load(f)
        nodes = _load_nodes(data)
        assert len(nodes) == 25

    def test_botvalley_loads_63_nodes(self):
        """_load_nodes must return exactly 63 nodes for botvalley."""
        with open(BOTVALLEY_JSON) as f:
            data = json.load(f)
        nodes = _load_nodes(data)
        assert len(nodes) == 63

    def test_simple_grid_node_types(self):
        """simple_grid should have charge, aisle, shelf, hub, pick, drop types."""
        with open(SIMPLE_GRID_JSON) as f:
            data = json.load(f)
        nodes = _load_nodes(data)
        types = set(n.node_type for n in nodes)
        assert "charge" in types
        assert "aisle" in types
        assert "shelf" in types
        assert "hub" in types
        assert "pick" in types
        assert "drop" in types

    def test_botvalley_has_charge_and_pick_drop(self):
        """botvalley should have charge, pick, drop types."""
        with open(BOTVALLEY_JSON) as f:
            data = json.load(f)
        nodes = _load_nodes(data)
        types = set(n.node_type for n in nodes)
        assert "charge" in types
        assert "pick" in types
        assert "drop" in types

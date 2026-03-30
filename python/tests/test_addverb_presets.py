"""
Tests for Phase 9 — Addverb Fleet Presets.

Validates that all Addverb robot configs, warehouse layout, fleet manifest,
and behavior trees load correctly and contain realistic specifications.

TDD: Written FIRST, then configs until green.
"""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def project_root() -> Path:
    """Return the project root directory."""
    return Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def configs_dir(project_root) -> Path:
    """Return the configs directory."""
    return project_root / "configs"


# ── Helper to load YAML configs ──────────────────────────────────


def load_robot_yaml(configs_dir: Path, name: str) -> dict:
    """Load a robot YAML config by name."""
    path = configs_dir / "robots" / f"{name}.yaml"
    assert path.exists(), f"Robot config not found: {path}"
    with open(path) as f:
        return yaml.safe_load(f)


# ── Dynamo AMR Config ────────────────────────────────────────────


class TestDynamoConfigLoads:
    """test_dynamo_config_loads — valid YAML, all fields present."""

    def test_dynamo_config_loads(self, configs_dir):
        config = load_robot_yaml(configs_dir, "addverb_dynamo")
        assert config["name"] == "Addverb_Dynamo"
        assert config["type"] == "differential_drive"
        # All top-level sections present
        for section in ("motion", "dimensions", "sensors", "battery",
                        "obstacle_thresholds", "attachment", "mpc",
                        "action_codes", "response_codes"):
            assert section in config, f"Missing section: {section}"
        # Behavior tree reference
        assert "behavior_tree" in config
        assert config["behavior_tree"] == "addverb_dynamo.xml"


class TestDynamoSpecsRealistic:
    """test_dynamo_specs_realistic — velocity 1.5, payload 1500kg."""

    def test_dynamo_velocity(self, configs_dir):
        config = load_robot_yaml(configs_dir, "addverb_dynamo")
        assert config["motion"]["max_linear_velocity"] == 1.5

    def test_dynamo_payload(self, configs_dir):
        config = load_robot_yaml(configs_dir, "addverb_dynamo")
        assert config["dimensions"]["payload_capacity"] == 1500.0

    def test_dynamo_acceleration(self, configs_dir):
        config = load_robot_yaml(configs_dir, "addverb_dynamo")
        assert config["motion"]["linear_acceleration"] == 0.2

    def test_dynamo_lidar_360(self, configs_dir):
        config = load_robot_yaml(configs_dir, "addverb_dynamo")
        assert config["sensors"]["lidar"]["fov_deg"] == 360
        assert config["sensors"]["lidar"]["type"] == "2d"

    def test_dynamo_footprint(self, configs_dir):
        config = load_robot_yaml(configs_dir, "addverb_dynamo")
        assert config["dimensions"]["length"] == 0.85
        assert config["dimensions"]["width"] == 0.65


# ── Veloce ACR Config ────────────────────────────────────────────


class TestVeloceConfigLoads:
    """test_veloce_config_loads — valid YAML, all fields present."""

    def test_veloce_config_loads(self, configs_dir):
        config = load_robot_yaml(configs_dir, "addverb_veloce")
        assert config["name"] == "Addverb_Veloce"
        assert config["type"] == "unidirectional"
        for section in ("motion", "dimensions", "sensors", "battery",
                        "obstacle_thresholds", "attachment", "mpc",
                        "action_codes", "response_codes"):
            assert section in config, f"Missing section: {section}"
        assert config["behavior_tree"] == "addverb_veloce.xml"


class TestVeloceSpecsRealistic:
    """test_veloce_specs_realistic — grid-based nav, 240kg."""

    def test_veloce_payload(self, configs_dir):
        config = load_robot_yaml(configs_dir, "addverb_veloce")
        assert config["dimensions"]["payload_capacity"] == 240.0

    def test_veloce_grid_nav(self, configs_dir):
        """Veloce uses barcode scanner for grid-based nav."""
        config = load_robot_yaml(configs_dir, "addverb_veloce")
        assert config["sensors"]["barcode_reader"]["enabled"] is True
        # Veloce relies on barcode grid, limited LiDAR
        assert config["sensors"]["lidar"]["fov_deg"] <= 60

    def test_veloce_compact_footprint(self, configs_dir):
        config = load_robot_yaml(configs_dir, "addverb_veloce")
        assert config["dimensions"]["length"] == 0.6
        assert config["dimensions"]["width"] == 0.6


# ── Quadron Shuttle Config ───────────────────────────────────────


class TestQuadronConfigLoads:
    """test_quadron_config_loads — valid YAML, all fields present."""

    def test_quadron_config_loads(self, configs_dir):
        config = load_robot_yaml(configs_dir, "addverb_quadron")
        assert config["name"] == "Addverb_Quadron"
        assert config["type"] == "unidirectional"
        for section in ("motion", "dimensions", "sensors", "battery",
                        "obstacle_thresholds", "attachment", "mpc",
                        "action_codes", "response_codes"):
            assert section in config, f"Missing section: {section}"
        assert config["behavior_tree"] == "addverb_quadron.xml"


class TestQuadronSpecsRealistic:
    """test_quadron_specs_realistic — 4 m/s, rail-guided."""

    def test_quadron_high_speed(self, configs_dir):
        config = load_robot_yaml(configs_dir, "addverb_quadron")
        assert config["motion"]["max_linear_velocity"] == 4.0

    def test_quadron_rail_guided_no_angular(self, configs_dir):
        """Rail-guided shuttle has zero angular velocity."""
        config = load_robot_yaml(configs_dir, "addverb_quadron")
        assert config["motion"]["max_angular_velocity"] == 0.0

    def test_quadron_payload(self, configs_dir):
        config = load_robot_yaml(configs_dir, "addverb_quadron")
        assert config["dimensions"]["payload_capacity"] == 50.0

    def test_quadron_no_lidar(self, configs_dir):
        """Rail-guided shuttle uses encoder, no LiDAR needed."""
        config = load_robot_yaml(configs_dir, "addverb_quadron")
        assert config["sensors"]["lidar"]["enabled"] is False


# ── Addverb Noida Warehouse ──────────────────────────────────────


class TestNoidaWarehouseLoads:
    """test_noida_warehouse_loads — valid JSON, nodes+edges+zones."""

    def test_noida_warehouse_loads(self, configs_dir):
        path = configs_dir / "warehouses" / "addverb_noida.json"
        assert path.exists(), f"Warehouse config not found: {path}"
        with open(path) as f:
            config = json.load(f)
        assert "name" in config
        assert "nodes" in config
        assert "edges" in config
        assert "zones" in config
        # 49 nodes (7x7 grid)
        assert len(config["nodes"]) == 49
        # All nodes have required fields
        for node in config["nodes"]:
            assert "name" in node
            assert "x" in node
            assert "y" in node
            assert "type" in node


class TestNoidaWarehouseValidates:
    """test_noida_warehouse_validates — passes WarehouseValidator."""

    def test_noida_warehouse_validates(self, configs_dir):
        from wes.warehouse_validator import WarehouseValidator

        path = configs_dir / "warehouses" / "addverb_noida.json"
        with open(path) as f:
            config = json.load(f)
        result = WarehouseValidator.validate(config)
        assert result["valid"] is True, f"Validation errors: {result['errors']}"
        assert result["errors"] == []


class TestNoidaHasAllZoneTypes:
    """test_noida_has_all_zone_types — inbound, storage, outbound, charging."""

    def test_noida_has_all_zone_types(self, configs_dir):
        path = configs_dir / "warehouses" / "addverb_noida.json"
        with open(path) as f:
            config = json.load(f)
        zone_names_lower = [z["name"].lower() for z in config["zones"]]
        zone_text = " ".join(zone_names_lower)
        # Must have zones for: inbound (pick), storage (shelf), outbound (drop), charging
        assert any("inbound" in n or "pick" in n for n in zone_names_lower), \
            f"No inbound/pick zone found in zones: {zone_names_lower}"
        assert any("storage" in n or "shelf" in n for n in zone_names_lower), \
            f"No storage zone found in zones: {zone_names_lower}"
        assert any("outbound" in n or "drop" in n for n in zone_names_lower), \
            f"No outbound/drop zone found in zones: {zone_names_lower}"
        assert any("charg" in n for n in zone_names_lower), \
            f"No charging zone found in zones: {zone_names_lower}"


class TestNoidaHasEnoughChargeStations:
    """test_noida_has_enough_charge_stations — >=4 charge nodes."""

    def test_noida_has_enough_charge_stations(self, configs_dir):
        path = configs_dir / "warehouses" / "addverb_noida.json"
        with open(path) as f:
            config = json.load(f)
        charge_nodes = [n for n in config["nodes"] if n["type"] == "charge"]
        assert len(charge_nodes) >= 4, \
            f"Only {len(charge_nodes)} charge nodes — need at least 4 for mixed fleet"


# ── Mixed Fleet Manifest ─────────────────────────────────────────


class TestMixedFleetManifestLoads:
    """test_mixed_fleet_manifest_loads — valid JSON with correct structure."""

    def test_mixed_fleet_manifest_loads(self, configs_dir):
        path = configs_dir / "fleets" / "addverb_mixed.json"
        assert path.exists(), f"Fleet manifest not found: {path}"
        with open(path) as f:
            manifest = json.load(f)
        assert "name" in manifest
        assert "robots" in manifest
        assert len(manifest["robots"]) == 3  # Dynamo + Veloce + Quadron
        # Total robots: 3 + 5 + 2 = 10
        total = sum(r["count"] for r in manifest["robots"])
        assert total == 10


class TestMixedFleetReferencesValidConfigs:
    """test_mixed_fleet_references_valid_configs — all robot configs exist."""

    def test_mixed_fleet_references_valid_configs(self, configs_dir):
        path = configs_dir / "fleets" / "addverb_mixed.json"
        with open(path) as f:
            manifest = json.load(f)
        for entry in manifest["robots"]:
            config_ref = entry["config"]
            # Config reference is a path like "configs/robots/addverb_dynamo.yaml"
            config_path = configs_dir.parent / config_ref
            assert config_path.exists(), \
                f"Fleet entry references nonexistent config: {config_ref} (looked at {config_path})"


# ── Behavior Trees ───────────────────────────────────────────────


class TestBtDynamoLoads:
    """test_bt_dynamo_loads — valid XML."""

    def test_bt_dynamo_loads(self, configs_dir):
        path = configs_dir / "behavior_trees" / "addverb_dynamo.xml"
        assert path.exists(), f"BT not found: {path}"
        tree = ET.parse(path)
        root = tree.getroot()
        assert root.tag == "root"
        assert root.attrib.get("BTCPP_format") == "4"
        # Must have at least one BehaviorTree element
        bt_elements = root.findall(".//BehaviorTree")
        assert len(bt_elements) >= 1

    def test_bt_dynamo_has_charging(self, configs_dir):
        """Dynamo BT includes battery management."""
        path = configs_dir / "behavior_trees" / "addverb_dynamo.xml"
        tree = ET.parse(path)
        root = tree.getroot()
        # Look for battery-related subtree or action
        xml_str = ET.tostring(root, encoding="unicode")
        assert "Battery" in xml_str or "Charg" in xml_str


class TestBtVeloceLoads:
    """test_bt_veloce_loads — valid XML."""

    def test_bt_veloce_loads(self, configs_dir):
        path = configs_dir / "behavior_trees" / "addverb_veloce.xml"
        assert path.exists(), f"BT not found: {path}"
        tree = ET.parse(path)
        root = tree.getroot()
        assert root.tag == "root"
        assert root.attrib.get("BTCPP_format") == "4"
        bt_elements = root.findall(".//BehaviorTree")
        assert len(bt_elements) >= 1

    def test_bt_veloce_grid_navigation(self, configs_dir):
        """Veloce BT uses grid-based navigation with barcode verification."""
        path = configs_dir / "behavior_trees" / "addverb_veloce.xml"
        tree = ET.parse(path)
        root = tree.getroot()
        xml_str = ET.tostring(root, encoding="unicode")
        # Grid-based navigation via GridNavigate subtree
        assert "GridNavigate" in xml_str
        # Barcode verification modeled via AlignAtStation with barcode_verify type
        assert "barcode_verify" in xml_str or "barcode_scan" in xml_str
        # No unregistered actions remain
        assert "ScanBarcode" not in xml_str


class TestBtQuadronLoads:
    """test_bt_quadron_loads — valid XML."""

    def test_bt_quadron_loads(self, configs_dir):
        path = configs_dir / "behavior_trees" / "addverb_quadron.xml"
        assert path.exists(), f"BT not found: {path}"
        tree = ET.parse(path)
        root = tree.getroot()
        assert root.tag == "root"
        assert root.attrib.get("BTCPP_format") == "4"
        bt_elements = root.findall(".//BehaviorTree")
        assert len(bt_elements) >= 1

    def test_bt_quadron_rail_shuttle(self, configs_dir):
        """Quadron BT models rail shuttle lane operations using registered actions."""
        path = configs_dir / "behavior_trees" / "addverb_quadron.xml"
        tree = ET.parse(path)
        root = tree.getroot()
        xml_str = ET.tostring(root, encoding="unicode")
        # Rail shuttle lane operation modeled via ShuttleLaneOperation subtree
        assert "ShuttleLaneOperation" in xml_str
        # Uses only registered actions (NavigateToNode for lane enter/exit)
        assert "NavigateToNode" in xml_str
        # No unregistered actions remain
        assert "EnterLane" not in xml_str
        assert "ExitLane" not in xml_str
        assert "RailLimitReached" not in xml_str


# ── Config Hardening Tests ──────────────────────────────────────


class TestRobotConfigPathTraversal:
    """test_robot_config_path_traversal — names with ../ are rejected."""

    def test_robot_config_path_traversal_dotdot(self):
        from app.config import load_robot_config

        with pytest.raises(ValueError, match="Invalid robot config name"):
            load_robot_config("../../../etc/passwd")

    def test_robot_config_path_traversal_slash(self):
        from app.config import load_robot_config

        with pytest.raises(ValueError, match="Invalid robot config name"):
            load_robot_config("subdir/evil")

    def test_robot_config_path_traversal_backslash(self):
        from app.config import load_robot_config

        with pytest.raises(ValueError, match="Invalid robot config name"):
            load_robot_config("subdir\\evil")


class TestWarehouseConfigPathTraversal:
    """test_warehouse_config_path_traversal — names with ../ are rejected."""

    def test_warehouse_config_path_traversal_dotdot(self):
        from app.config import load_warehouse_config

        with pytest.raises(ValueError, match="Invalid warehouse config name"):
            load_warehouse_config("../../../etc/passwd")

    def test_warehouse_config_path_traversal_slash(self):
        from app.config import load_warehouse_config

        with pytest.raises(ValueError, match="Invalid warehouse config name"):
            load_warehouse_config("subdir/evil")

    def test_warehouse_config_path_traversal_backslash(self):
        from app.config import load_warehouse_config

        with pytest.raises(ValueError, match="Invalid warehouse config name"):
            load_warehouse_config("subdir\\evil")


class TestRobotConfigVelocityValidation:
    """test_robot_config_invalid_velocity — velocity 0 or negative is rejected."""

    def test_robot_config_zero_velocity(self, configs_dir, tmp_path):
        """A config with max_linear_velocity=0 raises ValueError."""
        from app.config import load_robot_config, PROJECT_ROOT

        # Create a temporary invalid config in the actual configs/robots/ dir
        bad_config = {
            "name": "BadBot",
            "type": "differential_drive",
            "motion": {"max_linear_velocity": 0, "max_angular_velocity": 1.0},
            "dimensions": {},
            "sensors": {},
            "battery": {},
            "obstacle_thresholds": {},
        }
        bad_path = PROJECT_ROOT / "configs" / "robots" / "_test_bad_velocity.yaml"
        try:
            with open(bad_path, "w") as f:
                yaml.dump(bad_config, f)
            with pytest.raises(ValueError, match="max_linear_velocity must be positive"):
                load_robot_config("_test_bad_velocity")
        finally:
            # Clean up: move to archive instead of rm
            archive_dir = tmp_path / "archive"
            archive_dir.mkdir(exist_ok=True)
            if bad_path.exists():
                import shutil
                shutil.move(str(bad_path), str(archive_dir / bad_path.name))

    def test_robot_config_negative_velocity(self, configs_dir, tmp_path):
        """A config with max_linear_velocity=-1 raises ValueError."""
        from app.config import load_robot_config, PROJECT_ROOT

        bad_config = {
            "name": "BadBot",
            "type": "differential_drive",
            "motion": {"max_linear_velocity": -1.0, "max_angular_velocity": 1.0},
            "dimensions": {},
            "sensors": {},
            "battery": {},
            "obstacle_thresholds": {},
        }
        bad_path = PROJECT_ROOT / "configs" / "robots" / "_test_neg_velocity.yaml"
        try:
            with open(bad_path, "w") as f:
                yaml.dump(bad_config, f)
            with pytest.raises(ValueError, match="max_linear_velocity must be positive"):
                load_robot_config("_test_neg_velocity")
        finally:
            archive_dir = tmp_path / "archive"
            archive_dir.mkdir(exist_ok=True)
            if bad_path.exists():
                import shutil
                shutil.move(str(bad_path), str(archive_dir / bad_path.name))

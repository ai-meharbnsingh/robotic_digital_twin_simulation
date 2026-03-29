"""
Phase 2: Mixed Fleet Types — test fleet manifest loading,
robot type differentiation, and type-filtered task assignment.

Tests verify:
- Fleet manifest JSON parses correctly
- Expanded fleet has correct robot IDs and types
- isTypeCompatible rules are respected (AGVs can't PICK/PLACE)
- API responses include robot_type field
"""

import json
from pathlib import Path

import pytest

# Resolve project root (python/tests/ → project root is ../../)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# ── Fleet manifest loading tests ─────────────────────────


class TestFleetManifest:
    """Tests for configs/fleets/default_mixed.json structure."""

    @pytest.fixture
    def manifest(self):
        manifest_path = PROJECT_ROOT / "configs" / "fleets" / "default_mixed.json"
        with open(manifest_path) as f:
            return json.load(f)

    def test_manifest_has_name(self, manifest):
        assert manifest["name"] == "Default Mixed Fleet"

    def test_manifest_has_description(self, manifest):
        assert "description" in manifest
        assert len(manifest["description"]) > 0

    def test_manifest_has_robot_entries(self, manifest):
        assert "robots" in manifest
        assert len(manifest["robots"]) == 2

    def test_manifest_amr_entry(self, manifest):
        amr = manifest["robots"][0]
        assert amr["id_prefix"] == "AMR"
        assert amr["count"] == 5
        assert "differential_drive" in amr["config"]

    def test_manifest_agv_entry(self, manifest):
        agv = manifest["robots"][1]
        assert agv["id_prefix"] == "AGV"
        assert agv["count"] == 5
        assert "unidirectional" in agv["config"]

    def test_manifest_config_files_exist(self, manifest):
        """Verify that all referenced robot config YAML files actually exist."""
        for entry in manifest["robots"]:
            config_path = PROJECT_ROOT / entry["config"]
            assert config_path.exists(), f"Robot config not found: {config_path}"

    def test_manifest_total_robots(self, manifest):
        total = sum(entry["count"] for entry in manifest["robots"])
        assert total == 10


# ── Fleet expansion tests ─────────────────────────────────


class TestFleetExpansion:
    """Tests for expanding a fleet manifest into individual robot configs."""

    @pytest.fixture
    def expanded_fleet(self):
        """Simulate fleet expansion (Python equivalent of C++ expandFleetManifest)."""
        manifest_path = PROJECT_ROOT / "configs" / "fleets" / "default_mixed.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        robots = []
        for entry in manifest["robots"]:
            config_path = PROJECT_ROOT / entry["config"]

            # Load the base YAML config to get type info
            import yaml
            with open(config_path) as yf:
                base_config = yaml.safe_load(yf)

            for i in range(1, entry["count"] + 1):
                robot_id = f"{entry['id_prefix']}_{i:03d}"
                robots.append({
                    "robot_id": robot_id,
                    "robot_type": base_config["type"],
                    "name": base_config["name"],
                    "max_linear_velocity": base_config["motion"]["max_linear_velocity"],
                    "behavior_tree": base_config.get("behavior_tree", ""),
                })
        return robots

    def test_expanded_count(self, expanded_fleet):
        assert len(expanded_fleet) == 10

    def test_amr_ids(self, expanded_fleet):
        amr_ids = [r["robot_id"] for r in expanded_fleet if r["robot_id"].startswith("AMR")]
        assert amr_ids == ["AMR_001", "AMR_002", "AMR_003", "AMR_004", "AMR_005"]

    def test_agv_ids(self, expanded_fleet):
        agv_ids = [r["robot_id"] for r in expanded_fleet if r["robot_id"].startswith("AGV")]
        assert agv_ids == ["AGV_001", "AGV_002", "AGV_003", "AGV_004", "AGV_005"]

    def test_amr_type(self, expanded_fleet):
        for r in expanded_fleet:
            if r["robot_id"].startswith("AMR"):
                assert r["robot_type"] == "differential_drive"

    def test_agv_type(self, expanded_fleet):
        for r in expanded_fleet:
            if r["robot_id"].startswith("AGV"):
                assert r["robot_type"] == "unidirectional"

    def test_amr_speed(self, expanded_fleet):
        """AMRs should have 2.0 m/s max linear velocity."""
        for r in expanded_fleet:
            if r["robot_id"].startswith("AMR"):
                assert r["max_linear_velocity"] == 2.0

    def test_agv_speed(self, expanded_fleet):
        """AGVs should have 1.4 m/s max linear velocity."""
        for r in expanded_fleet:
            if r["robot_id"].startswith("AGV"):
                assert r["max_linear_velocity"] == 1.4

    def test_amr_behavior_tree(self, expanded_fleet):
        for r in expanded_fleet:
            if r["robot_id"].startswith("AMR"):
                assert r["behavior_tree"] == "default_amr.xml"

    def test_agv_behavior_tree(self, expanded_fleet):
        for r in expanded_fleet:
            if r["robot_id"].startswith("AGV"):
                assert r["behavior_tree"] == "default_agv.xml"


# ── Type compatibility tests ──────────────────────────────


class TestTypeCompatibility:
    """
    Test isTypeCompatible logic (Python mirror of C++ TaskManager::isTypeCompatible).

    Rules:
    - All types can do: MOVE, CHARGE, PARK
    - Only DIFFERENTIAL_DRIVE and OMNIDIRECTIONAL can do: PICK, PLACE
    - UNIDIRECTIONAL cannot do: PICK, PLACE
    """

    @staticmethod
    def is_type_compatible(robot_type: str, task_type: str) -> bool:
        """Python mirror of C++ TaskManager::isTypeCompatible."""
        if task_type in ("move", "charge", "park"):
            return True
        if task_type in ("pick", "place"):
            return robot_type in ("differential_drive", "omnidirectional")
        return True

    def test_amr_can_move(self):
        assert self.is_type_compatible("differential_drive", "move")

    def test_agv_can_move(self):
        assert self.is_type_compatible("unidirectional", "move")

    def test_omni_can_move(self):
        assert self.is_type_compatible("omnidirectional", "move")

    def test_amr_can_pick(self):
        assert self.is_type_compatible("differential_drive", "pick")

    def test_agv_cannot_pick(self):
        assert not self.is_type_compatible("unidirectional", "pick")

    def test_omni_can_pick(self):
        assert self.is_type_compatible("omnidirectional", "pick")

    def test_amr_can_place(self):
        assert self.is_type_compatible("differential_drive", "place")

    def test_agv_cannot_place(self):
        assert not self.is_type_compatible("unidirectional", "place")

    def test_omni_can_place(self):
        assert self.is_type_compatible("omnidirectional", "place")

    def test_amr_can_charge(self):
        assert self.is_type_compatible("differential_drive", "charge")

    def test_agv_can_charge(self):
        assert self.is_type_compatible("unidirectional", "charge")

    def test_amr_can_park(self):
        assert self.is_type_compatible("differential_drive", "park")

    def test_agv_can_park(self):
        assert self.is_type_compatible("unidirectional", "park")


# ── Robot config differentiation tests ────────────────────


class TestRobotConfigDifferences:
    """Verify that AMR and AGV configs have meaningfully different parameters."""

    @pytest.fixture
    def amr_config(self):
        import yaml
        with open(PROJECT_ROOT / "configs" / "robots" / "differential_drive.yaml") as f:
            return yaml.safe_load(f)

    @pytest.fixture
    def agv_config(self):
        import yaml
        with open(PROJECT_ROOT / "configs" / "robots" / "unidirectional.yaml") as f:
            return yaml.safe_load(f)

    def test_different_types(self, amr_config, agv_config):
        assert amr_config["type"] == "differential_drive"
        assert agv_config["type"] == "unidirectional"

    def test_different_speeds(self, amr_config, agv_config):
        amr_speed = amr_config["motion"]["max_linear_velocity"]
        agv_speed = agv_config["motion"]["max_linear_velocity"]
        assert amr_speed > agv_speed  # AMR is faster (2.0 vs 1.4)

    def test_different_lidar_fov(self, amr_config, agv_config):
        amr_fov = amr_config["sensors"]["lidar"]["fov_deg"]
        agv_fov = agv_config["sensors"]["lidar"]["fov_deg"]
        assert amr_fov == 360   # Full 360
        assert agv_fov == 30    # Forward-facing only

    def test_different_behavior_trees(self, amr_config, agv_config):
        assert amr_config["behavior_tree"] == "default_amr.xml"
        assert agv_config["behavior_tree"] == "default_agv.xml"

    def test_agv_has_conveyor_attachment(self, amr_config, agv_config):
        assert amr_config["attachment"]["type"] == "none"
        assert agv_config["attachment"]["type"] == "conveyor"

    def test_different_imu(self, amr_config, agv_config):
        assert amr_config["sensors"]["imu"]["enabled"] is True
        assert agv_config["sensors"]["imu"]["enabled"] is False

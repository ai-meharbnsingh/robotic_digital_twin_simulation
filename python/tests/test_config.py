"""
Tests for config loading.

REAL assertions on actual values from simple_grid.json and differential_drive.yaml.
No MagicMock. No hardcoded True.
"""

import pytest

from app.config import load_robot_config, load_warehouse_config


class TestWarehouseConfig:
    """Test loading simple_grid.json warehouse config."""

    def test_load_simple_grid_returns_dict(self):
        warehouse = load_warehouse_config("simple_grid")
        assert isinstance(warehouse, dict)

    def test_warehouse_has_required_keys(self):
        warehouse = load_warehouse_config("simple_grid")
        assert "nodes" in warehouse
        assert "edges" in warehouse
        assert "zones" in warehouse
        assert "name" in warehouse

    def test_warehouse_name(self):
        warehouse = load_warehouse_config("simple_grid")
        assert warehouse["name"] == "Simple 5x5 Grid"

    def test_warehouse_has_25_nodes(self):
        warehouse = load_warehouse_config("simple_grid")
        assert len(warehouse["nodes"]) == 25

    def test_warehouse_has_40_edges(self):
        warehouse = load_warehouse_config("simple_grid")
        assert len(warehouse["edges"]) == 40

    def test_warehouse_has_3_zones(self):
        warehouse = load_warehouse_config("simple_grid")
        assert len(warehouse["zones"]) == 3

    def test_zone_names(self):
        warehouse = load_warehouse_config("simple_grid")
        zone_names = [z["name"] for z in warehouse["zones"]]
        assert "Charging" in zone_names
        assert "Storage" in zone_names
        assert "Operations" in zone_names

    def test_nodes_have_required_fields(self):
        warehouse = load_warehouse_config("simple_grid")
        for node in warehouse["nodes"]:
            assert "name" in node
            assert "x" in node
            assert "y" in node
            assert "type" in node

    def test_edges_have_required_fields(self):
        warehouse = load_warehouse_config("simple_grid")
        for edge in warehouse["edges"]:
            assert "from" in edge
            assert "to" in edge

    def test_dock_nodes_exist(self):
        warehouse = load_warehouse_config("simple_grid")
        node_names = [n["name"] for n in warehouse["nodes"]]
        assert "DOCK_1" in node_names
        assert "DOCK_2" in node_names

    def test_hub_node_at_center(self):
        warehouse = load_warehouse_config("simple_grid")
        hub = [n for n in warehouse["nodes"] if n["name"] == "HUB"][0]
        assert hub["x"] == 4
        assert hub["y"] == 4
        assert hub["type"] == "hub"

    def test_nonexistent_warehouse_raises(self):
        with pytest.raises(FileNotFoundError):
            load_warehouse_config("nonexistent_warehouse_xyz")


class TestRobotConfig:
    """Test loading differential_drive.yaml robot config."""

    def test_load_differential_drive_returns_dict(self):
        robot = load_robot_config("differential_drive")
        assert isinstance(robot, dict)

    def test_robot_has_motion_section(self):
        robot = load_robot_config("differential_drive")
        assert "motion" in robot
        assert isinstance(robot["motion"], dict)

    def test_robot_has_battery_section(self):
        robot = load_robot_config("differential_drive")
        assert "battery" in robot
        assert isinstance(robot["battery"], dict)

    def test_robot_has_sensors_section(self):
        robot = load_robot_config("differential_drive")
        assert "sensors" in robot
        assert isinstance(robot["sensors"], dict)

    def test_robot_has_mpc_section(self):
        robot = load_robot_config("differential_drive")
        assert "mpc" in robot
        assert isinstance(robot["mpc"], dict)

    def test_robot_name(self):
        robot = load_robot_config("differential_drive")
        assert robot["name"] == "DiffDrive_AMR"

    def test_robot_type(self):
        robot = load_robot_config("differential_drive")
        assert robot["type"] == "differential_drive"

    def test_motion_max_velocity(self):
        robot = load_robot_config("differential_drive")
        assert robot["motion"]["max_linear_velocity"] == 2.0

    def test_battery_charge_duration(self):
        robot = load_robot_config("differential_drive")
        assert robot["battery"]["charge_duration_s"] == 600

    def test_battery_discharge_duration(self):
        robot = load_robot_config("differential_drive")
        assert robot["battery"]["discharge_duration_s"] == 54000

    def test_battery_critical_threshold(self):
        robot = load_robot_config("differential_drive")
        assert robot["battery"]["critical_threshold_pct"] == 20

    def test_obstacle_thresholds(self):
        robot = load_robot_config("differential_drive")
        thresholds = robot["obstacle_thresholds"]
        assert thresholds["critical_m"] == 0.7
        assert thresholds["warning_m"] == 0.8
        assert thresholds["planning_m"] == 1.5

    def test_mpc_opt_vars(self):
        robot = load_robot_config("differential_drive")
        assert robot["mpc"]["num_opt_vars"] == 12

    def test_lidar_config(self):
        robot = load_robot_config("differential_drive")
        lidar = robot["sensors"]["lidar"]
        assert lidar["enabled"] is True
        assert lidar["fov_deg"] == 360
        assert lidar["range_m"] == 5.0

    def test_action_codes(self):
        robot = load_robot_config("differential_drive")
        codes = robot["action_codes"]
        assert codes["move"] == 0
        assert codes["charge_dock"] == 2
        assert codes["start_charging"] == 3

    def test_nonexistent_robot_raises(self):
        with pytest.raises(FileNotFoundError):
            load_robot_config("nonexistent_robot_xyz")

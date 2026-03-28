"""
Tests for gazebo/scripts/generate_robot.py

Generates robot models from REAL robot YAML configs and validates:
  - Output is valid XML / SDF
  - Chassis link exists with correct dimensions
  - Drive wheels exist (2 for diff drive, 4 for unidirectional)
  - Caster wheels exist for differential drive
  - LiDAR sensor present when enabled
  - IMU sensor present when enabled
  - Diff drive plugin configured with correct YAML values
  - model.config file generated
"""

import math
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

# Add scripts to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "gazebo" / "scripts"))

from generate_robot import generate_robot

# ---------------------------------------------------------------------------
# Config paths
# ---------------------------------------------------------------------------

DIFF_DRIVE_YAML = PROJECT_ROOT / "configs" / "robots" / "differential_drive.yaml"
UNI_YAML = PROJECT_ROOT / "configs" / "robots" / "unidirectional.yaml"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def diff_drive_sdf(tmp_path):
    """Generate differential_drive robot into a temp directory."""
    sdf_path = generate_robot(str(DIFF_DRIVE_YAML), str(tmp_path))
    return sdf_path


@pytest.fixture
def uni_sdf(tmp_path):
    """Generate unidirectional robot into a temp directory."""
    sdf_path = generate_robot(str(UNI_YAML), str(tmp_path))
    return sdf_path


@pytest.fixture
def diff_drive_cfg():
    """Load the differential_drive YAML config."""
    with open(DIFF_DRIVE_YAML) as f:
        return yaml.safe_load(f)


@pytest.fixture
def uni_cfg():
    """Load the unidirectional YAML config."""
    with open(UNI_YAML) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _parse_sdf(path: str) -> ET.Element:
    tree = ET.parse(path)
    return tree.getroot()


def _find_links(root: ET.Element) -> list[ET.Element]:
    model = root.find("model")
    assert model is not None
    return model.findall("link")


def _find_joints(root: ET.Element) -> list[ET.Element]:
    model = root.find("model")
    assert model is not None
    return model.findall("joint")


def _find_plugins(root: ET.Element) -> list[ET.Element]:
    model = root.find("model")
    assert model is not None
    return model.findall("plugin")


# ---------------------------------------------------------------------------
# Tests: Differential Drive
# ---------------------------------------------------------------------------

class TestDiffDriveRobot:

    def test_output_is_valid_xml(self, diff_drive_sdf):
        """SDF file must be parseable XML."""
        root = _parse_sdf(diff_drive_sdf)
        assert root.tag == "sdf"
        assert root.attrib.get("version") == "1.9"

    def test_has_model_element(self, diff_drive_sdf):
        """SDF must contain a <model> element."""
        root = _parse_sdf(diff_drive_sdf)
        model = root.find("model")
        assert model is not None
        assert model.attrib.get("name") == "diffdrive_amr"

    def test_has_chassis_link(self, diff_drive_sdf):
        """Model must have a chassis link."""
        root = _parse_sdf(diff_drive_sdf)
        links = _find_links(root)
        chassis = [l for l in links if l.attrib.get("name") == "chassis"]
        assert len(chassis) == 1

    def test_chassis_dimensions_from_yaml(self, diff_drive_sdf, diff_drive_cfg):
        """Chassis box dimensions must match YAML config."""
        root = _parse_sdf(diff_drive_sdf)
        links = _find_links(root)
        chassis = [l for l in links if l.attrib.get("name") == "chassis"][0]

        # Find the visual box size
        vis = chassis.find(".//visual//geometry/box/size")
        assert vis is not None
        parts = vis.text.split()
        assert len(parts) == 3

        dims = diff_drive_cfg["dimensions"]
        assert float(parts[0]) == pytest.approx(dims["length"], abs=0.01)
        assert float(parts[1]) == pytest.approx(dims["width"], abs=0.01)
        assert float(parts[2]) == pytest.approx(dims["height"], abs=0.01)

    def test_has_two_drive_wheels(self, diff_drive_sdf):
        """Differential drive must have left_wheel and right_wheel links."""
        root = _parse_sdf(diff_drive_sdf)
        links = _find_links(root)
        link_names = [l.attrib.get("name") for l in links]
        assert "left_wheel" in link_names
        assert "right_wheel" in link_names

    def test_has_caster_wheels(self, diff_drive_sdf):
        """Differential drive must have front and rear caster links."""
        root = _parse_sdf(diff_drive_sdf)
        links = _find_links(root)
        link_names = [l.attrib.get("name") for l in links]
        assert "front_caster" in link_names
        assert "rear_caster" in link_names

    def test_wheel_radius_from_yaml(self, diff_drive_sdf, diff_drive_cfg):
        """Drive wheel radius must match YAML config."""
        root = _parse_sdf(diff_drive_sdf)
        links = _find_links(root)
        left_wheel = [l for l in links if l.attrib.get("name") == "left_wheel"][0]

        radius_elem = left_wheel.find(".//geometry/cylinder/radius")
        assert radius_elem is not None
        assert float(radius_elem.text) == pytest.approx(
            diff_drive_cfg["dimensions"]["wheel_radius"], abs=0.001)

    def test_has_lidar_sensor(self, diff_drive_sdf):
        """LiDAR is enabled in diff_drive YAML — must have lidar_link + sensor."""
        root = _parse_sdf(diff_drive_sdf)
        links = _find_links(root)
        lidar_links = [l for l in links if l.attrib.get("name") == "lidar_link"]
        assert len(lidar_links) == 1

        sensor = lidar_links[0].find(".//sensor[@name='lidar_sensor']")
        assert sensor is not None
        assert sensor.attrib.get("type") == "gpu_lidar"

    def test_lidar_fov_from_yaml(self, diff_drive_sdf, diff_drive_cfg):
        """LiDAR FOV must match YAML config."""
        root = _parse_sdf(diff_drive_sdf)
        links = _find_links(root)
        lidar_link = [l for l in links if l.attrib.get("name") == "lidar_link"][0]

        sensor = lidar_link.find(".//sensor[@name='lidar_sensor']")
        max_angle = sensor.find(".//horizontal/max_angle")
        assert max_angle is not None

        fov_deg = diff_drive_cfg["sensors"]["lidar"]["fov_deg"]
        expected_half_fov = math.radians(fov_deg) / 2
        assert float(max_angle.text) == pytest.approx(expected_half_fov, abs=0.01)

    def test_lidar_range_from_yaml(self, diff_drive_sdf, diff_drive_cfg):
        """LiDAR max range must match YAML config."""
        root = _parse_sdf(diff_drive_sdf)
        links = _find_links(root)
        lidar_link = [l for l in links if l.attrib.get("name") == "lidar_link"][0]
        sensor = lidar_link.find(".//sensor[@name='lidar_sensor']")
        range_max = sensor.find(".//range/max")
        assert range_max is not None
        assert float(range_max.text) == pytest.approx(
            diff_drive_cfg["sensors"]["lidar"]["range_m"], abs=0.1)

    def test_lidar_rays_from_yaml(self, diff_drive_sdf, diff_drive_cfg):
        """LiDAR ray count must match YAML config."""
        root = _parse_sdf(diff_drive_sdf)
        links = _find_links(root)
        lidar_link = [l for l in links if l.attrib.get("name") == "lidar_link"][0]
        sensor = lidar_link.find(".//sensor[@name='lidar_sensor']")
        samples = sensor.find(".//horizontal/samples")
        assert samples is not None
        assert int(samples.text) == diff_drive_cfg["sensors"]["lidar"]["rays"]

    def test_has_imu_sensor(self, diff_drive_sdf):
        """IMU is enabled in diff_drive YAML — must have imu_link + sensor."""
        root = _parse_sdf(diff_drive_sdf)
        links = _find_links(root)
        imu_links = [l for l in links if l.attrib.get("name") == "imu_link"]
        assert len(imu_links) == 1

        sensor = imu_links[0].find(".//sensor[@name='imu_sensor']")
        assert sensor is not None
        assert sensor.attrib.get("type") == "imu"

    def test_has_diff_drive_plugin(self, diff_drive_sdf):
        """Must have gz-sim-diff-drive-system plugin."""
        root = _parse_sdf(diff_drive_sdf)
        plugins = _find_plugins(root)
        dd_plugins = [p for p in plugins
                      if p.attrib.get("filename") == "gz-sim-diff-drive-system"]
        assert len(dd_plugins) == 1

    def test_diff_drive_plugin_values_from_yaml(self, diff_drive_sdf, diff_drive_cfg):
        """Diff drive plugin wheel_separation and wheel_radius from YAML."""
        root = _parse_sdf(diff_drive_sdf)
        plugins = _find_plugins(root)
        dd = [p for p in plugins
              if p.attrib.get("filename") == "gz-sim-diff-drive-system"][0]

        ws = dd.find("wheel_separation")
        assert ws is not None
        assert float(ws.text) == pytest.approx(
            diff_drive_cfg["dimensions"]["wheel_separation"], abs=0.001)

        wr = dd.find("wheel_radius")
        assert wr is not None
        assert float(wr.text) == pytest.approx(
            diff_drive_cfg["dimensions"]["wheel_radius"], abs=0.001)

    def test_has_joint_state_publisher(self, diff_drive_sdf):
        """Must have joint state publisher plugin."""
        root = _parse_sdf(diff_drive_sdf)
        plugins = _find_plugins(root)
        jsp = [p for p in plugins
               if p.attrib.get("filename") == "gz-sim-joint-state-publisher-system"]
        assert len(jsp) == 1

    def test_has_model_config(self, diff_drive_sdf):
        """model.config must exist alongside model.sdf."""
        sdf_dir = Path(diff_drive_sdf).parent
        config_path = sdf_dir / "model.config"
        assert config_path.exists()
        tree = ET.parse(str(config_path))
        root = tree.getroot()
        assert root.tag == "model"
        name = root.find("name")
        assert name is not None
        assert name.text == "DiffDrive_AMR"

    def test_wheel_joints_exist(self, diff_drive_sdf):
        """Must have left_wheel_joint and right_wheel_joint."""
        root = _parse_sdf(diff_drive_sdf)
        joints = _find_joints(root)
        joint_names = [j.attrib.get("name") for j in joints]
        assert "left_wheel_joint" in joint_names
        assert "right_wheel_joint" in joint_names

    def test_caster_joints_exist(self, diff_drive_sdf):
        """Must have front_caster_joint and rear_caster_joint."""
        root = _parse_sdf(diff_drive_sdf)
        joints = _find_joints(root)
        joint_names = [j.attrib.get("name") for j in joints]
        assert "front_caster_joint" in joint_names
        assert "rear_caster_joint" in joint_names

    def test_inertial_on_chassis(self, diff_drive_sdf, diff_drive_cfg):
        """Chassis must have inertial element with correct mass."""
        root = _parse_sdf(diff_drive_sdf)
        links = _find_links(root)
        chassis = [l for l in links if l.attrib.get("name") == "chassis"][0]
        inertial = chassis.find("inertial")
        assert inertial is not None
        mass = inertial.find("mass")
        assert mass is not None
        assert float(mass.text) == pytest.approx(
            diff_drive_cfg["dimensions"]["weight"], abs=0.1)


# ---------------------------------------------------------------------------
# Tests: Unidirectional AGV
# ---------------------------------------------------------------------------

class TestUnidirectionalRobot:

    def test_output_is_valid_xml(self, uni_sdf):
        """SDF file must be parseable XML."""
        root = _parse_sdf(uni_sdf)
        assert root.tag == "sdf"

    def test_has_four_wheels(self, uni_sdf):
        """Unidirectional must have 4 wheel links."""
        root = _parse_sdf(uni_sdf)
        links = _find_links(root)
        link_names = [l.attrib.get("name") for l in links]
        assert "front_left_wheel" in link_names
        assert "front_right_wheel" in link_names
        assert "rear_left_wheel" in link_names
        assert "rear_right_wheel" in link_names

    def test_no_caster_wheels(self, uni_sdf):
        """Unidirectional must NOT have caster wheels."""
        root = _parse_sdf(uni_sdf)
        links = _find_links(root)
        link_names = [l.attrib.get("name") for l in links]
        assert "front_caster" not in link_names
        assert "rear_caster" not in link_names

    def test_has_lidar(self, uni_sdf):
        """LiDAR is enabled in uni YAML — must exist."""
        root = _parse_sdf(uni_sdf)
        links = _find_links(root)
        lidar_links = [l for l in links if l.attrib.get("name") == "lidar_link"]
        assert len(lidar_links) == 1

    def test_lidar_fov_30_degrees(self, uni_sdf, uni_cfg):
        """Unidirectional LiDAR FOV is 30 degrees (forward-facing)."""
        root = _parse_sdf(uni_sdf)
        links = _find_links(root)
        lidar_link = [l for l in links if l.attrib.get("name") == "lidar_link"][0]
        sensor = lidar_link.find(".//sensor[@name='lidar_sensor']")
        max_angle = sensor.find(".//horizontal/max_angle")
        expected_half_fov = math.radians(30) / 2
        assert float(max_angle.text) == pytest.approx(expected_half_fov, abs=0.01)

    def test_no_imu(self, uni_sdf):
        """IMU is disabled in uni YAML — must NOT have imu_link."""
        root = _parse_sdf(uni_sdf)
        links = _find_links(root)
        imu_links = [l for l in links if l.attrib.get("name") == "imu_link"]
        assert len(imu_links) == 0

    def test_chassis_dimensions(self, uni_sdf, uni_cfg):
        """Chassis dimensions must match uni YAML (0.6 x 0.5 x 0.25)."""
        root = _parse_sdf(uni_sdf)
        links = _find_links(root)
        chassis = [l for l in links if l.attrib.get("name") == "chassis"][0]
        vis = chassis.find(".//visual//geometry/box/size")
        parts = vis.text.split()
        dims = uni_cfg["dimensions"]
        assert float(parts[0]) == pytest.approx(dims["length"], abs=0.01)
        assert float(parts[1]) == pytest.approx(dims["width"], abs=0.01)
        assert float(parts[2]) == pytest.approx(dims["height"], abs=0.01)

    def test_has_diff_drive_plugin(self, uni_sdf):
        """Unidirectional still uses diff drive plugin (front wheels)."""
        root = _parse_sdf(uni_sdf)
        plugins = _find_plugins(root)
        dd_plugins = [p for p in plugins
                      if p.attrib.get("filename") == "gz-sim-diff-drive-system"]
        assert len(dd_plugins) == 1

    def test_model_name(self, uni_sdf):
        """Model name must be uni_agv."""
        root = _parse_sdf(uni_sdf)
        model = root.find("model")
        assert model.attrib.get("name") == "uni_agv"

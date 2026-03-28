#!/usr/bin/env python3
"""
Generate Gazebo Fortress SDF robot model from robot YAML config.

Reads the same YAML used by C++ Config and generates a complete robot SDF
model with:
  - Chassis box (visual + collision) from dimensions in YAML
  - Drive wheels (2 for differential, 4 for unidirectional)
  - Caster wheel(s) for differential drive
  - LiDAR sensor (GPU ray, FOV/range/rays from YAML)
  - IMU sensor (if enabled in YAML)
  - Differential drive plugin (max velocity from YAML)

Usage:
  python3 gazebo/scripts/generate_robot.py configs/robots/differential_drive.yaml
  python3 gazebo/scripts/generate_robot.py configs/robots/unidirectional.yaml

Output: gazebo/models/{robot_name}/model.sdf
"""

import math
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.dom import minidom

import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _indent_xml(elem: ET.Element) -> str:
    """Pretty-print an ElementTree element as a string."""
    rough = ET.tostring(elem, encoding="unicode")
    parsed = minidom.parseString(rough)
    return parsed.toprettyxml(indent="  ", encoding=None)


def _add_sub(parent: ET.Element, tag: str, text: str | None = None, **attribs) -> ET.Element:
    elem = ET.SubElement(parent, tag, **attribs)
    if text is not None:
        elem.text = str(text)
    return elem


def _pose_str(x: float, y: float, z: float,
              roll: float = 0, pitch: float = 0, yaw: float = 0) -> str:
    return f"{x} {y} {z} {roll} {pitch} {yaw}"


def _inertial_box(mass: float, sx: float, sy: float, sz: float, parent: ET.Element):
    """Add <inertial> block for a box shape."""
    inertial = _add_sub(parent, "inertial")
    _add_sub(inertial, "mass", str(mass))
    inertia = _add_sub(inertial, "inertia")
    ixx = mass / 12.0 * (sy * sy + sz * sz)
    iyy = mass / 12.0 * (sx * sx + sz * sz)
    izz = mass / 12.0 * (sx * sx + sy * sy)
    _add_sub(inertia, "ixx", f"{ixx:.6f}")
    _add_sub(inertia, "ixy", "0")
    _add_sub(inertia, "ixz", "0")
    _add_sub(inertia, "iyy", f"{iyy:.6f}")
    _add_sub(inertia, "iyz", "0")
    _add_sub(inertia, "izz", f"{izz:.6f}")


def _inertial_cylinder(mass: float, radius: float, length: float, parent: ET.Element):
    """Add <inertial> block for a cylinder shape."""
    inertial = _add_sub(parent, "inertial")
    _add_sub(inertial, "mass", str(mass))
    inertia = _add_sub(inertial, "inertia")
    ixx = mass / 12.0 * (3 * radius * radius + length * length)
    iyy = ixx
    izz = mass / 2.0 * radius * radius
    _add_sub(inertia, "ixx", f"{ixx:.6f}")
    _add_sub(inertia, "ixy", "0")
    _add_sub(inertia, "ixz", "0")
    _add_sub(inertia, "iyy", f"{iyy:.6f}")
    _add_sub(inertia, "iyz", "0")
    _add_sub(inertia, "izz", f"{izz:.6f}")


def _add_visual_collision_box(link: ET.Element, name: str,
                               sx: float, sy: float, sz: float,
                               r: float, g: float, b: float, a: float = 1.0):
    """Add visual + collision box to a link."""
    for kind in ("visual", "collision"):
        elem = _add_sub(link, kind, name=f"{name}_{kind}")
        geom = _add_sub(elem, "geometry")
        box = _add_sub(geom, "box")
        _add_sub(box, "size", f"{sx} {sy} {sz}")
        if kind == "visual":
            mat = _add_sub(elem, "material")
            _add_sub(mat, "ambient", f"{r} {g} {b} {a}")
            _add_sub(mat, "diffuse", f"{r} {g} {b} {a}")


def _add_visual_collision_cylinder(link: ET.Element, name: str,
                                    radius: float, length: float,
                                    r: float, g: float, b: float, a: float = 1.0):
    """Add visual + collision cylinder to a link."""
    for kind in ("visual", "collision"):
        elem = _add_sub(link, kind, name=f"{name}_{kind}")
        geom = _add_sub(elem, "geometry")
        cyl = _add_sub(geom, "cylinder")
        _add_sub(cyl, "radius", str(radius))
        _add_sub(cyl, "length", str(length))
        if kind == "visual":
            mat = _add_sub(elem, "material")
            _add_sub(mat, "ambient", f"{r} {g} {b} {a}")
            _add_sub(mat, "diffuse", f"{r} {g} {b} {a}")


# ---------------------------------------------------------------------------
# Robot model construction
# ---------------------------------------------------------------------------

def _build_chassis(model: ET.Element, cfg: dict) -> ET.Element:
    """Build the chassis link from YAML dimensions."""
    dims = cfg["dimensions"]
    length = dims["length"]
    width = dims["width"]
    height = dims["height"]
    weight = dims["weight"]
    wheel_radius = dims["wheel_radius"]

    # Chassis center is at wheel_radius + height/2 above ground
    chassis_z = wheel_radius + height / 2

    link = _add_sub(model, "link", name="chassis")
    _add_sub(link, "pose", _pose_str(0, 0, chassis_z))
    _inertial_box(weight, length, width, height, link)
    _add_visual_collision_box(link, "chassis", length, width, height,
                               0.2, 0.2, 0.8)  # blue-ish
    return link


def _build_wheel(model: ET.Element, name: str, x: float, y: float,
                 radius: float, width: float, chassis_z: float, chassis_height: float):
    """Build a single wheel link + joint."""
    wheel_z = radius  # wheel center height

    link = _add_sub(model, "link", name=name)
    # Wheel rotates around its Y axis, oriented with roll=pi/2
    _add_sub(link, "pose", _pose_str(x, y, wheel_z, math.pi / 2, 0, 0))
    wheel_mass = 1.0
    _inertial_cylinder(wheel_mass, radius, width, link)
    _add_visual_collision_cylinder(link, name, radius, width, 0.1, 0.1, 0.1)

    # Surface friction
    col = link.find(f".//collision[@name='{name}_collision']")
    if col is not None:
        surface = _add_sub(col, "surface")
        friction = _add_sub(surface, "friction")
        ode = _add_sub(friction, "ode")
        _add_sub(ode, "mu", "1.0")
        _add_sub(ode, "mu2", "1.0")

    # Revolute joint — wheel to chassis
    joint = _add_sub(model, "joint", name=f"{name}_joint", type="revolute")
    _add_sub(joint, "parent", "chassis")
    _add_sub(joint, "child", name)
    axis = _add_sub(joint, "axis")
    _add_sub(axis, "xyz", "0 0 1")  # local Z is wheel rotation axis after roll
    limit = _add_sub(axis, "limit")
    _add_sub(limit, "lower", "-1e16")
    _add_sub(limit, "upper", "1e16")

    return link


def _build_caster(model: ET.Element, name: str, x: float, y: float,
                  radius: float):
    """Build a caster wheel (sphere) link + joint."""
    link = _add_sub(model, "link", name=name)
    _add_sub(link, "pose", _pose_str(x, y, radius))
    caster_mass = 0.5
    inertial = _add_sub(link, "inertial")
    _add_sub(inertial, "mass", str(caster_mass))
    inertia = _add_sub(inertial, "inertia")
    i_val = 2.0 / 5.0 * caster_mass * radius * radius
    _add_sub(inertia, "ixx", f"{i_val:.6f}")
    _add_sub(inertia, "ixy", "0")
    _add_sub(inertia, "ixz", "0")
    _add_sub(inertia, "iyy", f"{i_val:.6f}")
    _add_sub(inertia, "iyz", "0")
    _add_sub(inertia, "izz", f"{i_val:.6f}")

    # Visual + collision sphere
    for kind in ("visual", "collision"):
        elem = _add_sub(link, kind, name=f"{name}_{kind}")
        geom = _add_sub(elem, "geometry")
        sphere = _add_sub(geom, "sphere")
        _add_sub(sphere, "radius", str(radius))
        if kind == "visual":
            mat = _add_sub(elem, "material")
            _add_sub(mat, "ambient", "0.3 0.3 0.3 1.0")
            _add_sub(mat, "diffuse", "0.3 0.3 0.3 1.0")

    # Low-friction surface
    col = link.find(f".//collision[@name='{name}_collision']")
    if col is not None:
        surface = _add_sub(col, "surface")
        friction = _add_sub(surface, "friction")
        ode = _add_sub(friction, "ode")
        _add_sub(ode, "mu", "0.01")
        _add_sub(ode, "mu2", "0.01")

    # Ball joint to chassis
    joint = _add_sub(model, "joint", name=f"{name}_joint", type="ball")
    _add_sub(joint, "parent", "chassis")
    _add_sub(joint, "child", name)


def _build_lidar_sensor(model: ET.Element, cfg: dict, chassis_link: ET.Element):
    """Add a LiDAR sensor link + fixed joint to the chassis."""
    lidar_cfg = cfg["sensors"]["lidar"]
    if not lidar_cfg.get("enabled", False):
        return

    dims = cfg["dimensions"]
    height = dims["height"]
    wheel_radius = dims["wheel_radius"]
    lidar_z = wheel_radius + height + 0.02  # just above chassis top

    lidar_height_m = lidar_cfg.get("height_m", 0.15)
    fov_deg = lidar_cfg.get("fov_deg", 360)
    range_m = lidar_cfg.get("range_m", 5.0)
    rays = lidar_cfg.get("rays", 360)
    noise_stddev = lidar_cfg.get("noise_stddev_m", 0.03)

    fov_rad = math.radians(fov_deg)
    half_fov = fov_rad / 2

    # LiDAR link
    link = _add_sub(model, "link", name="lidar_link")
    _add_sub(link, "pose", _pose_str(0, 0, lidar_z))

    # Small cylinder visual for the lidar puck
    lidar_puck_r = 0.04
    lidar_puck_h = 0.03
    _inertial_cylinder(0.1, lidar_puck_r, lidar_puck_h, link)
    _add_visual_collision_cylinder(link, "lidar_puck", lidar_puck_r, lidar_puck_h,
                                    0.1, 0.1, 0.1)

    # Sensor element
    sensor = _add_sub(link, "sensor", name="lidar_sensor", type="gpu_lidar")
    _add_sub(sensor, "always_on", "true")
    _add_sub(sensor, "update_rate", "10")
    _add_sub(sensor, "visualize", "true")
    _add_sub(sensor, "topic", "lidar")

    ray = _add_sub(sensor, "ray")
    scan = _add_sub(ray, "scan")
    horizontal = _add_sub(scan, "horizontal")
    _add_sub(horizontal, "samples", str(rays))
    _add_sub(horizontal, "resolution", "1")
    _add_sub(horizontal, "min_angle", f"{-half_fov:.6f}")
    _add_sub(horizontal, "max_angle", f"{half_fov:.6f}")

    range_elem = _add_sub(ray, "range")
    _add_sub(range_elem, "min", "0.08")
    _add_sub(range_elem, "max", str(range_m))
    _add_sub(range_elem, "resolution", "0.01")

    noise = _add_sub(ray, "noise")
    _add_sub(noise, "type", "gaussian")
    _add_sub(noise, "mean", "0.0")
    _add_sub(noise, "stddev", str(noise_stddev))

    # Fixed joint
    joint = _add_sub(model, "joint", name="lidar_joint", type="fixed")
    _add_sub(joint, "parent", "chassis")
    _add_sub(joint, "child", "lidar_link")


def _build_imu_sensor(model: ET.Element, cfg: dict):
    """Add an IMU sensor to the chassis if enabled."""
    imu_cfg = cfg["sensors"].get("imu", {})
    if not imu_cfg.get("enabled", False):
        return

    noise_stddev_deg = imu_cfg.get("noise_stddev_deg", 3.0)
    noise_stddev_rad = math.radians(noise_stddev_deg)

    # IMU link — co-located with chassis
    dims = cfg["dimensions"]
    wheel_radius = dims["wheel_radius"]
    height = dims["height"]
    imu_z = wheel_radius + height / 2

    link = _add_sub(model, "link", name="imu_link")
    _add_sub(link, "pose", _pose_str(0, 0, imu_z))
    # Minimal inertia for IMU
    inertial = _add_sub(link, "inertial")
    _add_sub(inertial, "mass", "0.01")
    inertia = _add_sub(inertial, "inertia")
    for tag in ("ixx", "iyy", "izz"):
        _add_sub(inertia, tag, "0.000001")
    for tag in ("ixy", "ixz", "iyz"):
        _add_sub(inertia, tag, "0")

    sensor = _add_sub(link, "sensor", name="imu_sensor", type="imu")
    _add_sub(sensor, "always_on", "true")
    _add_sub(sensor, "update_rate", "100")
    _add_sub(sensor, "topic", "imu")

    imu_elem = _add_sub(sensor, "imu")
    ang_vel = _add_sub(imu_elem, "angular_velocity")
    for axis_name in ("x", "y", "z"):
        axis_el = _add_sub(ang_vel, axis_name)
        noise = _add_sub(axis_el, "noise", type="gaussian")
        _add_sub(noise, "mean", "0.0")
        _add_sub(noise, "stddev", str(noise_stddev_rad))

    lin_acc = _add_sub(imu_elem, "linear_acceleration")
    for axis_name in ("x", "y", "z"):
        axis_el = _add_sub(lin_acc, axis_name)
        noise = _add_sub(axis_el, "noise", type="gaussian")
        _add_sub(noise, "mean", "0.0")
        _add_sub(noise, "stddev", "0.01")

    # Fixed joint
    joint = _add_sub(model, "joint", name="imu_joint", type="fixed")
    _add_sub(joint, "parent", "chassis")
    _add_sub(joint, "child", "imu_link")


def _build_diff_drive_plugin(model: ET.Element, cfg: dict):
    """Add the Gazebo Fortress differential drive plugin."""
    motion = cfg["motion"]
    dims = cfg["dimensions"]

    plugin = _add_sub(model, "plugin",
                       filename="gz-sim-diff-drive-system",
                       name="gz::sim::systems::DiffDrive")
    _add_sub(plugin, "left_joint", "left_wheel_joint")
    _add_sub(plugin, "right_joint", "right_wheel_joint")
    _add_sub(plugin, "wheel_separation", str(dims["wheel_separation"]))
    _add_sub(plugin, "wheel_radius", str(dims["wheel_radius"]))
    _add_sub(plugin, "max_linear_acceleration", str(motion["linear_acceleration"]))
    _add_sub(plugin, "max_angular_velocity", str(motion["max_angular_velocity"]))
    _add_sub(plugin, "topic", "cmd_vel")
    _add_sub(plugin, "odom_topic", "odom")
    _add_sub(plugin, "tf_topic", "tf")
    _add_sub(plugin, "frame_id", "odom")
    _add_sub(plugin, "child_frame_id", "chassis")
    _add_sub(plugin, "odom_publish_frequency", "15")


def _build_joint_state_publisher(model: ET.Element):
    """Add joint state publisher plugin."""
    plugin = _add_sub(model, "plugin",
                       filename="gz-sim-joint-state-publisher-system",
                       name="gz::sim::systems::JointStatePublisher")


# ---------------------------------------------------------------------------
# Main generation
# ---------------------------------------------------------------------------

def generate_robot(yaml_path: str, output_dir: str | None = None) -> str:
    """
    Generate a Gazebo Fortress SDF robot model from a robot YAML config.

    Args:
        yaml_path: Path to the robot YAML config.
        output_dir: Base directory for models. Defaults to gazebo/models/.

    Returns:
        Path to the generated model.sdf file.
    """
    yaml_path = Path(yaml_path).resolve()
    with open(yaml_path) as f:
        cfg = yaml.safe_load(f)

    robot_name = cfg["name"]
    robot_type = cfg["type"]  # differential_drive, unidirectional
    safe_robot_name = robot_name.replace(" ", "_").lower()

    # Output path
    if output_dir is None:
        project_root = Path(__file__).resolve().parent.parent.parent
        output_dir = project_root / "gazebo" / "models" / safe_robot_name
    else:
        output_dir = Path(output_dir) / safe_robot_name
    output_dir.mkdir(parents=True, exist_ok=True)
    sdf_path = output_dir / "model.sdf"

    dims = cfg["dimensions"]
    length = dims["length"]
    width = dims["width"]
    height = dims["height"]
    wheel_sep = dims["wheel_separation"]
    wheel_radius = dims["wheel_radius"]
    wheel_width = 0.04  # standard wheel width

    chassis_z = wheel_radius + height / 2

    # Build SDF
    sdf = ET.Element("sdf", version="1.9")
    model = _add_sub(sdf, "model", name=safe_robot_name)
    _add_sub(model, "self_collide", "false")

    # Chassis
    chassis_link = _build_chassis(model, cfg)

    if robot_type == "differential_drive":
        # Two drive wheels + one front caster + one rear caster
        _build_wheel(model, "left_wheel",
                     0, wheel_sep / 2,
                     wheel_radius, wheel_width, chassis_z, height)
        _build_wheel(model, "right_wheel",
                     0, -wheel_sep / 2,
                     wheel_radius, wheel_width, chassis_z, height)

        # Front and rear casters — smaller than drive wheels
        caster_radius = wheel_radius * 0.5
        _build_caster(model, "front_caster",
                      length / 2 - caster_radius, 0, caster_radius)
        _build_caster(model, "rear_caster",
                      -(length / 2 - caster_radius), 0, caster_radius)

        # Diff drive plugin
        _build_diff_drive_plugin(model, cfg)

    elif robot_type == "unidirectional":
        # Four wheels at corners
        half_l = length / 2 - wheel_radius
        half_w = wheel_sep / 2

        _build_wheel(model, "front_left_wheel",
                     half_l, half_w, wheel_radius, wheel_width, chassis_z, height)
        _build_wheel(model, "front_right_wheel",
                     half_l, -half_w, wheel_radius, wheel_width, chassis_z, height)
        _build_wheel(model, "rear_left_wheel",
                     -half_l, half_w, wheel_radius, wheel_width, chassis_z, height)
        _build_wheel(model, "rear_right_wheel",
                     -half_l, -half_w, wheel_radius, wheel_width, chassis_z, height)

        # Use diff drive plugin with front wheels as primary
        plugin = _add_sub(model, "plugin",
                           filename="gz-sim-diff-drive-system",
                           name="gz::sim::systems::DiffDrive")
        _add_sub(plugin, "left_joint", "front_left_wheel_joint")
        _add_sub(plugin, "right_joint", "front_right_wheel_joint")
        _add_sub(plugin, "wheel_separation", str(wheel_sep))
        _add_sub(plugin, "wheel_radius", str(wheel_radius))
        _add_sub(plugin, "max_linear_acceleration",
                 str(cfg["motion"]["linear_acceleration"]))
        _add_sub(plugin, "max_angular_velocity",
                 str(cfg["motion"]["max_angular_velocity"]))
        _add_sub(plugin, "topic", "cmd_vel")
        _add_sub(plugin, "odom_topic", "odom")
        _add_sub(plugin, "tf_topic", "tf")
        _add_sub(plugin, "frame_id", "odom")
        _add_sub(plugin, "child_frame_id", "chassis")
        _add_sub(plugin, "odom_publish_frequency", "15")

    else:
        raise ValueError(f"Unknown robot type: {robot_type}")

    # LiDAR
    _build_lidar_sensor(model, cfg, chassis_link)

    # IMU
    _build_imu_sensor(model, cfg)

    # Joint state publisher
    _build_joint_state_publisher(model)

    # Write SDF
    xml_str = _indent_xml(sdf)
    with open(sdf_path, "w") as f:
        f.write(xml_str)

    # Write model.config for Gazebo model discovery
    config_path = output_dir / "model.config"
    config_root = ET.Element("model")
    _add_sub(config_root, "name", robot_name)
    _add_sub(config_root, "version", "1.0")
    _add_sub(config_root, "sdf", "model.sdf", version="1.9")
    author = _add_sub(config_root, "author")
    _add_sub(author, "name", "Autonomous Factory")
    _add_sub(config_root, "description", f"Gazebo model for {robot_name} ({robot_type})")

    config_str = _indent_xml(config_root)
    with open(config_path, "w") as f:
        f.write(config_str)

    print(f"Generated: {sdf_path}")
    print(f"  Robot: {robot_name} ({robot_type})")
    print(f"  Dimensions: {length}x{width}x{height}m")
    print(f"  Wheel radius: {wheel_radius}m, separation: {wheel_sep}m")
    print(f"  LiDAR: {'enabled' if cfg['sensors']['lidar'].get('enabled') else 'disabled'}")
    print(f"  IMU: {'enabled' if cfg['sensors'].get('imu', {}).get('enabled') else 'disabled'}")

    return str(sdf_path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <robot_yaml_path> [output_dir]")
        sys.exit(1)

    yaml_file = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else None
    generate_robot(yaml_file, out_dir)

#!/usr/bin/env python3
"""
Generate Gazebo SDF robot models from configs/robots/*.yaml.

Reads each robot YAML config and produces a physically accurate SDF model
with correct dimensions, mass, wheel geometry, LiDAR specs, IMU, and
drive plugin configuration.

Usage:
    python3 generate_robot_sdf.py                    # Generate all
    python3 generate_robot_sdf.py addverb_dynamo     # Generate one

Output: gazebo/models/<manufacturer>/<robot_name>/model.sdf + model.config
"""

import math
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
CONFIGS_DIR = PROJECT_ROOT / "configs" / "robots"
MODELS_DIR = SCRIPT_DIR.parent / "models"

# ── Manufacturer classification ──────────────────────────────
# Map robot config filename (without .yaml) to manufacturer
MANUFACTURER_MAP = {
    "addverb_dynamo": "addverb",
    "addverb_veloce": "addverb",
    "addverb_quadron": "addverb",
    "amr500": "addverb",
    "zippy10": "addverb",
    "differential_drive": "generic",
    "unidirectional": "generic",
}

# Visual colors per manufacturer (RGBA)
COLORS = {
    "addverb": {"chassis": "0.9 0.35 0.1 1.0", "accent": "0.2 0.2 0.2 1.0"},     # Addverb orange
    "generic": {"chassis": "0.2 0.2 0.8 1.0", "accent": "0.1 0.1 0.1 1.0"},       # Blue
    "hai_robotics": {"chassis": "0.0 0.6 0.9 1.0", "accent": "0.2 0.2 0.2 1.0"},  # Hai blue
    "geekplus": {"chassis": "0.1 0.7 0.3 1.0", "accent": "0.2 0.2 0.2 1.0"},      # Geek+ green
    "locus": {"chassis": "0.6 0.0 0.7 1.0", "accent": "0.3 0.3 0.3 1.0"},         # Locus purple
    "mir": {"chassis": "0.95 0.95 0.95 1.0", "accent": "0.1 0.4 0.8 1.0"},        # MiR white+blue
    "fetch": {"chassis": "0.15 0.15 0.15 1.0", "accent": "0.0 0.7 0.4 1.0"},      # Fetch dark+green
}


def load_robot_config(yaml_path: Path) -> dict:
    """Load and normalize a robot YAML config."""
    with open(yaml_path) as f:
        cfg = yaml.safe_load(f)

    dims = cfg.get("dimensions", {})
    # Normalize: some configs have length_front/length_rear instead of length
    if "length" not in dims and "length_front" in dims:
        dims["length"] = dims.get("length_front", 0.5) + dims.get("length_rear", 0.5)
    if "width" not in dims and "width_left" in dims:
        dims["width"] = dims.get("width_left", 0.35) + dims.get("width_right", 0.35)
    if "height" not in dims:
        dims["height"] = dims.get("height_top", 0.15) + dims.get("height_bottom", 0.15)

    # Default wheel params if missing
    if "wheel_separation" not in dims:
        dims["wheel_separation"] = dims.get("width", 0.6) * 0.75
    if "wheel_radius" not in dims:
        dims["wheel_radius"] = 0.06

    cfg["dimensions"] = dims
    return cfg


def compute_inertia(mass: float, lx: float, ly: float, lz: float):
    """Box inertia tensor."""
    return {
        "ixx": mass / 12.0 * (ly**2 + lz**2),
        "iyy": mass / 12.0 * (lx**2 + lz**2),
        "izz": mass / 12.0 * (lx**2 + ly**2),
    }


def compute_wheel_inertia(mass: float, radius: float, length: float):
    """Cylinder inertia (wheel)."""
    return {
        "ixx": mass / 12.0 * (3 * radius**2 + length**2),
        "iyy": mass / 12.0 * (3 * radius**2 + length**2),
        "izz": mass * radius**2 / 2.0,
    }


def generate_sdf(cfg: dict, manufacturer: str) -> str:
    """Generate SDF XML string from robot config."""
    name = cfg["name"].replace(" ", "_")
    dims = cfg["dimensions"]
    motion = cfg.get("motion", {})
    sensors = cfg.get("sensors", {})
    battery = cfg.get("battery", {})

    lx = dims.get("length", 0.8)
    ly = dims.get("width", 0.6)
    lz = dims.get("height", 0.3)
    wheel_sep = dims["wheel_separation"]
    wheel_rad = dims["wheel_radius"]
    wheel_width = 0.04
    payload = dims.get("payload_capacity", 100)

    # Chassis mass = weight + fraction of payload for inertia
    chassis_mass = dims.get("weight", 50.0)
    chassis_z = lz / 2.0 + wheel_rad  # chassis center height

    color = COLORS.get(manufacturer, COLORS["generic"])
    chassis_color = color["chassis"]
    wheel_color = color["accent"]

    ci = compute_inertia(chassis_mass, lx, ly, lz)
    wi = compute_wheel_inertia(1.0, wheel_rad, wheel_width)
    caster_rad = wheel_rad / 2.0
    caster_x = lx * 0.45  # 90% of half-length

    # LiDAR config
    lidar_cfg = sensors.get("lidar", {})
    lidar_enabled = lidar_cfg.get("enabled", True)
    lidar_fov_deg = lidar_cfg.get("fov_deg", 360)
    lidar_range = lidar_cfg.get("range_m", 5.0)
    lidar_rays = lidar_cfg.get("rays", 360)
    lidar_height = lidar_cfg.get("height_m", lz + 0.02)
    lidar_noise = lidar_cfg.get("noise_stddev_m", 0.03)

    # Obstacle sensor fallback (AMR500 style)
    if not lidar_enabled or lidar_fov_deg == 0:
        obs_sensor = sensors.get("obstacle_sensor", {})
        if obs_sensor:
            s0 = obs_sensor.get("sensor_0", {})
            fov_min = s0.get("fov_min_rad", -0.52)
            fov_max = s0.get("fov_max_rad", 0.52)
            lidar_fov_deg = math.degrees(fov_max - fov_min)
            lidar_range = s0.get("range_m", 3.0)
            lidar_rays = max(30, int(lidar_fov_deg * 2))
            lidar_enabled = True

    if lidar_fov_deg >= 360:
        lidar_min_angle = -math.pi
        lidar_max_angle = math.pi
    else:
        half_fov = math.radians(lidar_fov_deg / 2)
        lidar_min_angle = -half_fov
        lidar_max_angle = half_fov

    # IMU config
    imu_cfg = sensors.get("imu", {})
    imu_enabled = imu_cfg.get("enabled", True)
    imu_noise = math.radians(imu_cfg.get("noise_stddev_deg", 3.0))

    # Drive plugin
    max_lin_accel = motion.get("linear_acceleration", 0.8)
    max_ang_vel = motion.get("max_angular_velocity", 2.5)

    # Build SDF
    sdf = f"""<?xml version="1.0" ?>
<sdf version="1.9">
  <model name="{name}">
    <self_collide>false</self_collide>

    <!-- ══ Chassis ══ -->
    <link name="chassis">
      <pose>0 0 {chassis_z:.6f} 0 0 0</pose>
      <inertial>
        <mass>{chassis_mass:.1f}</mass>
        <inertia>
          <ixx>{ci['ixx']:.6f}</ixx><ixy>0</ixy><ixz>0</ixz>
          <iyy>{ci['iyy']:.6f}</iyy><iyz>0</iyz>
          <izz>{ci['izz']:.6f}</izz>
        </inertia>
      </inertial>
      <visual name="chassis_visual">
        <geometry><box><size>{lx} {ly} {lz}</size></box></geometry>
        <material>
          <ambient>{chassis_color}</ambient>
          <diffuse>{chassis_color}</diffuse>
        </material>
      </visual>
      <collision name="chassis_collision">
        <geometry><box><size>{lx} {ly} {lz}</size></box></geometry>
      </collision>
    </link>

    <!-- ══ Left Wheel ══ -->
    <link name="left_wheel">
      <pose>0 {wheel_sep/2:.6f} {wheel_rad:.6f} {math.pi/2:.10f} 0 0</pose>
      <inertial>
        <mass>1.0</mass>
        <inertia>
          <ixx>{wi['ixx']:.6f}</ixx><ixy>0</ixy><ixz>0</ixz>
          <iyy>{wi['iyy']:.6f}</iyy><iyz>0</iyz>
          <izz>{wi['izz']:.6f}</izz>
        </inertia>
      </inertial>
      <visual name="left_wheel_visual">
        <geometry><cylinder><radius>{wheel_rad}</radius><length>{wheel_width}</length></cylinder></geometry>
        <material><ambient>{wheel_color}</ambient><diffuse>{wheel_color}</diffuse></material>
      </visual>
      <collision name="left_wheel_collision">
        <geometry><cylinder><radius>{wheel_rad}</radius><length>{wheel_width}</length></cylinder></geometry>
        <surface><friction><ode><mu>1.0</mu><mu2>1.0</mu2></ode></friction></surface>
      </collision>
    </link>
    <joint name="left_wheel_joint" type="revolute">
      <parent>chassis</parent><child>left_wheel</child>
      <axis><xyz>0 0 1</xyz><limit><lower>-1e16</lower><upper>1e16</upper></limit></axis>
    </joint>

    <!-- ══ Right Wheel ══ -->
    <link name="right_wheel">
      <pose>0 {-wheel_sep/2:.6f} {wheel_rad:.6f} {math.pi/2:.10f} 0 0</pose>
      <inertial>
        <mass>1.0</mass>
        <inertia>
          <ixx>{wi['ixx']:.6f}</ixx><ixy>0</ixy><ixz>0</ixz>
          <iyy>{wi['iyy']:.6f}</iyy><iyz>0</iyz>
          <izz>{wi['izz']:.6f}</izz>
        </inertia>
      </inertial>
      <visual name="right_wheel_visual">
        <geometry><cylinder><radius>{wheel_rad}</radius><length>{wheel_width}</length></cylinder></geometry>
        <material><ambient>{wheel_color}</ambient><diffuse>{wheel_color}</diffuse></material>
      </visual>
      <collision name="right_wheel_collision">
        <geometry><cylinder><radius>{wheel_rad}</radius><length>{wheel_width}</length></cylinder></geometry>
        <surface><friction><ode><mu>1.0</mu><mu2>1.0</mu2></ode></friction></surface>
      </collision>
    </link>
    <joint name="right_wheel_joint" type="revolute">
      <parent>chassis</parent><child>right_wheel</child>
      <axis><xyz>0 0 1</xyz><limit><lower>-1e16</lower><upper>1e16</upper></limit></axis>
    </joint>

    <!-- ══ Front Caster ══ -->
    <link name="front_caster">
      <pose>{caster_x:.6f} 0 {caster_rad:.6f} 0 0 0</pose>
      <inertial>
        <mass>0.5</mass>
        <inertia><ixx>0.000281</ixx><ixy>0</ixy><ixz>0</ixz><iyy>0.000281</iyy><iyz>0</iyz><izz>0.000281</izz></inertia>
      </inertial>
      <visual name="front_caster_visual">
        <geometry><sphere><radius>{caster_rad:.6f}</radius></sphere></geometry>
        <material><ambient>0.3 0.3 0.3 1.0</ambient><diffuse>0.3 0.3 0.3 1.0</diffuse></material>
      </visual>
      <collision name="front_caster_collision">
        <geometry><sphere><radius>{caster_rad:.6f}</radius></sphere></geometry>
        <surface><friction><ode><mu>0.01</mu><mu2>0.01</mu2></ode></friction></surface>
      </collision>
    </link>
    <joint name="front_caster_joint" type="ball"><parent>chassis</parent><child>front_caster</child></joint>

    <!-- ══ Rear Caster ══ -->
    <link name="rear_caster">
      <pose>{-caster_x:.6f} 0 {caster_rad:.6f} 0 0 0</pose>
      <inertial>
        <mass>0.5</mass>
        <inertia><ixx>0.000281</ixx><ixy>0</ixy><ixz>0</ixz><iyy>0.000281</iyy><iyz>0</iyz><izz>0.000281</izz></inertia>
      </inertial>
      <visual name="rear_caster_visual">
        <geometry><sphere><radius>{caster_rad:.6f}</radius></sphere></geometry>
        <material><ambient>0.3 0.3 0.3 1.0</ambient><diffuse>0.3 0.3 0.3 1.0</diffuse></material>
      </visual>
      <collision name="rear_caster_collision">
        <geometry><sphere><radius>{caster_rad:.6f}</radius></sphere></geometry>
        <surface><friction><ode><mu>0.01</mu><mu2>0.01</mu2></ode></friction></surface>
      </collision>
    </link>
    <joint name="rear_caster_joint" type="ball"><parent>chassis</parent><child>rear_caster</child></joint>

    <!-- ══ DiffDrive Plugin ══ -->
    <plugin filename="gz-sim-diff-drive-system" name="gz::sim::systems::DiffDrive">
      <left_joint>left_wheel_joint</left_joint>
      <right_joint>right_wheel_joint</right_joint>
      <wheel_separation>{wheel_sep}</wheel_separation>
      <wheel_radius>{wheel_rad}</wheel_radius>
      <max_linear_acceleration>{max_lin_accel}</max_linear_acceleration>
      <max_angular_velocity>{max_ang_vel}</max_angular_velocity>
      <topic>cmd_vel</topic>
      <odom_topic>odom</odom_topic>
      <tf_topic>tf</tf_topic>
      <frame_id>odom</frame_id>
      <child_frame_id>chassis</child_frame_id>
      <odom_publish_frequency>15</odom_publish_frequency>
    </plugin>"""

    # LiDAR sensor
    if lidar_enabled:
        lidar_z = chassis_z + lz / 2.0 + 0.02
        sdf += f"""

    <!-- ══ LiDAR ══ -->
    <link name="lidar_link">
      <pose>0 0 {lidar_z:.6f} 0 0 0</pose>
      <inertial>
        <mass>0.1</mass>
        <inertia><ixx>0.000047</ixx><ixy>0</ixy><ixz>0</ixz><iyy>0.000047</iyy><iyz>0</iyz><izz>0.000080</izz></inertia>
      </inertial>
      <visual name="lidar_puck_visual">
        <geometry><cylinder><radius>0.04</radius><length>0.03</length></cylinder></geometry>
        <material><ambient>0.1 0.1 0.1 1.0</ambient><diffuse>0.1 0.1 0.1 1.0</diffuse></material>
      </visual>
      <sensor name="lidar_sensor" type="gpu_lidar">
        <always_on>true</always_on>
        <update_rate>10</update_rate>
        <visualize>true</visualize>
        <topic>lidar</topic>
        <ray>
          <scan>
            <horizontal>
              <samples>{lidar_rays}</samples>
              <resolution>1</resolution>
              <min_angle>{lidar_min_angle:.6f}</min_angle>
              <max_angle>{lidar_max_angle:.6f}</max_angle>
            </horizontal>
          </scan>
          <range>
            <min>0.08</min>
            <max>{lidar_range}</max>
            <resolution>0.01</resolution>
          </range>
          <noise><type>gaussian</type><mean>0.0</mean><stddev>{lidar_noise}</stddev></noise>
        </ray>
      </sensor>
    </link>
    <joint name="lidar_joint" type="fixed"><parent>chassis</parent><child>lidar_link</child></joint>"""

    # IMU sensor
    if imu_enabled:
        sdf += f"""

    <!-- ══ IMU ══ -->
    <link name="imu_link">
      <pose>0 0 {chassis_z:.6f} 0 0 0</pose>
      <inertial>
        <mass>0.01</mass>
        <inertia><ixx>0.000001</ixx><iyy>0.000001</iyy><izz>0.000001</izz><ixy>0</ixy><ixz>0</ixz><iyz>0</iyz></inertia>
      </inertial>
      <sensor name="imu_sensor" type="imu">
        <always_on>true</always_on>
        <update_rate>100</update_rate>
        <topic>imu</topic>
        <imu>
          <angular_velocity>
            <x><noise type="gaussian"><mean>0.0</mean><stddev>{imu_noise:.10f}</stddev></noise></x>
            <y><noise type="gaussian"><mean>0.0</mean><stddev>{imu_noise:.10f}</stddev></noise></y>
            <z><noise type="gaussian"><mean>0.0</mean><stddev>{imu_noise:.10f}</stddev></noise></z>
          </angular_velocity>
          <linear_acceleration>
            <x><noise type="gaussian"><mean>0.0</mean><stddev>0.01</stddev></noise></x>
            <y><noise type="gaussian"><mean>0.0</mean><stddev>0.01</stddev></noise></y>
            <z><noise type="gaussian"><mean>0.0</mean><stddev>0.01</stddev></noise></z>
          </linear_acceleration>
        </imu>
      </sensor>
    </link>
    <joint name="imu_joint" type="fixed"><parent>chassis</parent><child>imu_link</child></joint>"""

    sdf += """

    <plugin filename="gz-sim-joint-state-publisher-system" name="gz::sim::systems::JointStatePublisher"/>
  </model>
</sdf>
"""
    return sdf


def generate_model_config(name: str, manufacturer: str, description: str) -> str:
    """Generate model.config XML."""
    return f"""<?xml version="1.0" ?>
<model>
  <name>{name}</name>
  <version>1.0</version>
  <sdf version="1.9">model.sdf</sdf>
  <author>
    <name>RDT Generator</name>
    <email>meharban@rdt.dev</email>
  </author>
  <description>{description} — {manufacturer}</description>
</model>
"""


def main():
    filter_name = sys.argv[1] if len(sys.argv) > 1 else None

    yaml_files = sorted(CONFIGS_DIR.glob("*.yaml"))
    if not yaml_files:
        print(f"No YAML files found in {CONFIGS_DIR}")
        sys.exit(1)

    generated = []
    for yaml_path in yaml_files:
        config_name = yaml_path.stem  # e.g., "addverb_dynamo"
        if filter_name and config_name != filter_name:
            continue

        manufacturer = MANUFACTURER_MAP.get(config_name, "other")
        cfg = load_robot_config(yaml_path)
        robot_name = cfg["name"].replace(" ", "_").lower()

        # Output path: gazebo/models/<manufacturer>/<robot_name>/
        model_dir = MODELS_DIR / manufacturer / robot_name
        model_dir.mkdir(parents=True, exist_ok=True)

        # Generate SDF
        sdf_content = generate_sdf(cfg, manufacturer)
        sdf_path = model_dir / "model.sdf"
        sdf_path.write_text(sdf_content)

        # Generate model.config
        dims = cfg["dimensions"]
        desc = f"{cfg['name']} ({dims.get('payload_capacity', '?')}kg payload, {cfg.get('type', '?')} drive)"
        config_content = generate_model_config(cfg["name"], manufacturer, desc)
        (model_dir / "model.config").write_text(config_content)

        generated.append(f"  {manufacturer}/{robot_name}/ ({config_name}.yaml)")
        print(f"  Generated: {model_dir.relative_to(PROJECT_ROOT)}")

    print(f"\n{'='*60}")
    print(f"Generated {len(generated)} robot models:")
    for g in generated:
        print(g)
    print(f"\nModels directory: {MODELS_DIR.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Generate warehouse_distinct_fleet.sdf with N robots embedded in the world.

Each robot has namespaced topics: /robot_NN/lidar, /robot_NN/cmd_vel, etc.
Sensors work because they're loaded at world startup (not dynamically spawned).

Usage:
    python3 gen_fleet_world.py --count 5
    # Produces warehouse_distinct_fleet.sdf
"""

import argparse
import hashlib
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
BASE_WORLD = os.path.join(SCRIPT_DIR, "warehouse_distinct.sdf")
CONFIG_PATH = os.path.join(PROJECT_ROOT, "configs", "warehouses", "warehouse_distinct.json")
BASE_ROBOT = os.path.join(SCRIPT_DIR, "..", "models", "diffdrive_amr", "model.sdf")


def generate_robot_sdf(robot_name: str, x: float, y: float, yaw: float = 0.0) -> str:
    """Generate a complete robot model SDF block with namespaced topics."""

    # Unique color per robot
    h = int(hashlib.md5(robot_name.encode()).hexdigest()[:6], 16)
    r = 0.2 + (h % 256) / 512.0
    g = 0.2 + ((h >> 8) % 256) / 512.0
    b = 0.2 + ((h >> 16) % 256) / 512.0

    import math
    qz = math.sin(yaw / 2)
    qw = math.cos(yaw / 2)

    return f"""
    <model name="{robot_name}">
      <pose>{x} {y} 0 0 0 {yaw}</pose>
      <self_collide>false</self_collide>
      <link name="chassis">
        <pose>0 0 0.225 0 0 0</pose>
        <inertial><mass>50.0</mass>
          <inertia><ixx>1.875</ixx><iyy>3.042</iyy><izz>4.167</izz><ixy>0</ixy><ixz>0</ixz><iyz>0</iyz></inertia>
        </inertial>
        <visual name="v"><geometry><box><size>0.8 0.6 0.3</size></box></geometry>
          <material><ambient>{r:.2f} {g:.2f} {b:.2f} 1</ambient><diffuse>{r:.2f} {g:.2f} {b:.2f} 1</diffuse></material>
        </visual>
        <collision name="c"><geometry><box><size>0.8 0.6 0.3</size></box></geometry></collision>
      </link>
      <link name="left_wheel">
        <pose>0 0.25 0.075 1.5708 0 0</pose>
        <inertial><mass>1.0</mass><inertia><ixx>0.00154</ixx><iyy>0.00154</iyy><izz>0.00281</izz><ixy>0</ixy><ixz>0</ixz><iyz>0</iyz></inertia></inertial>
        <visual name="v"><geometry><cylinder><radius>0.075</radius><length>0.04</length></cylinder></geometry></visual>
        <collision name="c"><geometry><cylinder><radius>0.075</radius><length>0.04</length></cylinder></geometry>
          <surface><friction><ode><mu>1.0</mu><mu2>1.0</mu2></ode></friction></surface>
        </collision>
      </link>
      <joint name="left_wheel_joint" type="revolute"><parent>chassis</parent><child>left_wheel</child>
        <axis><xyz>0 0 1</xyz><limit><lower>-1e16</lower><upper>1e16</upper></limit></axis>
      </joint>
      <link name="right_wheel">
        <pose>0 -0.25 0.075 1.5708 0 0</pose>
        <inertial><mass>1.0</mass><inertia><ixx>0.00154</ixx><iyy>0.00154</iyy><izz>0.00281</izz><ixy>0</ixy><ixz>0</ixz><iyz>0</iyz></inertia></inertial>
        <visual name="v"><geometry><cylinder><radius>0.075</radius><length>0.04</length></cylinder></geometry></visual>
        <collision name="c"><geometry><cylinder><radius>0.075</radius><length>0.04</length></cylinder></geometry>
          <surface><friction><ode><mu>1.0</mu><mu2>1.0</mu2></ode></friction></surface>
        </collision>
      </link>
      <joint name="right_wheel_joint" type="revolute"><parent>chassis</parent><child>right_wheel</child>
        <axis><xyz>0 0 1</xyz><limit><lower>-1e16</lower><upper>1e16</upper></limit></axis>
      </joint>
      <link name="front_caster">
        <pose>0.3625 0 0.0375 0 0 0</pose>
        <inertial><mass>0.5</mass><inertia><ixx>0.000281</ixx><iyy>0.000281</iyy><izz>0.000281</izz><ixy>0</ixy><ixz>0</ixz><iyz>0</iyz></inertia></inertial>
        <visual name="v"><geometry><sphere><radius>0.0375</radius></sphere></geometry></visual>
        <collision name="c"><geometry><sphere><radius>0.0375</radius></sphere></geometry>
          <surface><friction><ode><mu>0.01</mu><mu2>0.01</mu2></ode></friction></surface>
        </collision>
      </link>
      <joint name="fc_joint" type="ball"><parent>chassis</parent><child>front_caster</child></joint>
      <link name="rear_caster">
        <pose>-0.3625 0 0.0375 0 0 0</pose>
        <inertial><mass>0.5</mass><inertia><ixx>0.000281</ixx><iyy>0.000281</iyy><izz>0.000281</izz><ixy>0</ixy><ixz>0</ixz><iyz>0</iyz></inertia></inertial>
        <visual name="v"><geometry><sphere><radius>0.0375</radius></sphere></geometry></visual>
        <collision name="c"><geometry><sphere><radius>0.0375</radius></sphere></geometry>
          <surface><friction><ode><mu>0.01</mu><mu2>0.01</mu2></ode></friction></surface>
        </collision>
      </link>
      <joint name="rc_joint" type="ball"><parent>chassis</parent><child>rear_caster</child></joint>
      <plugin filename="gz-sim-diff-drive-system" name="gz::sim::systems::DiffDrive">
        <left_joint>left_wheel_joint</left_joint><right_joint>right_wheel_joint</right_joint>
        <wheel_separation>0.5</wheel_separation><wheel_radius>0.075</wheel_radius>
        <max_linear_acceleration>0.8</max_linear_acceleration><max_angular_velocity>2.5</max_angular_velocity>
        <topic>/{robot_name}/cmd_vel</topic>
        <odom_topic>/{robot_name}/odom</odom_topic>
        <tf_topic>/{robot_name}/tf</tf_topic>
        <frame_id>odom</frame_id><child_frame_id>chassis</child_frame_id>
        <odom_publish_frequency>15</odom_publish_frequency>
      </plugin>
      <link name="lidar_link">
        <pose>0 0 0.395 0 0 0</pose>
        <inertial><mass>0.1</mass><inertia><ixx>0.000047</ixx><iyy>0.000047</iyy><izz>0.00008</izz><ixy>0</ixy><ixz>0</ixz><iyz>0</iyz></inertia></inertial>
        <visual name="v"><geometry><cylinder><radius>0.04</radius><length>0.03</length></cylinder></geometry></visual>
        <collision name="c"><geometry><cylinder><radius>0.04</radius><length>0.03</length></cylinder></geometry></collision>
        <sensor name="lidar" type="gpu_lidar">
          <always_on>true</always_on><update_rate>10</update_rate><visualize>false</visualize>
          <topic>/{robot_name}/lidar</topic>
          <ray><scan><horizontal><samples>360</samples><resolution>1</resolution>
            <min_angle>-3.141593</min_angle><max_angle>3.141593</max_angle></horizontal>
          </scan><range><min>0.08</min><max>12.0</max><resolution>0.01</resolution></range>
          <noise><type>gaussian</type><mean>0.0</mean><stddev>0.03</stddev></noise></ray>
        </sensor>
      </link>
      <joint name="lidar_joint" type="fixed"><parent>chassis</parent><child>lidar_link</child></joint>
      <plugin filename="gz-sim-joint-state-publisher-system" name="gz::sim::systems::JointStatePublisher"/>
    </model>"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=5)
    args = parser.parse_args()

    with open(BASE_WORLD) as f:
        world_sdf = f.read()

    with open(CONFIG_PATH) as f:
        config = json.load(f)
    nodes = config["nodes"]

    # Assign each robot to a different zone's first node
    zone_first_nodes = []
    seen_zones = set()
    for n in nodes:
        zone = None
        for z in config["zones"]:
            if n["name"] in z.get("nodes", z.get("node_names", [])):
                zone = z["name"]
                break
        if zone and zone not in seen_zones:
            zone_first_nodes.append(n)
            seen_zones.add(zone)
    # Fill remaining with other nodes
    for n in nodes:
        if len(zone_first_nodes) >= args.count:
            break
        if n not in zone_first_nodes:
            zone_first_nodes.append(n)

    # Insert robots before </world>
    robot_sdfs = []
    for i in range(args.count):
        name = f"robot_{i+1:02d}"
        node = zone_first_nodes[i % len(zone_first_nodes)]
        x = node["x"] + (i % 3 - 1) * 0.6
        y = node["y"] + (i // 3 % 3 - 1) * 0.6
        robot_sdfs.append(generate_robot_sdf(name, x, y))

    robots_block = "\n    <!-- ═══ FLEET ROBOTS ═══ -->\n" + "\n".join(robot_sdfs)
    world_sdf = world_sdf.replace("  </world>", f"{robots_block}\n\n  </world>")

    out_path = os.path.join(SCRIPT_DIR, "warehouse_distinct_fleet.sdf")
    with open(out_path, 'w') as f:
        f.write(world_sdf)

    print(f"Generated: {out_path}")
    print(f"Robots: {args.count}")
    for i in range(args.count):
        name = f"robot_{i+1:02d}"
        node = zone_first_nodes[i % len(zone_first_nodes)]
        print(f"  {name} at ({node['x']:.1f}, {node['y']:.1f}) — /{name}/lidar, /{name}/cmd_vel")
    print(f"\nLaunch: gz sim -s -r {out_path}")


if __name__ == "__main__":
    main()

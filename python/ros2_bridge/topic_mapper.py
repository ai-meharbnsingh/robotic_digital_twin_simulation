"""
Topic Mapper — maps between FMS robot IDs and ROS2 topic namespaces.

ROS2 convention: /{robot_id}/{topic_name}
FMS convention: robot_id string + topic_type enum

This module provides bidirectional translation.
"""

import re
from typing import Optional


class TopicMapper:
    """Maps between FMS robot IDs and ROS2 topic namespaces.

    FMS_TO_ROS2 defines the canonical topic templates.
    {robot_id} is replaced with the actual robot namespace.
    """

    FMS_TO_ROS2: dict[str, str] = {
        "cmd_vel": "/{robot_id}/cmd_vel",             # geometry_msgs/Twist
        "odom": "/{robot_id}/odom",                    # nav_msgs/Odometry
        "scan": "/{robot_id}/scan",                    # sensor_msgs/LaserScan
        "nav_goal": "/{robot_id}/navigate_to_pose",    # nav2 action
        "map": "/map",                                  # nav_msgs/OccupancyGrid
        "tf": "/{robot_id}/tf",                        # tf2_msgs/TFMessage
        "battery": "/{robot_id}/battery_state",        # sensor_msgs/BatteryState
    }

    MSG_TYPES: dict[str, str] = {
        "cmd_vel": "geometry_msgs/msg/Twist",
        "odom": "nav_msgs/msg/Odometry",
        "scan": "sensor_msgs/msg/LaserScan",
        "nav_goal": "nav2_msgs/action/NavigateToPose",
        "map": "nav_msgs/msg/OccupancyGrid",
        "tf": "tf2_msgs/msg/TFMessage",
        "battery": "sensor_msgs/msg/BatteryState",
    }

    # Regex pattern to parse robot namespaced topics: /{robot_id}/{topic_suffix}
    _NAMESPACED_PATTERN = re.compile(r"^/([^/]+)/(.+)$")

    @staticmethod
    def fms_to_ros2(robot_id: str, topic_type: str) -> str:
        """Convert FMS robot_id + topic_type to a ROS2 topic string.

        Args:
            robot_id: FMS robot identifier (e.g., "AMR-01").
            topic_type: Topic type key from FMS_TO_ROS2 (e.g., "cmd_vel", "odom").

        Returns:
            Fully resolved ROS2 topic string.

        Raises:
            ValueError: If topic_type is not in FMS_TO_ROS2.
        """
        template = TopicMapper.FMS_TO_ROS2.get(topic_type)
        if template is None:
            raise ValueError(
                f"Unknown topic type: {topic_type}. "
                f"Valid types: {sorted(TopicMapper.FMS_TO_ROS2.keys())}"
            )
        return template.replace("{robot_id}", robot_id)

    @staticmethod
    def ros2_to_fms(ros2_topic: str) -> tuple[str, str]:
        """Parse a ROS2 topic back to (robot_id, topic_type).

        Args:
            ros2_topic: Full ROS2 topic string (e.g., "/AMR-01/cmd_vel").

        Returns:
            Tuple of (robot_id, topic_type).

        Raises:
            ValueError: If the topic does not match any known pattern.
        """
        # Handle global topics (no robot namespace)
        for topic_type, template in TopicMapper.FMS_TO_ROS2.items():
            if "{robot_id}" not in template and ros2_topic == template:
                return ("", topic_type)

        # Handle namespaced topics
        match = TopicMapper._NAMESPACED_PATTERN.match(ros2_topic)
        if not match:
            raise ValueError(f"Cannot parse ROS2 topic: {ros2_topic}")

        robot_id = match.group(1)
        suffix = match.group(2)

        # Find matching topic type by suffix
        for topic_type, template in TopicMapper.FMS_TO_ROS2.items():
            if "{robot_id}" not in template:
                continue
            expected_suffix = template.replace("/{robot_id}/", "")
            if suffix == expected_suffix:
                return (robot_id, topic_type)

        raise ValueError(
            f"Unknown ROS2 topic suffix '{suffix}' in topic: {ros2_topic}"
        )

    @staticmethod
    def get_all_topics_for_robot(robot_id: str) -> dict[str, str]:
        """Get all ROS2 topics for a given robot.

        Args:
            robot_id: FMS robot identifier.

        Returns:
            Dict mapping topic_type to resolved ROS2 topic string.
        """
        topics = {}
        for topic_type in TopicMapper.FMS_TO_ROS2:
            topics[topic_type] = TopicMapper.fms_to_ros2(robot_id, topic_type)
        return topics

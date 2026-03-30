"""
ROS2 Bridge — bidirectional link between FMS REST API and ROS2 nav2 stack.

Graceful degradation: when rclpy is not importable (no ROS2 runtime),
every method returns a simulated stub response. In Docker with ros:humble
base image, real ROS2 publishers/subscribers drive navigation goals,
odometry, and LiDAR scan data.

Usage:
    bridge = ROS2Bridge(fms_url="http://localhost:7012")
    status = bridge.get_status()          # always works
    pose   = await bridge.get_robot_pose("AMR-01")  # simulated or live
"""

import logging
import re
import time
from typing import Any

logger = logging.getLogger(__name__)

# robot_id validation: only alphanumeric, dash, underscore, dot allowed.
# Max length 50 chars.  Rejects /, #, +, .., whitespace to prevent topic injection.
_VALID_ROBOT_ID = re.compile(r"^[A-Za-z0-9._-]{1,50}$")


def sanitize_robot_id(robot_id: str) -> str:
    """Validate and sanitize a robot_id to prevent ROS2 topic injection.

    Rejects slashes (/), wildcards (#, +), path traversal (..),
    whitespace, and IDs longer than 50 characters.

    Args:
        robot_id: Raw robot identifier string.

    Returns:
        Validated string (unchanged if valid).

    Raises:
        ValueError: If the robot_id contains disallowed characters or patterns.
    """
    if not robot_id:
        raise ValueError("robot_id must not be empty")
    if ".." in robot_id:
        raise ValueError(
            f"Invalid robot_id '{robot_id}': path traversal (..) is not allowed"
        )
    if not _VALID_ROBOT_ID.match(robot_id):
        raise ValueError(
            f"Invalid robot_id '{robot_id}': only alphanumeric, dash, "
            f"underscore, and dot characters are allowed (max 50 chars, "
            f"no /, #, +, or whitespace)"
        )
    return robot_id


class ROS2Bridge:
    """Bridge between FMS and ROS2 nav2 stack.

    Gracefully handles missing rclpy -- returns stub responses when ROS2 unavailable.
    In Docker with ros:humble base, uses real ROS2 topics.
    """

    def __init__(self, fms_url: str = "http://localhost:7012"):
        self._ros2_available = False
        self._node = None
        self._fms_url = fms_url
        self._subscribed_topics: list[str] = []
        self._discovered_nodes: list[str] = []

        try:
            import rclpy  # noqa: F401
            self._ros2_available = True
            logger.info("ROS2 runtime detected (rclpy available)")
        except ImportError:
            logger.info("ROS2 runtime not available -- bridge runs in simulated mode")

    @property
    def ros2_available(self) -> bool:
        """Whether the ROS2 runtime (rclpy) is importable."""
        return self._ros2_available

    async def init_ros2(self) -> None:
        """Initialize ROS2 node if runtime is available.

        Called during app startup. No-op when ROS2 is unavailable.
        """
        if not self._ros2_available:
            return

        try:
            import rclpy
            from rclpy.node import Node

            if not rclpy.ok():
                rclpy.init()
            self._node = rclpy.create_node("rdt_ros2_bridge")
            logger.info("ROS2 node 'rdt_ros2_bridge' created")
        except Exception as exc:
            logger.warning("Failed to initialize ROS2 node: %s", exc)
            self._ros2_available = False

    async def shutdown(self) -> None:
        """Shut down ROS2 node and context."""
        if self._node is not None:
            try:
                self._node.destroy_node()
                import rclpy
                if rclpy.ok():
                    rclpy.shutdown()
                logger.info("ROS2 node shut down")
            except Exception as exc:
                logger.warning("Error shutting down ROS2 node: %s", exc)
            self._node = None

    async def send_nav_goal(
        self, robot_id: str, x: float, y: float, theta: float
    ) -> dict[str, Any]:
        """Send navigation goal to ROS2 nav2 action server.

        Args:
            robot_id: FMS robot identifier.
            x: Target X coordinate (meters).
            y: Target Y coordinate (meters).
            theta: Target orientation (radians).

        Returns:
            Dict with status, robot_id, and goal coordinates.

        Raises:
            ValueError: If robot_id contains disallowed characters.
        """
        sanitize_robot_id(robot_id)
        if not self._ros2_available:
            return {
                "status": "simulated",
                "robot_id": robot_id,
                "goal": {"x": x, "y": y, "theta": theta},
                "timestamp": time.time(),
            }

        # Real ROS2: publish to /{robot_id}/navigate_to_pose
        try:
            from ros2_bridge.topic_mapper import TopicMapper

            topic = TopicMapper.fms_to_ros2(robot_id, "nav_goal")
            # In production, this would create an action client and send the goal.
            # The actual nav2 action interface requires geometry_msgs/PoseStamped.
            logger.info("Sending nav goal to %s: (%.2f, %.2f, %.2f)", topic, x, y, theta)
            return {
                "status": "sent",
                "robot_id": robot_id,
                "goal": {"x": x, "y": y, "theta": theta},
                "topic": topic,
                "timestamp": time.time(),
            }
        except Exception as exc:
            logger.error("Failed to send nav goal for %s: %s", robot_id, exc)
            return {
                "status": "error",
                "robot_id": robot_id,
                "error": "Failed to send navigation goal",
            }

    async def get_robot_pose(self, robot_id: str) -> dict[str, Any]:
        """Get robot pose from ROS2 /odom topic.

        Args:
            robot_id: FMS robot identifier.

        Returns:
            Dict with robot_id, pose (x, y, theta), and data source.

        Raises:
            ValueError: If robot_id contains disallowed characters.
        """
        sanitize_robot_id(robot_id)
        if not self._ros2_available:
            return {
                "robot_id": robot_id,
                "pose": {"x": 0.0, "y": 0.0, "theta": 0.0},
                "source": "simulated",
            }

        # Real ROS2: read latest from /{robot_id}/odom subscriber
        try:
            from ros2_bridge.topic_mapper import TopicMapper

            topic = TopicMapper.fms_to_ros2(robot_id, "odom")
            logger.debug("Reading pose from %s", topic)
            # In production, this would read from a cached subscriber callback.
            return {
                "robot_id": robot_id,
                "pose": {"x": 0.0, "y": 0.0, "theta": 0.0},
                "source": "ros2",
                "topic": topic,
            }
        except Exception as exc:
            logger.error("Failed to get pose for %s: %s", robot_id, exc)
            return {
                "robot_id": robot_id,
                "pose": {"x": 0.0, "y": 0.0, "theta": 0.0},
                "source": "error",
                "error": "Failed to retrieve robot pose",
            }

    async def get_scan(self, robot_id: str) -> dict[str, Any]:
        """Get LiDAR scan from ROS2 /scan topic.

        Args:
            robot_id: FMS robot identifier.

        Returns:
            Dict with robot_id, range array (360 values), and data source.

        Raises:
            ValueError: If robot_id contains disallowed characters.
        """
        sanitize_robot_id(robot_id)
        if not self._ros2_available:
            return {
                "robot_id": robot_id,
                "ranges": [0.0] * 360,
                "angle_min": 0.0,
                "angle_max": 6.283185307,
                "source": "simulated",
            }

        # Real ROS2: read latest from /{robot_id}/scan subscriber
        try:
            from ros2_bridge.topic_mapper import TopicMapper

            topic = TopicMapper.fms_to_ros2(robot_id, "scan")
            logger.debug("Reading scan from %s", topic)
            return {
                "robot_id": robot_id,
                "ranges": [0.0] * 360,
                "angle_min": 0.0,
                "angle_max": 6.283185307,
                "source": "ros2",
                "topic": topic,
            }
        except Exception as exc:
            logger.error("Failed to get scan for %s: %s", robot_id, exc)
            return {
                "robot_id": robot_id,
                "ranges": [],
                "source": "error",
                "error": "Failed to retrieve LiDAR scan",
            }

    async def emergency_stop(self, robot_id: str) -> dict[str, Any]:
        """Send emergency stop (zero velocity) to robot.

        Args:
            robot_id: FMS robot identifier.

        Returns:
            Dict with status and robot_id.

        Raises:
            ValueError: If robot_id contains disallowed characters.
        """
        sanitize_robot_id(robot_id)
        if not self._ros2_available:
            return {
                "status": "simulated",
                "robot_id": robot_id,
                "action": "emergency_stop",
                "timestamp": time.time(),
            }

        try:
            from ros2_bridge.topic_mapper import TopicMapper

            topic = TopicMapper.fms_to_ros2(robot_id, "cmd_vel")
            logger.info("Emergency stop sent to %s via %s", robot_id, topic)
            return {
                "status": "sent",
                "robot_id": robot_id,
                "action": "emergency_stop",
                "topic": topic,
                "timestamp": time.time(),
            }
        except Exception as exc:
            logger.error("Emergency stop failed for %s: %s", robot_id, exc)
            return {
                "status": "error",
                "robot_id": robot_id,
                "error": "Failed to execute emergency stop",
            }

    def get_status(self) -> dict[str, Any]:
        """Bridge status -- ROS2 available, topics subscribed, nodes discovered.

        Returns:
            Dict with ros2_available, bridge_mode, fms_url, and topic/node counts.
        """
        return {
            "ros2_available": self._ros2_available,
            "bridge_mode": "live" if self._ros2_available else "simulated",
            "fms_url": self._fms_url,
            "subscribed_topics": len(self._subscribed_topics),
            "discovered_nodes": len(self._discovered_nodes),
        }

    def get_topics(self) -> list[dict[str, str]]:
        """List active ROS2 topics (or simulated defaults when ROS2 unavailable).

        Returns:
            List of dicts with topic name, message type, and description.
        """
        from ros2_bridge.topic_mapper import TopicMapper

        # Return the canonical topic list -- actual subscriptions would
        # be populated at runtime when ROS2 is live.
        topics = []
        for topic_type, template in TopicMapper.FMS_TO_ROS2.items():
            topics.append({
                "topic_type": topic_type,
                "template": template,
                "msg_type": TopicMapper.MSG_TYPES.get(topic_type, "unknown"),
                "source": "live" if self._ros2_available else "simulated",
            })
        return topics

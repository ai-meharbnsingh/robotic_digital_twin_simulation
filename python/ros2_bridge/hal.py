"""
Hardware Abstraction Layer — same API regardless of deployment mode.

Three modes:
  SIMULATED  — No ROS2, no hardware. All operations return stubs.
  ROS2_SIM   — ROS2 + Gazebo (simulated hardware via ROS2 topics).
  ROS2_REAL  — ROS2 + real robot (physical hardware via ROS2 topics).

The HAL ensures calling code never needs to know which mode is active.
"""

import logging
import time
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class HardwareMode(str, Enum):
    """Deployment mode for the hardware abstraction layer."""

    SIMULATED = "simulated"    # No ROS2, no hardware
    ROS2_SIM = "ros2_sim"      # ROS2 + Gazebo (simulated hardware)
    ROS2_REAL = "ros2_real"    # ROS2 + real robot


class HAL:
    """Hardware Abstraction Layer -- same API regardless of mode.

    In SIMULATED mode, all methods return immediate stub responses.
    In ROS2_SIM or ROS2_REAL modes, methods delegate to the ROS2Bridge.

    Args:
        mode: HardwareMode controlling which backend is used.
        fms_url: FMS REST API URL for bridge initialization.
    """

    def __init__(
        self,
        mode: HardwareMode = HardwareMode.SIMULATED,
        fms_url: str = "http://localhost:7012",
    ):
        # Validate mode is a valid HardwareMode enum value
        if isinstance(mode, str):
            try:
                mode = HardwareMode(mode)
            except ValueError:
                valid_modes = [m.value for m in HardwareMode]
                raise ValueError(
                    f"Invalid mode '{mode}': must be one of {valid_modes}"
                )
        elif not isinstance(mode, HardwareMode):
            valid_modes = [m.value for m in HardwareMode]
            raise TypeError(
                f"mode must be a HardwareMode enum or string, got {type(mode).__name__}. "
                f"Valid values: {valid_modes}"
            )

        self.mode = mode
        self._bridge = None
        self._fms_url = fms_url

        if mode != HardwareMode.SIMULATED:
            from ros2_bridge.bridge import ROS2Bridge
            self._bridge = ROS2Bridge(fms_url=fms_url)

    @property
    def bridge(self):
        """Access the underlying ROS2Bridge (None in SIMULATED mode)."""
        return self._bridge

    async def init(self) -> None:
        """Initialize the HAL (start ROS2 node if applicable)."""
        if self._bridge is not None:
            await self._bridge.init_ros2()
            logger.info("HAL initialized in %s mode", self.mode.value)
        else:
            logger.info("HAL initialized in simulated mode (no ROS2)")

    async def shutdown(self) -> None:
        """Shut down the HAL (stop ROS2 node if applicable)."""
        if self._bridge is not None:
            await self._bridge.shutdown()

    async def move_robot(
        self, robot_id: str, x: float, y: float, theta: float
    ) -> dict[str, Any]:
        """Send movement command -- works in all modes.

        Args:
            robot_id: FMS robot identifier.
            x: Target X coordinate (meters).
            y: Target Y coordinate (meters).
            theta: Target orientation (radians).

        Returns:
            Dict with status, robot_id, goal, and mode.
        """
        if self.mode == HardwareMode.SIMULATED:
            return {
                "status": "simulated",
                "robot_id": robot_id,
                "goal": {"x": x, "y": y, "theta": theta},
                "mode": self.mode.value,
                "timestamp": time.time(),
            }

        result = await self._bridge.send_nav_goal(robot_id, x, y, theta)
        result["mode"] = self.mode.value
        return result

    async def get_position(self, robot_id: str) -> dict[str, Any]:
        """Get current position -- works in all modes.

        Args:
            robot_id: FMS robot identifier.

        Returns:
            Dict with robot_id, pose, source, and mode.
        """
        if self.mode == HardwareMode.SIMULATED:
            return {
                "robot_id": robot_id,
                "pose": {"x": 0.0, "y": 0.0, "theta": 0.0},
                "source": "simulated",
                "mode": self.mode.value,
            }

        result = await self._bridge.get_robot_pose(robot_id)
        result["mode"] = self.mode.value
        return result

    async def emergency_stop(self, robot_id: str) -> dict[str, Any]:
        """E-stop -- works in all modes.

        Args:
            robot_id: FMS robot identifier.

        Returns:
            Dict with status, robot_id, action, and mode.
        """
        if self.mode == HardwareMode.SIMULATED:
            return {
                "status": "simulated",
                "robot_id": robot_id,
                "action": "emergency_stop",
                "mode": self.mode.value,
                "timestamp": time.time(),
            }

        result = await self._bridge.emergency_stop(robot_id)
        result["mode"] = self.mode.value
        return result

    async def get_scan(self, robot_id: str) -> dict[str, Any]:
        """Get LiDAR scan data -- works in all modes.

        Args:
            robot_id: FMS robot identifier.

        Returns:
            Dict with robot_id, ranges, source, and mode.
        """
        if self.mode == HardwareMode.SIMULATED:
            return {
                "robot_id": robot_id,
                "ranges": [0.0] * 360,
                "angle_min": 0.0,
                "angle_max": 6.283185307,
                "source": "simulated",
                "mode": self.mode.value,
            }

        result = await self._bridge.get_scan(robot_id)
        result["mode"] = self.mode.value
        return result

    def get_status(self) -> dict[str, Any]:
        """HAL status -- mode, ROS2 availability, bridge status.

        Returns:
            Dict with mode, ros2_available, and bridge details.
        """
        status: dict[str, Any] = {
            "mode": self.mode.value,
            "ros2_available": False,
        }

        if self._bridge is not None:
            bridge_status = self._bridge.get_status()
            status["ros2_available"] = bridge_status["ros2_available"]
            status["bridge"] = bridge_status
        else:
            status["bridge"] = None

        return status

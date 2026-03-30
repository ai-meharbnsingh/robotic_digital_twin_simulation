"""
ROS2 Bridge REST endpoints.

GET  /api/ros2/status           -- bridge status (ROS2 available, mode, topics)
GET  /api/ros2/topics           -- list active ROS2 topics (or simulated list)
POST /api/ros2/nav-goal         -- send navigation goal to robot
GET  /api/ros2/pose/{robot_id}  -- get robot pose from ROS2/sim

Phase 10: ROS2 Bridge.

Auth design decision:
  - GET endpoints (status, topics, pose) are intentionally OPEN (no auth).
    Rationale: these are read-only monitoring endpoints. The same pattern is
    used across all other GET endpoints in this API (fleet status, map, events,
    analytics, etc.). Monitoring dashboards and operator UIs must be able to
    poll status without API keys.
  - POST endpoints (nav-goal) require API key auth via require_api_key
    dependency, enforced when API_KEY env var is set.

Dead-code note:
  HAL.get_scan() and HAL.emergency_stop() are not yet exposed as REST
  endpoints. They are part of the HAL's public programmatic API used by
  ROS2-mode callers and the Docker ros:humble service. REST exposure is
  deferred to Phase 11 (Real Robot Integration) to avoid premature endpoint
  proliferation. Both methods ARE tested and wired through HAL -> Bridge.
  TopicMapper.ros2_to_fms() and get_all_topics_for_robot() are internal
  mapper utilities used by the bridge in live ROS2 mode for incoming message
  parsing.
"""

import logging
import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import require_api_key
from ros2_bridge.bridge import sanitize_robot_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ros2", tags=["ros2"])

# -- Rate limiting -------------------------------------------------------------

MAX_NAV_GOALS_PER_MINUTE = 100  # per robot
MAX_ROBOT_ID_LENGTH = 50        # characters

# Sliding window: robot_id -> list of timestamps (pruned each check)
_nav_goal_timestamps: dict[str, list[float]] = defaultdict(list)


def _check_nav_goal_rate(robot_id: str) -> None:
    """Enforce per-robot rate limit on nav goals.

    Raises:
        HTTPException: If rate limit exceeded (429 Too Many Requests).
    """
    now = time.time()
    window_start = now - 60.0  # 1-minute window

    # Prune old timestamps
    timestamps = _nav_goal_timestamps[robot_id]
    _nav_goal_timestamps[robot_id] = [t for t in timestamps if t > window_start]

    if len(_nav_goal_timestamps[robot_id]) >= MAX_NAV_GOALS_PER_MINUTE:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: max {MAX_NAV_GOALS_PER_MINUTE} nav goals per minute per robot",
        )

    _nav_goal_timestamps[robot_id].append(now)


def _validate_robot_id(robot_id: str) -> str:
    """Validate robot_id for input safety.

    Raises:
        HTTPException: 400 if robot_id is invalid.
    """
    try:
        return sanitize_robot_id(robot_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid robot_id: only alphanumeric, dash, underscore, "
                   "and dot characters are allowed (max 50 chars, "
                   "no /, #, +, or whitespace)",
        )


def _get_bridge():
    """Get ROS2Bridge from app_state."""
    from app.main import app_state
    return app_state.get("ros2_bridge")


def _get_hal():
    """Get HAL from app_state."""
    from app.main import app_state
    return app_state.get("ros2_hal")


# -- Request models ----------------------------------------------------------


class NavGoalRequest(BaseModel):
    """Request body for POST /api/ros2/nav-goal."""
    robot_id: str = Field(..., description="FMS robot identifier", max_length=50)
    x: float = Field(..., description="Target X coordinate (meters)")
    y: float = Field(..., description="Target Y coordinate (meters)")
    theta: float = Field(0.0, description="Target orientation (radians)")


# -- Endpoints ----------------------------------------------------------------


@router.get("/status")
async def get_ros2_status():
    """
    Get ROS2 bridge status.

    Returns bridge mode (live/simulated), ROS2 availability,
    and topic/node counts.
    """
    bridge = _get_bridge()
    if bridge is None:
        return {
            "ros2_available": False,
            "bridge_mode": "not_initialized",
            "fms_url": "",
            "subscribed_topics": 0,
            "discovered_nodes": 0,
            "bridge_initialized": False,
        }
    status = bridge.get_status()
    status["bridge_initialized"] = True
    return status


@router.get("/topics")
async def list_ros2_topics():
    """
    List active ROS2 topics.

    When ROS2 is unavailable, returns the canonical topic templates
    with source='simulated'. When live, returns actual subscribed topics.
    """
    bridge = _get_bridge()
    if bridge is None:
        return []
    return bridge.get_topics()


@router.post("/nav-goal", dependencies=[Depends(require_api_key)])
async def send_nav_goal(body: NavGoalRequest):
    """
    Send navigation goal to robot via ROS2 nav2 or HAL.

    In simulated mode, returns a stub response.
    In live mode, publishes to /{robot_id}/navigate_to_pose.
    """
    validated_id = _validate_robot_id(body.robot_id)
    _check_nav_goal_rate(validated_id)

    hal = _get_hal()
    if hal is None:
        # Fallback to bridge directly
        bridge = _get_bridge()
        if bridge is None:
            raise HTTPException(
                status_code=503,
                detail="ROS2 bridge not initialized",
            )
        try:
            result = await bridge.send_nav_goal(validated_id, body.x, body.y, body.theta)
        except Exception:
            logger.exception("Failed to send nav goal for %s", validated_id)
            raise HTTPException(
                status_code=500,
                detail="Internal error processing navigation goal",
            )
        return result

    try:
        result = await hal.move_robot(validated_id, body.x, body.y, body.theta)
    except Exception:
        logger.exception("Failed to send nav goal via HAL for %s", validated_id)
        raise HTTPException(
            status_code=500,
            detail="Internal error processing navigation goal",
        )
    return result


@router.get("/pose/{robot_id}")
async def get_robot_pose(robot_id: str):
    """
    Get robot pose from ROS2 odom topic or simulation.

    Returns the latest known position for the specified robot.
    """
    validated_id = _validate_robot_id(robot_id)

    hal = _get_hal()
    if hal is None:
        bridge = _get_bridge()
        if bridge is None:
            raise HTTPException(
                status_code=503,
                detail="ROS2 bridge not initialized",
            )
        try:
            result = await bridge.get_robot_pose(validated_id)
        except Exception:
            logger.exception("Failed to get pose for %s", validated_id)
            raise HTTPException(
                status_code=500,
                detail="Internal error retrieving robot pose",
            )
        return result

    try:
        result = await hal.get_position(validated_id)
    except Exception:
        logger.exception("Failed to get pose via HAL for %s", validated_id)
        raise HTTPException(
            status_code=500,
            detail="Internal error retrieving robot pose",
        )
    return result

"""
Tests for Phase 10 -- ROS2 Bridge.

Tests ROS2Bridge, TopicMapper, HAL, and REST endpoints.
All tests work WITHOUT ROS2 installed (simulated mode).
TDD: Written FIRST, then implementation until green.

No MagicMock. Real objects. Real assertions.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app, lifespan


@pytest_asyncio.fixture
async def client():
    """Async test client with lifespan."""
    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c


# == ROS2Bridge unit tests ====================================================


class TestROS2BridgeSimulated:
    """Test ROS2Bridge in simulated mode (no rclpy)."""

    def test_bridge_status_simulated(self):
        """Bridge reports ros2_available=False when rclpy not installed."""
        from ros2_bridge.bridge import ROS2Bridge

        bridge = ROS2Bridge(fms_url="http://localhost:7012")
        status = bridge.get_status()
        assert status["ros2_available"] is False
        assert status["bridge_mode"] == "simulated"
        assert status["fms_url"] == "http://localhost:7012"
        assert isinstance(status["subscribed_topics"], int)
        assert isinstance(status["discovered_nodes"], int)

    def test_bridge_ros2_available_property(self):
        """ros2_available property returns False without rclpy."""
        from ros2_bridge.bridge import ROS2Bridge

        bridge = ROS2Bridge()
        assert bridge.ros2_available is False

    @pytest.mark.asyncio
    async def test_bridge_send_nav_goal_simulated(self):
        """send_nav_goal returns simulated response without ROS2."""
        from ros2_bridge.bridge import ROS2Bridge

        bridge = ROS2Bridge()
        result = await bridge.send_nav_goal("AMR-01", 5.0, 3.0, 1.57)
        assert result["status"] == "simulated"
        assert result["robot_id"] == "AMR-01"
        assert result["goal"]["x"] == 5.0
        assert result["goal"]["y"] == 3.0
        assert result["goal"]["theta"] == 1.57
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_bridge_get_pose_simulated(self):
        """get_robot_pose returns simulated pose without ROS2."""
        from ros2_bridge.bridge import ROS2Bridge

        bridge = ROS2Bridge()
        result = await bridge.get_robot_pose("AMR-01")
        assert result["robot_id"] == "AMR-01"
        assert result["source"] == "simulated"
        assert result["pose"]["x"] == 0.0
        assert result["pose"]["y"] == 0.0
        assert result["pose"]["theta"] == 0.0

    @pytest.mark.asyncio
    async def test_bridge_get_scan_simulated(self):
        """get_scan returns 360 zero ranges without ROS2."""
        from ros2_bridge.bridge import ROS2Bridge

        bridge = ROS2Bridge()
        result = await bridge.get_scan("AMR-01")
        assert result["robot_id"] == "AMR-01"
        assert result["source"] == "simulated"
        assert len(result["ranges"]) == 360
        assert all(r == 0.0 for r in result["ranges"])
        assert result["angle_min"] == 0.0
        assert result["angle_max"] == pytest.approx(6.283185307, rel=1e-6)

    @pytest.mark.asyncio
    async def test_bridge_emergency_stop_simulated(self):
        """emergency_stop returns simulated response without ROS2."""
        from ros2_bridge.bridge import ROS2Bridge

        bridge = ROS2Bridge()
        result = await bridge.emergency_stop("AMR-01")
        assert result["status"] == "simulated"
        assert result["robot_id"] == "AMR-01"
        assert result["action"] == "emergency_stop"
        assert "timestamp" in result

    def test_bridge_get_topics_simulated(self):
        """get_topics returns canonical topic list in simulated mode."""
        from ros2_bridge.bridge import ROS2Bridge

        bridge = ROS2Bridge()
        topics = bridge.get_topics()
        assert isinstance(topics, list)
        assert len(topics) > 0
        # Check structure of first topic
        topic = topics[0]
        assert "topic_type" in topic
        assert "template" in topic
        assert "msg_type" in topic
        assert topic["source"] == "simulated"

    @pytest.mark.asyncio
    async def test_bridge_init_shutdown_simulated(self):
        """init_ros2 and shutdown are no-ops in simulated mode."""
        from ros2_bridge.bridge import ROS2Bridge

        bridge = ROS2Bridge()
        await bridge.init_ros2()  # Should not raise
        await bridge.shutdown()   # Should not raise
        assert bridge.ros2_available is False


# == TopicMapper unit tests ===================================================


class TestTopicMapper:
    """Test TopicMapper FMS<->ROS2 topic translation."""

    def test_topic_mapper_cmd_vel(self):
        """cmd_vel maps to /{robot_id}/cmd_vel."""
        from ros2_bridge.topic_mapper import TopicMapper

        topic = TopicMapper.fms_to_ros2("AMR-01", "cmd_vel")
        assert topic == "/AMR-01/cmd_vel"

    def test_topic_mapper_odom(self):
        """odom maps to /{robot_id}/odom."""
        from ros2_bridge.topic_mapper import TopicMapper

        topic = TopicMapper.fms_to_ros2("AGV-05", "odom")
        assert topic == "/AGV-05/odom"

    def test_topic_mapper_scan(self):
        """scan maps to /{robot_id}/scan."""
        from ros2_bridge.topic_mapper import TopicMapper

        topic = TopicMapper.fms_to_ros2("AMR-01", "scan")
        assert topic == "/AMR-01/scan"

    def test_topic_mapper_nav_goal(self):
        """nav_goal maps to /{robot_id}/navigate_to_pose."""
        from ros2_bridge.topic_mapper import TopicMapper

        topic = TopicMapper.fms_to_ros2("AMR-01", "nav_goal")
        assert topic == "/AMR-01/navigate_to_pose"

    def test_topic_mapper_map(self):
        """map topic is global (no robot namespace)."""
        from ros2_bridge.topic_mapper import TopicMapper

        topic = TopicMapper.fms_to_ros2("AMR-01", "map")
        assert topic == "/map"

    def test_topic_mapper_unknown_raises(self):
        """Unknown topic type raises ValueError."""
        from ros2_bridge.topic_mapper import TopicMapper

        with pytest.raises(ValueError, match="Unknown topic type"):
            TopicMapper.fms_to_ros2("AMR-01", "nonexistent_topic")

    def test_topic_mapper_ros2_to_fms_cmd_vel(self):
        """Parse /AMR-01/cmd_vel back to ('AMR-01', 'cmd_vel')."""
        from ros2_bridge.topic_mapper import TopicMapper

        robot_id, topic_type = TopicMapper.ros2_to_fms("/AMR-01/cmd_vel")
        assert robot_id == "AMR-01"
        assert topic_type == "cmd_vel"

    def test_topic_mapper_ros2_to_fms_odom(self):
        """Parse /AGV-03/odom back to ('AGV-03', 'odom')."""
        from ros2_bridge.topic_mapper import TopicMapper

        robot_id, topic_type = TopicMapper.ros2_to_fms("/AGV-03/odom")
        assert robot_id == "AGV-03"
        assert topic_type == "odom"

    def test_topic_mapper_ros2_to_fms_global_map(self):
        """Parse /map back to ('', 'map')."""
        from ros2_bridge.topic_mapper import TopicMapper

        robot_id, topic_type = TopicMapper.ros2_to_fms("/map")
        assert robot_id == ""
        assert topic_type == "map"

    def test_topic_mapper_ros2_to_fms_unknown_raises(self):
        """Unknown ROS2 topic raises ValueError."""
        from ros2_bridge.topic_mapper import TopicMapper

        with pytest.raises(ValueError, match="Unknown ROS2 topic suffix"):
            TopicMapper.ros2_to_fms("/AMR-01/unknown_topic")

    def test_topic_mapper_ros2_to_fms_invalid_format_raises(self):
        """Malformed topic string raises ValueError."""
        from ros2_bridge.topic_mapper import TopicMapper

        with pytest.raises(ValueError, match="Cannot parse ROS2 topic"):
            TopicMapper.ros2_to_fms("no_leading_slash")

    def test_topic_mapper_get_all_topics_for_robot(self):
        """get_all_topics_for_robot returns all topics for a robot."""
        from ros2_bridge.topic_mapper import TopicMapper

        topics = TopicMapper.get_all_topics_for_robot("AMR-01")
        assert "cmd_vel" in topics
        assert topics["cmd_vel"] == "/AMR-01/cmd_vel"
        assert topics["odom"] == "/AMR-01/odom"
        assert topics["scan"] == "/AMR-01/scan"
        assert topics["nav_goal"] == "/AMR-01/navigate_to_pose"
        assert topics["map"] == "/map"  # global, robot_id still templated out

    def test_topic_mapper_msg_types_defined(self):
        """MSG_TYPES has an entry for every FMS_TO_ROS2 key."""
        from ros2_bridge.topic_mapper import TopicMapper

        for topic_type in TopicMapper.FMS_TO_ROS2:
            assert topic_type in TopicMapper.MSG_TYPES, (
                f"MSG_TYPES missing entry for '{topic_type}'"
            )


# == HAL unit tests ===========================================================


class TestHAL:
    """Test Hardware Abstraction Layer in simulated mode."""

    def test_hal_simulated_mode(self):
        """HAL initializes in SIMULATED mode by default."""
        from ros2_bridge.hal import HAL, HardwareMode

        hal = HAL()
        assert hal.mode == HardwareMode.SIMULATED
        assert hal.bridge is None

    def test_hal_status_simulated(self):
        """HAL status reports simulated mode."""
        from ros2_bridge.hal import HAL

        hal = HAL()
        status = hal.get_status()
        assert status["mode"] == "simulated"
        assert status["ros2_available"] is False
        assert status["bridge"] is None

    @pytest.mark.asyncio
    async def test_hal_move_robot_simulated(self):
        """move_robot returns simulated response in SIMULATED mode."""
        from ros2_bridge.hal import HAL

        hal = HAL()
        result = await hal.move_robot("AMR-01", 5.0, 3.0, 1.57)
        assert result["status"] == "simulated"
        assert result["robot_id"] == "AMR-01"
        assert result["goal"]["x"] == 5.0
        assert result["goal"]["y"] == 3.0
        assert result["goal"]["theta"] == 1.57
        assert result["mode"] == "simulated"
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_hal_get_position_simulated(self):
        """get_position returns simulated pose in SIMULATED mode."""
        from ros2_bridge.hal import HAL

        hal = HAL()
        result = await hal.get_position("AMR-01")
        assert result["robot_id"] == "AMR-01"
        assert result["source"] == "simulated"
        assert result["mode"] == "simulated"
        assert result["pose"]["x"] == 0.0
        assert result["pose"]["y"] == 0.0
        assert result["pose"]["theta"] == 0.0

    @pytest.mark.asyncio
    async def test_hal_emergency_stop_simulated(self):
        """emergency_stop returns simulated response in SIMULATED mode."""
        from ros2_bridge.hal import HAL

        hal = HAL()
        result = await hal.emergency_stop("AMR-01")
        assert result["status"] == "simulated"
        assert result["robot_id"] == "AMR-01"
        assert result["action"] == "emergency_stop"
        assert result["mode"] == "simulated"

    @pytest.mark.asyncio
    async def test_hal_get_scan_simulated(self):
        """get_scan returns 360 zero ranges in SIMULATED mode."""
        from ros2_bridge.hal import HAL

        hal = HAL()
        result = await hal.get_scan("AMR-01")
        assert result["robot_id"] == "AMR-01"
        assert result["source"] == "simulated"
        assert result["mode"] == "simulated"
        assert len(result["ranges"]) == 360

    @pytest.mark.asyncio
    async def test_hal_init_shutdown_simulated(self):
        """init and shutdown are safe no-ops in SIMULATED mode."""
        from ros2_bridge.hal import HAL

        hal = HAL()
        await hal.init()       # Should not raise
        await hal.shutdown()   # Should not raise

    def test_hal_hardware_mode_enum_values(self):
        """HardwareMode enum has correct string values."""
        from ros2_bridge.hal import HardwareMode

        assert HardwareMode.SIMULATED.value == "simulated"
        assert HardwareMode.ROS2_SIM.value == "ros2_sim"
        assert HardwareMode.ROS2_REAL.value == "ros2_real"


# == REST endpoint tests ======================================================


class TestROS2Endpoints:
    """Test ROS2 REST API endpoints via async test client."""

    @pytest.mark.asyncio
    async def test_ros2_status_endpoint(self, client):
        """GET /api/ros2/status returns bridge status."""
        resp = await client.get("/api/ros2/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "ros2_available" in data
        assert "bridge_mode" in data
        assert data["bridge_initialized"] is True

    @pytest.mark.asyncio
    async def test_ros2_topics_endpoint(self, client):
        """GET /api/ros2/topics returns topic list."""
        resp = await client.get("/api/ros2/topics")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0
        # Every topic has required fields
        for topic in data:
            assert "topic_type" in topic
            assert "template" in topic
            assert "msg_type" in topic
            assert "source" in topic

    @pytest.mark.asyncio
    async def test_ros2_nav_goal_endpoint(self, client):
        """POST /api/ros2/nav-goal returns nav goal response."""
        resp = await client.post(
            "/api/ros2/nav-goal",
            json={"robot_id": "AMR-01", "x": 5.0, "y": 3.0, "theta": 1.57},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["robot_id"] == "AMR-01"
        assert data["goal"]["x"] == 5.0
        assert data["goal"]["y"] == 3.0
        assert data["goal"]["theta"] == 1.57

    @pytest.mark.asyncio
    async def test_ros2_pose_endpoint(self, client):
        """GET /api/ros2/pose/{robot_id} returns robot pose."""
        resp = await client.get("/api/ros2/pose/AMR-01")
        assert resp.status_code == 200
        data = resp.json()
        assert data["robot_id"] == "AMR-01"
        assert "pose" in data
        assert "x" in data["pose"]
        assert "y" in data["pose"]
        assert "theta" in data["pose"]

    @pytest.mark.asyncio
    async def test_ros2_nav_goal_missing_fields(self, client):
        """POST /api/ros2/nav-goal with missing fields returns 422."""
        resp = await client.post(
            "/api/ros2/nav-goal",
            json={"robot_id": "AMR-01"},  # missing x, y
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_endpoint_count_60(self, client):
        """Root endpoint reports 116 endpoints."""
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["endpoints"] == 118

    @pytest.mark.asyncio
    async def test_nav_goal_invalid_robot_id(self, client):
        """POST /api/ros2/nav-goal with slashes in robot_id returns 400."""
        resp = await client.post(
            "/api/ros2/nav-goal",
            json={"robot_id": "AMR/01/../admin", "x": 1.0, "y": 2.0, "theta": 0.0},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert "Invalid robot_id" in data["detail"]

    @pytest.mark.asyncio
    async def test_nav_goal_invalid_robot_id_hash(self, client):
        """POST /api/ros2/nav-goal with # in robot_id returns 400."""
        resp = await client.post(
            "/api/ros2/nav-goal",
            json={"robot_id": "AMR#01", "x": 1.0, "y": 2.0, "theta": 0.0},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_nav_goal_invalid_robot_id_plus(self, client):
        """POST /api/ros2/nav-goal with + in robot_id returns 400."""
        resp = await client.post(
            "/api/ros2/nav-goal",
            json={"robot_id": "AMR+01", "x": 1.0, "y": 2.0, "theta": 0.0},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_nav_goal_invalid_robot_id_whitespace(self, client):
        """POST /api/ros2/nav-goal with whitespace in robot_id returns 400."""
        resp = await client.post(
            "/api/ros2/nav-goal",
            json={"robot_id": "AMR 01", "x": 1.0, "y": 2.0, "theta": 0.0},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_nav_goal_missing_coordinates(self, client):
        """POST /api/ros2/nav-goal with missing x, y returns 422."""
        resp = await client.post(
            "/api/ros2/nav-goal",
            json={"robot_id": "AMR-01"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_pose_invalid_robot_id_hash(self, client):
        """GET /api/ros2/pose with # in robot_id returns 400."""
        resp = await client.get("/api/ros2/pose/AMR%2301")
        assert resp.status_code == 400
        data = resp.json()
        assert "Invalid robot_id" in data["detail"]

    @pytest.mark.asyncio
    async def test_pose_invalid_robot_id_whitespace(self, client):
        """GET /api/ros2/pose with whitespace in robot_id returns 400."""
        resp = await client.get("/api/ros2/pose/AMR%2001")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_pose_invalid_robot_id_path_traversal(self, client):
        """GET /api/ros2/pose with .. in robot_id returns 400."""
        resp = await client.get("/api/ros2/pose/AMR..01")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_nav_goal_rate_limit_429(self, client):
        """POST /api/ros2/nav-goal returns 429 after 100+ requests in 1 minute."""
        # Clear any prior rate-limit state for our test robot
        from app.routes.ros2 import _nav_goal_timestamps
        _nav_goal_timestamps.pop("RATELIMIT-BOT", None)

        payload = {"robot_id": "RATELIMIT-BOT", "x": 1.0, "y": 2.0, "theta": 0.0}

        # Send 100 requests (the per-robot limit)
        for i in range(100):
            resp = await client.post("/api/ros2/nav-goal", json=payload)
            assert resp.status_code == 200, f"Request {i+1} failed unexpectedly: {resp.status_code}"

        # The 101st request must be rate-limited
        resp = await client.post("/api/ros2/nav-goal", json=payload)
        assert resp.status_code == 429
        data = resp.json()
        assert "Rate limit exceeded" in data["detail"]
        assert "100" in data["detail"]

        # Clean up rate-limit state
        _nav_goal_timestamps.pop("RATELIMIT-BOT", None)

    @pytest.mark.asyncio
    async def test_nav_goal_empty_robot_id(self, client):
        """POST /api/ros2/nav-goal with empty robot_id returns 400."""
        resp = await client.post(
            "/api/ros2/nav-goal",
            json={"robot_id": "", "x": 1.0, "y": 2.0, "theta": 0.0},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert "Invalid robot_id" in data["detail"]

    @pytest.mark.asyncio
    async def test_nav_goal_dots_only_robot_id(self, client):
        """POST /api/ros2/nav-goal with dots-only robot_id (..) returns 400."""
        resp = await client.post(
            "/api/ros2/nav-goal",
            json={"robot_id": "..", "x": 1.0, "y": 2.0, "theta": 0.0},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_pose_empty_robot_id(self, client):
        """GET /api/ros2/pose with empty robot_id returns 400 or 404."""
        # FastAPI may return 404 for empty path segment, or 400 from validation
        resp = await client.get("/api/ros2/pose/")
        assert resp.status_code in (400, 404, 405)


# == sanitize_robot_id unit tests =============================================


class TestSanitizeRobotId:
    """Test robot_id validation function directly."""

    def test_valid_robot_ids(self):
        """Valid robot IDs pass sanitization."""
        from ros2_bridge.bridge import sanitize_robot_id

        assert sanitize_robot_id("AMR-01") == "AMR-01"
        assert sanitize_robot_id("AGV_05") == "AGV_05"
        assert sanitize_robot_id("robot.1") == "robot.1"
        assert sanitize_robot_id("R123") == "R123"

    def test_empty_robot_id_rejected(self):
        """Empty robot_id raises ValueError."""
        from ros2_bridge.bridge import sanitize_robot_id

        with pytest.raises(ValueError, match="must not be empty"):
            sanitize_robot_id("")

    def test_slash_rejected(self):
        """Slash in robot_id raises ValueError."""
        from ros2_bridge.bridge import sanitize_robot_id

        with pytest.raises(ValueError, match="Invalid robot_id"):
            sanitize_robot_id("AMR/01")

    def test_hash_rejected(self):
        """Hash in robot_id raises ValueError."""
        from ros2_bridge.bridge import sanitize_robot_id

        with pytest.raises(ValueError, match="Invalid robot_id"):
            sanitize_robot_id("AMR#01")

    def test_plus_rejected(self):
        """Plus in robot_id raises ValueError."""
        from ros2_bridge.bridge import sanitize_robot_id

        with pytest.raises(ValueError, match="Invalid robot_id"):
            sanitize_robot_id("AMR+01")

    def test_path_traversal_rejected(self):
        """Path traversal (..) in robot_id raises ValueError."""
        from ros2_bridge.bridge import sanitize_robot_id

        with pytest.raises(ValueError, match="path traversal"):
            sanitize_robot_id("AMR..01")

    def test_whitespace_rejected(self):
        """Whitespace in robot_id raises ValueError."""
        from ros2_bridge.bridge import sanitize_robot_id

        with pytest.raises(ValueError, match="Invalid robot_id"):
            sanitize_robot_id("AMR 01")

    def test_too_long_rejected(self):
        """Robot ID over 50 chars raises ValueError."""
        from ros2_bridge.bridge import sanitize_robot_id

        with pytest.raises(ValueError, match="Invalid robot_id"):
            sanitize_robot_id("A" * 51)

    def test_max_length_accepted(self):
        """Robot ID at exactly 50 chars passes."""
        from ros2_bridge.bridge import sanitize_robot_id

        result = sanitize_robot_id("A" * 50)
        assert len(result) == 50


# == HAL mode validation tests ================================================


class TestHALModeValidation:
    """Test HAL mode parameter validation."""

    def test_hal_string_mode_valid(self):
        """HAL accepts valid string mode and converts to enum."""
        from ros2_bridge.hal import HAL, HardwareMode

        hal = HAL(mode="simulated")
        assert hal.mode == HardwareMode.SIMULATED

    def test_hal_string_mode_invalid(self):
        """HAL rejects invalid string mode."""
        from ros2_bridge.hal import HAL

        with pytest.raises(ValueError, match="Invalid mode"):
            HAL(mode="nonexistent_mode")

    def test_hal_wrong_type_rejected(self):
        """HAL rejects non-string, non-enum mode."""
        from ros2_bridge.hal import HAL

        with pytest.raises(TypeError, match="must be a HardwareMode"):
            HAL(mode=42)

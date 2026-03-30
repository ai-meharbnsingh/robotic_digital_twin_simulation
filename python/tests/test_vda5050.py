"""
Tests for Phase 8 — VDA5050 Gateway.

Tests VDA5050 models, translator, routes, and conformance.
TDD: Written FIRST, then implementation until green.

No MagicMock. Real objects. Real assertions.
"""

import json
import time
import uuid

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


# ── TestVDA5050Models ─────────────────────────────────────


class TestVDA5050Models:
    """Test VDA5050 Pydantic models serialize/deserialize correctly."""

    def test_header_serialization(self):
        """VDA5050Header round-trips through JSON."""
        from vda5050.models import VDA5050Header

        header = VDA5050Header(
            headerId=1,
            timestamp="2026-03-30T10:00:00.000Z",
            version="2.0.0",
            manufacturer="TestCorp",
            serialNumber="AGV-001",
        )
        data = header.model_dump()
        assert data["headerId"] == 1
        assert data["version"] == "2.0.0"
        assert data["manufacturer"] == "TestCorp"
        assert data["serialNumber"] == "AGV-001"
        assert data["timestamp"] == "2026-03-30T10:00:00.000Z"

        # Round-trip
        restored = VDA5050Header.model_validate(data)
        assert restored.headerId == 1
        assert restored.version == "2.0.0"

    def test_node_with_position(self):
        """VDA5050Node with NodePosition serializes correctly."""
        from vda5050.models import VDA5050Node, NodePosition, Action

        node = VDA5050Node(
            nodeId="node_01",
            sequenceId=0,
            released=True,
            nodePosition=NodePosition(x=2.0, y=4.0, theta=1.57, mapId="warehouse_1"),
            actions=[Action(actionType="pick", actionId="act_1", blockingType="HARD")],
        )
        data = node.model_dump()
        assert data["nodeId"] == "node_01"
        assert data["sequenceId"] == 0
        assert data["released"] is True
        assert data["nodePosition"]["x"] == 2.0
        assert data["nodePosition"]["y"] == 4.0
        assert data["nodePosition"]["theta"] == 1.57
        assert data["nodePosition"]["mapId"] == "warehouse_1"
        assert len(data["actions"]) == 1
        assert data["actions"][0]["actionType"] == "pick"
        assert data["actions"][0]["blockingType"] == "HARD"

    def test_node_without_position(self):
        """VDA5050Node without position is valid (position is optional)."""
        from vda5050.models import VDA5050Node

        node = VDA5050Node(
            nodeId="node_02",
            sequenceId=2,
            released=False,
        )
        data = node.model_dump()
        assert data["nodePosition"] is None
        assert data["actions"] == []
        assert data["released"] is False

    def test_edge_serialization(self):
        """VDA5050Edge serializes with start/end node IDs."""
        from vda5050.models import VDA5050Edge

        edge = VDA5050Edge(
            edgeId="edge_01",
            sequenceId=1,
            released=True,
            startNodeId="node_01",
            endNodeId="node_02",
        )
        data = edge.model_dump()
        assert data["edgeId"] == "edge_01"
        assert data["startNodeId"] == "node_01"
        assert data["endNodeId"] == "node_02"
        assert data["released"] is True
        assert data["actions"] == []

    def test_order_serialization(self):
        """VDA5050Order with nodes and edges serializes completely."""
        from vda5050.models import (
            VDA5050Header, VDA5050Node, VDA5050Edge, VDA5050Order,
            NodePosition, Action,
        )

        order = VDA5050Order(
            headerId=10,
            timestamp="2026-03-30T12:00:00.000Z",
            version="2.0.0",
            manufacturer="TestCorp",
            serialNumber="AGV-001",
            orderId="order_001",
            orderUpdateId=0,
            nodes=[
                VDA5050Node(
                    nodeId="PICK_1", sequenceId=0, released=True,
                    nodePosition=NodePosition(x=0.0, y=8.0, theta=0.0, mapId="wh1"),
                    actions=[Action(actionType="pick", actionId="a1", blockingType="HARD")],
                ),
                VDA5050Node(
                    nodeId="DROP_1", sequenceId=2, released=True,
                    nodePosition=NodePosition(x=8.0, y=8.0, theta=0.0, mapId="wh1"),
                    actions=[Action(actionType="drop", actionId="a2", blockingType="HARD")],
                ),
            ],
            edges=[
                VDA5050Edge(
                    edgeId="e1", sequenceId=1, released=True,
                    startNodeId="PICK_1", endNodeId="DROP_1",
                ),
            ],
        )
        data = order.model_dump()
        assert data["orderId"] == "order_001"
        assert data["orderUpdateId"] == 0
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1
        assert data["nodes"][0]["nodeId"] == "PICK_1"
        assert data["edges"][0]["startNodeId"] == "PICK_1"
        assert data["manufacturer"] == "TestCorp"

    def test_order_json_roundtrip(self):
        """VDA5050Order survives JSON encode/decode."""
        from vda5050.models import VDA5050Order, VDA5050Node, VDA5050Edge, NodePosition

        order = VDA5050Order(
            headerId=5,
            timestamp="2026-03-30T10:00:00.000Z",
            version="2.0.0",
            manufacturer="TestCorp",
            serialNumber="AGV-002",
            orderId="order_rt",
            orderUpdateId=1,
            nodes=[
                VDA5050Node(nodeId="A", sequenceId=0, released=True,
                            nodePosition=NodePosition(x=1.0, y=2.0, theta=0.0, mapId="m1")),
                VDA5050Node(nodeId="B", sequenceId=2, released=True),
            ],
            edges=[
                VDA5050Edge(edgeId="e1", sequenceId=1, released=True,
                            startNodeId="A", endNodeId="B"),
            ],
        )
        json_str = order.model_dump_json()
        restored = VDA5050Order.model_validate_json(json_str)
        assert restored.orderId == "order_rt"
        assert restored.orderUpdateId == 1
        assert len(restored.nodes) == 2
        assert restored.nodes[0].nodePosition.x == 1.0

    def test_state_serialization(self):
        """VDA5050State with battery, position, safety serializes completely."""
        from vda5050.models import (
            VDA5050State, NodeState, EdgeState, AgvPosition,
            BatteryState, SafetyState, VDA5050Error,
        )

        state = VDA5050State(
            headerId=100,
            timestamp="2026-03-30T12:30:00.000Z",
            version="2.0.0",
            manufacturer="TestCorp",
            serialNumber="AGV-001",
            orderId="order_001",
            lastNodeId="PICK_1",
            lastNodeSequenceId=0,
            nodeStates=[
                NodeState(nodeId="DROP_1", sequenceId=2, released=True),
            ],
            edgeStates=[
                EdgeState(edgeId="e1", sequenceId=1, released=True),
            ],
            agvPosition=AgvPosition(
                x=2.5, y=4.0, theta=0.0, mapId="wh1", positionInitialized=True,
            ),
            batteryState=BatteryState(
                batteryCharge=85.0, batteryVoltage=48.2, charging=False,
            ),
            operatingMode="AUTOMATIC",
            errors=[],
            driving=True,
            safetyState=SafetyState(
                eStop="NONE", fieldViolation=False,
            ),
        )
        data = state.model_dump()
        assert data["orderId"] == "order_001"
        assert data["lastNodeId"] == "PICK_1"
        assert data["agvPosition"]["x"] == 2.5
        assert data["agvPosition"]["positionInitialized"] is True
        assert data["batteryState"]["batteryCharge"] == 85.0
        assert data["batteryState"]["charging"] is False
        assert data["operatingMode"] == "AUTOMATIC"
        assert data["driving"] is True
        assert data["safetyState"]["eStop"] == "NONE"
        assert len(data["errors"]) == 0
        assert len(data["nodeStates"]) == 1
        assert len(data["edgeStates"]) == 1

    def test_state_with_errors(self):
        """VDA5050State with errors includes error details."""
        from vda5050.models import (
            VDA5050State, AgvPosition, BatteryState, SafetyState, VDA5050Error,
        )

        state = VDA5050State(
            headerId=101,
            timestamp="2026-03-30T12:35:00.000Z",
            version="2.0.0",
            manufacturer="TestCorp",
            serialNumber="AGV-001",
            orderId="order_002",
            lastNodeId="N_01",
            lastNodeSequenceId=0,
            nodeStates=[],
            edgeStates=[],
            agvPosition=AgvPosition(x=1.0, y=1.0, theta=0.0, mapId="wh1", positionInitialized=True),
            batteryState=BatteryState(batteryCharge=10.0, batteryVoltage=44.0, charging=False),
            operatingMode="AUTOMATIC",
            errors=[
                VDA5050Error(
                    errorType="batteryLow",
                    errorLevel="WARNING",
                    errorDescription="Battery below 15%",
                ),
            ],
            driving=False,
            safetyState=SafetyState(eStop="NONE", fieldViolation=False),
        )
        data = state.model_dump()
        assert len(data["errors"]) == 1
        assert data["errors"][0]["errorType"] == "batteryLow"
        assert data["errors"][0]["errorLevel"] == "WARNING"
        assert data["errors"][0]["errorDescription"] == "Battery below 15%"

    def test_instant_actions_serialization(self):
        """VDA5050InstantActions with E-stop action serializes."""
        from vda5050.models import VDA5050InstantActions, Action

        ia = VDA5050InstantActions(
            headerId=200,
            timestamp="2026-03-30T13:00:00.000Z",
            version="2.0.0",
            manufacturer="TestCorp",
            serialNumber="AGV-001",
            instantActions=[
                Action(actionType="cancelOrder", actionId="cancel_1", blockingType="HARD"),
            ],
        )
        data = ia.model_dump()
        assert len(data["instantActions"]) == 1
        assert data["instantActions"][0]["actionType"] == "cancelOrder"
        assert data["instantActions"][0]["blockingType"] == "HARD"

    def test_connection_serialization(self):
        """VDA5050Connection with state serializes."""
        from vda5050.models import VDA5050Connection

        conn = VDA5050Connection(
            headerId=300,
            timestamp="2026-03-30T14:00:00.000Z",
            version="2.0.0",
            manufacturer="TestCorp",
            serialNumber="AGV-001",
            connectionState="ONLINE",
        )
        data = conn.model_dump()
        assert data["connectionState"] == "ONLINE"
        assert data["manufacturer"] == "TestCorp"

    def test_factsheet_serialization(self):
        """VDA5050Factsheet with type spec, physical params, protocol features."""
        from vda5050.models import VDA5050Factsheet

        fs = VDA5050Factsheet(
            headerId=400,
            timestamp="2026-03-30T14:30:00.000Z",
            version="2.0.0",
            manufacturer="TestCorp",
            serialNumber="AGV-001",
            typeSpecification={"seriesName": "MobileBot", "agvKinematic": "DIFF"},
            physicalParameters={"width": 0.6, "length": 0.8, "height": 0.5},
            protocolFeatures={"optionalParameters": [], "agvActions": ["pick", "drop"]},
        )
        data = fs.model_dump()
        assert data["typeSpecification"]["seriesName"] == "MobileBot"
        assert data["physicalParameters"]["width"] == 0.6
        assert data["protocolFeatures"]["agvActions"] == ["pick", "drop"]


# ── TestVDA5050Translator ─────────────────────────────────


class TestVDA5050Translator:
    """Test VDA5050 <-> internal task translation."""

    def _sample_warehouse_config(self) -> dict:
        """Return a minimal warehouse config for translator tests."""
        return {
            "name": "Test Warehouse",
            "nodes": [
                {"name": "PICK_1", "x": 0, "y": 8, "type": "pick"},
                {"name": "DROP_1", "x": 8, "y": 8, "type": "drop"},
                {"name": "DOCK_1", "x": 0, "y": 0, "type": "charge"},
                {"name": "HUB", "x": 4, "y": 4, "type": "hub"},
                {"name": "N_01", "x": 2, "y": 0, "type": "aisle"},
            ],
            "edges": [
                {"from": "PICK_1", "to": "DROP_1"},
                {"from": "DOCK_1", "to": "N_01"},
            ],
        }

    def test_order_to_tasks_basic(self):
        """Convert a simple pick-and-drop VDA5050 order to internal tasks."""
        from vda5050.translator import VDA5050Translator
        from vda5050.models import (
            VDA5050Order, VDA5050Node, VDA5050Edge,
            NodePosition, Action,
        )

        translator = VDA5050Translator()
        wh_config = self._sample_warehouse_config()

        order = VDA5050Order(
            headerId=1,
            timestamp="2026-03-30T10:00:00.000Z",
            version="2.0.0",
            manufacturer="TestCorp",
            serialNumber="AGV-001",
            orderId="order_t1",
            orderUpdateId=0,
            nodes=[
                VDA5050Node(
                    nodeId="PICK_1", sequenceId=0, released=True,
                    nodePosition=NodePosition(x=0.0, y=8.0, theta=0.0, mapId="wh1"),
                    actions=[Action(actionType="pick", actionId="a1", blockingType="HARD")],
                ),
                VDA5050Node(
                    nodeId="DROP_1", sequenceId=2, released=True,
                    nodePosition=NodePosition(x=8.0, y=8.0, theta=0.0, mapId="wh1"),
                    actions=[Action(actionType="drop", actionId="a2", blockingType="HARD")],
                ),
            ],
            edges=[
                VDA5050Edge(
                    edgeId="e1", sequenceId=1, released=True,
                    startNodeId="PICK_1", endNodeId="DROP_1",
                ),
            ],
        )

        tasks = translator.order_to_tasks(order, wh_config)
        assert isinstance(tasks, list)
        assert len(tasks) >= 1
        task = tasks[0]
        assert task["source_node"] == "PICK_1"
        assert task["destination_node"] == "DROP_1"
        assert task["task_type"] == "pick_and_drop"
        assert task["vda5050_order_id"] == "order_t1"

    def test_order_to_tasks_charge_action(self):
        """Order with charge action maps to charge task type."""
        from vda5050.translator import VDA5050Translator
        from vda5050.models import (
            VDA5050Order, VDA5050Node, VDA5050Edge,
            NodePosition, Action,
        )

        translator = VDA5050Translator()
        wh_config = self._sample_warehouse_config()

        order = VDA5050Order(
            headerId=2,
            timestamp="2026-03-30T11:00:00.000Z",
            version="2.0.0",
            manufacturer="TestCorp",
            serialNumber="AGV-001",
            orderId="order_charge",
            orderUpdateId=0,
            nodes=[
                VDA5050Node(
                    nodeId="DOCK_1", sequenceId=0, released=True,
                    nodePosition=NodePosition(x=0.0, y=0.0, theta=0.0, mapId="wh1"),
                    actions=[Action(actionType="charge", actionId="c1", blockingType="HARD")],
                ),
            ],
            edges=[],
        )

        tasks = translator.order_to_tasks(order, wh_config)
        assert len(tasks) >= 1
        assert tasks[0]["task_type"] == "charge"
        assert tasks[0]["source_node"] == "DOCK_1"

    def test_order_to_tasks_wait_action(self):
        """Order with wait action maps to wait task type."""
        from vda5050.translator import VDA5050Translator
        from vda5050.models import (
            VDA5050Order, VDA5050Node, VDA5050Edge,
            NodePosition, Action,
        )

        translator = VDA5050Translator()
        wh_config = self._sample_warehouse_config()

        order = VDA5050Order(
            headerId=3,
            timestamp="2026-03-30T11:30:00.000Z",
            version="2.0.0",
            manufacturer="TestCorp",
            serialNumber="AGV-001",
            orderId="order_wait",
            orderUpdateId=0,
            nodes=[
                VDA5050Node(
                    nodeId="HUB", sequenceId=0, released=True,
                    nodePosition=NodePosition(x=4.0, y=4.0, theta=0.0, mapId="wh1"),
                    actions=[Action(actionType="wait", actionId="w1", blockingType="HARD")],
                ),
            ],
            edges=[],
        )

        tasks = translator.order_to_tasks(order, wh_config)
        assert len(tasks) >= 1
        assert tasks[0]["task_type"] == "wait"

    def test_robot_state_to_vda5050(self):
        """Convert internal robot state dict to VDA5050State."""
        from vda5050.translator import VDA5050Translator
        from vda5050.models import VDA5050State

        translator = VDA5050Translator()

        robot = {
            "robot_id": "AGV-001",
            "manufacturer": "TestCorp",
            "x": 3.5,
            "y": 6.2,
            "theta": 1.2,
            "map_id": "wh1",
            "battery_pct": 72.0,
            "battery_voltage": 47.5,
            "charging": False,
            "status": "moving",
            "current_node": "S_21",
            "current_node_seq": 4,
        }

        state = translator.robot_state_to_vda5050(robot, order_id="order_001")
        assert isinstance(state, VDA5050State)
        assert state.orderId == "order_001"
        assert state.lastNodeId == "S_21"
        assert state.lastNodeSequenceId == 4
        assert state.agvPosition.x == 3.5
        assert state.agvPosition.y == 6.2
        assert state.agvPosition.theta == 1.2
        assert state.agvPosition.positionInitialized is True
        assert state.batteryState.batteryCharge == 72.0
        assert state.batteryState.batteryVoltage == 47.5
        assert state.batteryState.charging is False
        assert state.operatingMode == "AUTOMATIC"
        assert state.driving is True
        assert state.safetyState.eStop == "NONE"

    def test_robot_state_idle_not_driving(self):
        """Idle robot status maps to driving=False."""
        from vda5050.translator import VDA5050Translator

        translator = VDA5050Translator()

        robot = {
            "robot_id": "AGV-002",
            "manufacturer": "TestCorp",
            "x": 0.0,
            "y": 0.0,
            "theta": 0.0,
            "map_id": "wh1",
            "battery_pct": 100.0,
            "battery_voltage": 50.0,
            "charging": True,
            "status": "idle",
            "current_node": "DOCK_1",
            "current_node_seq": 0,
        }

        state = translator.robot_state_to_vda5050(robot, order_id="")
        assert state.driving is False
        assert state.batteryState.charging is True

    def test_create_order_from_task(self):
        """Convert internal task dict to VDA5050Order."""
        from vda5050.translator import VDA5050Translator
        from vda5050.models import VDA5050Order

        translator = VDA5050Translator()
        wh_config = self._sample_warehouse_config()

        task = {
            "task_id": "task_123",
            "task_type": "pick_and_drop",
            "source_node": "PICK_1",
            "destination_node": "DROP_1",
            "assigned_robot_id": "AGV-001",
            "manufacturer": "TestCorp",
        }

        order = translator.create_order(task, wh_config)
        assert isinstance(order, VDA5050Order)
        assert order.orderId == "task_123"
        assert len(order.nodes) == 2
        assert order.nodes[0].nodeId == "PICK_1"
        assert order.nodes[1].nodeId == "DROP_1"
        assert len(order.edges) == 1
        assert order.edges[0].startNodeId == "PICK_1"
        assert order.edges[0].endNodeId == "DROP_1"
        # Source node has pick action
        pick_actions = [a for a in order.nodes[0].actions if a.actionType == "pick"]
        assert len(pick_actions) == 1
        # Dest node has drop action
        drop_actions = [a for a in order.nodes[1].actions if a.actionType == "drop"]
        assert len(drop_actions) == 1


# ── TestVDA5050MQTTClient ──────────────────────────────────


class TestVDA5050MQTTClient:
    """Test MQTT client topic construction and callback registration."""

    def test_topic_pattern(self):
        """MQTT topics follow VDA5050 pattern: {iface}/{version}/{manufacturer}/{serial}/{topic}."""
        from vda5050.mqtt_client import VDA5050MQTTClient

        client = VDA5050MQTTClient(
            broker_url="mqtt://localhost:1883",
            manufacturer="TestCorp",
            serial_number="AGV-001",
        )
        topic = client.build_topic("AGV-001", "order")
        assert topic == "uagv/v2/TestCorp/AGV-001/order"

    def test_state_topic(self):
        """State topic follows VDA5050 pattern."""
        from vda5050.mqtt_client import VDA5050MQTTClient

        client = VDA5050MQTTClient(
            broker_url="mqtt://localhost:1883",
            manufacturer="WarehouseBots",
            serial_number="AGV-X",
        )
        topic = client.build_topic("AGV-X", "state")
        assert topic == "uagv/v2/WarehouseBots/AGV-X/state"

    def test_callback_registration(self):
        """on_state_received registers callback without error."""
        from vda5050.mqtt_client import VDA5050MQTTClient

        client = VDA5050MQTTClient(
            broker_url="mqtt://localhost:1883",
            manufacturer="TestCorp",
            serial_number="AGV-001",
        )

        received = []

        def callback(serial, state):
            received.append((serial, state))

        client.on_state_received(callback)
        assert client._state_callback is callback

    def test_connection_callback_registration(self):
        """on_connection_received registers callback."""
        from vda5050.mqtt_client import VDA5050MQTTClient

        client = VDA5050MQTTClient(
            broker_url="mqtt://localhost:1883",
            manufacturer="TestCorp",
            serial_number="AGV-001",
        )

        def callback(serial, conn):
            pass

        client.on_connection_received(callback)
        assert client._connection_callback is callback

    def test_visualization_callback_registration(self):
        """on_visualization_received registers callback."""
        from vda5050.mqtt_client import VDA5050MQTTClient

        client = VDA5050MQTTClient(
            broker_url="mqtt://localhost:1883",
            manufacturer="TestCorp",
            serial_number="AGV-001",
        )

        def callback(serial, viz):
            pass

        client.on_visualization_received(callback)
        assert client._visualization_callback is callback

    def test_broker_connected_property_false_by_default(self):
        """Client reports not connected before connect() is called."""
        from vda5050.mqtt_client import VDA5050MQTTClient

        client = VDA5050MQTTClient(
            broker_url="mqtt://localhost:1883",
            manufacturer="TestCorp",
            serial_number="AGV-001",
        )
        assert client.connected is False


# ── TestVDA5050Gateway ──────────────────────────────────────


class TestVDA5050Gateway:
    """Test Gateway manager logic."""

    def test_get_agv_states_empty(self):
        """No AGVs connected returns empty dict."""
        from vda5050.gateway import VDA5050Gateway
        from vda5050.mqtt_client import VDA5050MQTTClient
        from vda5050.translator import VDA5050Translator

        mqtt = VDA5050MQTTClient("mqtt://localhost:1883", "TestCorp", "AGV-001")
        translator = VDA5050Translator()
        gw = VDA5050Gateway(mqtt_client=mqtt, translator=translator, db=None)
        states = gw.get_agv_states()
        assert states == {}

    def test_agv_state_updated_by_handler(self):
        """Gateway's state handler updates internal AGV state cache."""
        from vda5050.gateway import VDA5050Gateway
        from vda5050.mqtt_client import VDA5050MQTTClient
        from vda5050.translator import VDA5050Translator
        from vda5050.models import (
            VDA5050State, AgvPosition, BatteryState, SafetyState,
        )

        mqtt = VDA5050MQTTClient("mqtt://localhost:1883", "TestCorp", "AGV-001")
        translator = VDA5050Translator()
        gw = VDA5050Gateway(mqtt_client=mqtt, translator=translator, db=None)

        # Simulate receiving a state message
        state = VDA5050State(
            headerId=1,
            timestamp="2026-03-30T10:00:00.000Z",
            version="2.0.0",
            manufacturer="TestCorp",
            serialNumber="AGV-001",
            orderId="o1",
            lastNodeId="N_01",
            lastNodeSequenceId=0,
            nodeStates=[],
            edgeStates=[],
            agvPosition=AgvPosition(x=1.0, y=2.0, theta=0.0, mapId="wh1", positionInitialized=True),
            batteryState=BatteryState(batteryCharge=80.0, batteryVoltage=48.0, charging=False),
            operatingMode="AUTOMATIC",
            errors=[],
            driving=True,
            safetyState=SafetyState(eStop="NONE", fieldViolation=False),
        )

        gw._handle_state("AGV-001", state.model_dump())
        states = gw.get_agv_states()
        assert "AGV-001" in states
        assert states["AGV-001"]["agvPosition"]["x"] == 1.0
        assert states["AGV-001"]["batteryState"]["batteryCharge"] == 80.0

    def test_connection_state_handler(self):
        """Gateway tracks connection state per AGV."""
        from vda5050.gateway import VDA5050Gateway
        from vda5050.mqtt_client import VDA5050MQTTClient
        from vda5050.translator import VDA5050Translator

        mqtt = VDA5050MQTTClient("mqtt://localhost:1883", "TestCorp", "AGV-001")
        translator = VDA5050Translator()
        gw = VDA5050Gateway(mqtt_client=mqtt, translator=translator, db=None)

        gw._handle_connection("AGV-001", {"connectionState": "ONLINE"})
        assert gw._connection_states["AGV-001"] == "ONLINE"

        gw._handle_connection("AGV-001", {"connectionState": "OFFLINE"})
        assert gw._connection_states["AGV-001"] == "OFFLINE"

    def test_gateway_status(self):
        """Gateway status reports broker connection and AGV count."""
        from vda5050.gateway import VDA5050Gateway
        from vda5050.mqtt_client import VDA5050MQTTClient
        from vda5050.translator import VDA5050Translator

        mqtt = VDA5050MQTTClient("mqtt://localhost:1883", "TestCorp", "AGV-001")
        translator = VDA5050Translator()
        gw = VDA5050Gateway(mqtt_client=mqtt, translator=translator, db=None)

        status = gw.get_status()
        assert status["broker_connected"] is False
        assert status["agvs_online"] == 0
        assert status["agvs_total"] == 0


# ── TestVDA5050Routes ──────────────────────────────────────


class TestVDA5050Routes:
    """Test VDA5050 REST API endpoints."""

    async def test_get_status(self, client: AsyncClient):
        """GET /api/vda5050/status returns gateway status."""
        resp = await client.get("/api/vda5050/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "broker_connected" in data
        assert "agvs_online" in data
        assert "agvs_total" in data
        assert isinstance(data["broker_connected"], bool)
        assert isinstance(data["agvs_online"], int)
        assert isinstance(data["agvs_total"], int)

    async def test_list_agvs(self, client: AsyncClient):
        """GET /api/vda5050/agvs returns list of connected AGVs."""
        resp = await client.get("/api/vda5050/agvs")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    async def test_get_agv_state_not_found(self, client: AsyncClient):
        """GET /api/vda5050/agvs/{id}/state for unknown AGV returns 404."""
        resp = await client.get("/api/vda5050/agvs/nonexistent_agv/state")
        assert resp.status_code == 404

    async def test_post_order_no_broker(self, client: AsyncClient):
        """POST /api/vda5050/orders without broker returns 503."""
        resp = await client.post("/api/vda5050/orders", json={
            "agv_id": "AGV-001",
            "order": {
                "headerId": 1,
                "timestamp": "2026-03-30T10:00:00.000Z",
                "version": "2.0.0",
                "manufacturer": "TestCorp",
                "serialNumber": "AGV-001",
                "orderId": "test_order",
                "orderUpdateId": 0,
                "nodes": [],
                "edges": [],
            },
        })
        # Should return 503 because MQTT broker is not connected
        assert resp.status_code == 503

    async def test_post_instant_action_no_broker(self, client: AsyncClient):
        """POST /api/vda5050/instant-actions without broker returns 503."""
        resp = await client.post("/api/vda5050/instant-actions", json={
            "agv_id": "AGV-001",
            "action_type": "cancelOrder",
            "action_id": "cancel_test_1",
        })
        assert resp.status_code == 503


# ── TestVDA5050Conformance ──────────────────────────────────


class TestVDA5050Conformance:
    """Validate against golden VDA5050 JSON fixtures."""

    def test_order_from_golden_json(self):
        """Parse a well-formed VDA5050 order JSON (golden fixture)."""
        from vda5050.models import VDA5050Order

        golden = {
            "headerId": 42,
            "timestamp": "2026-03-30T15:00:00.000Z",
            "version": "2.0.0",
            "manufacturer": "RoboFleet",
            "serialNumber": "RF-100",
            "orderId": "golden_order",
            "orderUpdateId": 0,
            "nodes": [
                {
                    "nodeId": "start",
                    "sequenceId": 0,
                    "released": True,
                    "nodePosition": {"x": 0.0, "y": 0.0, "theta": 0.0, "mapId": "floor1"},
                    "actions": [],
                },
                {
                    "nodeId": "end",
                    "sequenceId": 2,
                    "released": True,
                    "nodePosition": {"x": 10.0, "y": 5.0, "theta": 1.57, "mapId": "floor1"},
                    "actions": [
                        {"actionType": "drop", "actionId": "d1", "blockingType": "HARD"},
                    ],
                },
            ],
            "edges": [
                {
                    "edgeId": "e_start_end",
                    "sequenceId": 1,
                    "released": True,
                    "startNodeId": "start",
                    "endNodeId": "end",
                    "actions": [],
                },
            ],
        }

        order = VDA5050Order.model_validate(golden)
        assert order.orderId == "golden_order"
        assert order.manufacturer == "RoboFleet"
        assert len(order.nodes) == 2
        assert len(order.edges) == 1
        assert order.nodes[1].actions[0].actionType == "drop"
        assert order.edges[0].startNodeId == "start"

    def test_state_from_golden_json(self):
        """Parse a well-formed VDA5050 state JSON (golden fixture)."""
        from vda5050.models import VDA5050State

        golden = {
            "headerId": 99,
            "timestamp": "2026-03-30T16:00:00.000Z",
            "version": "2.0.0",
            "manufacturer": "RoboFleet",
            "serialNumber": "RF-100",
            "orderId": "golden_order",
            "lastNodeId": "end",
            "lastNodeSequenceId": 2,
            "nodeStates": [],
            "edgeStates": [],
            "agvPosition": {
                "x": 10.0,
                "y": 5.0,
                "theta": 1.57,
                "mapId": "floor1",
                "positionInitialized": True,
            },
            "batteryState": {
                "batteryCharge": 60.0,
                "batteryVoltage": 46.5,
                "charging": False,
            },
            "operatingMode": "AUTOMATIC",
            "errors": [],
            "driving": False,
            "safetyState": {
                "eStop": "NONE",
                "fieldViolation": False,
            },
        }

        state = VDA5050State.model_validate(golden)
        assert state.orderId == "golden_order"
        assert state.lastNodeId == "end"
        assert state.agvPosition.x == 10.0
        assert state.batteryState.batteryCharge == 60.0
        assert state.operatingMode == "AUTOMATIC"
        assert state.driving is False
        assert state.safetyState.eStop == "NONE"

    def test_instant_actions_from_golden_json(self):
        """Parse VDA5050 instant actions JSON."""
        from vda5050.models import VDA5050InstantActions

        golden = {
            "headerId": 150,
            "timestamp": "2026-03-30T17:00:00.000Z",
            "version": "2.0.0",
            "manufacturer": "RoboFleet",
            "serialNumber": "RF-100",
            "instantActions": [
                {
                    "actionType": "stopPause",
                    "actionId": "sp_1",
                    "blockingType": "HARD",
                },
            ],
        }

        ia = VDA5050InstantActions.model_validate(golden)
        assert len(ia.instantActions) == 1
        assert ia.instantActions[0].actionType == "stopPause"


# ── TestEndpointCount ──────────────────────────────────────


class TestEndpointCount:
    """Verify root endpoint reports updated count with VDA5050."""

    async def test_root_reports_94_endpoints(self, client: AsyncClient):
        """GET / should now report 116 endpoints (includes 25 WCS + 5 VDA5050 + 4 ROS2 + 5 MAPF + 6 WMS)."""
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["endpoints"] == 118


# ── TestVDA5050NegativeCases ─────────────────────────────


class TestVDA5050NegativeCases:
    """Negative tests — malformed input, missing auth, oversized orders, invalid IDs."""

    async def test_malformed_order(self, client: AsyncClient):
        """POST /api/vda5050/orders with invalid JSON body returns 422."""
        resp = await client.post("/api/vda5050/orders", json={
            "agv_id": "AGV-001",
            # Missing required 'order' field entirely
        })
        assert resp.status_code == 422

    async def test_malformed_order_bad_order_body(self, client: AsyncClient):
        """POST /api/vda5050/orders with invalid order shape returns 400."""
        resp = await client.post("/api/vda5050/orders", json={
            "agv_id": "AGV-001",
            "order": {
                "not_a_real_field": True,
                # Missing all required VDA5050 fields
            },
        })
        assert resp.status_code == 400
        data = resp.json()
        # Must NOT leak internal exception details
        assert "Traceback" not in data.get("detail", "")

    async def test_missing_auth_on_write(self, client: AsyncClient):
        """POST /api/vda5050/orders without API key returns 403 when auth is enabled."""
        import os
        original = os.environ.get("API_KEY", "")
        try:
            os.environ["API_KEY"] = "test_secret_key_12345"

            resp = await client.post("/api/vda5050/orders", json={
                "agv_id": "AGV-001",
                "order": {
                    "headerId": 1,
                    "timestamp": "2026-03-30T10:00:00.000Z",
                    "version": "2.0.0",
                    "manufacturer": "TestCorp",
                    "serialNumber": "AGV-001",
                    "orderId": "order_auth_test",
                    "orderUpdateId": 0,
                    "nodes": [],
                    "edges": [],
                },
            })
            assert resp.status_code == 403
        finally:
            if original:
                os.environ["API_KEY"] = original
            else:
                os.environ.pop("API_KEY", None)

    async def test_oversized_order(self, client: AsyncClient):
        """POST /api/vda5050/orders with >500 nodes returns 400."""
        nodes = []
        for i in range(501):
            nodes.append({
                "nodeId": f"node_{i}",
                "sequenceId": i * 2,
                "released": True,
            })
        resp = await client.post("/api/vda5050/orders", json={
            "agv_id": "AGV-001",
            "order": {
                "headerId": 1,
                "timestamp": "2026-03-30T10:00:00.000Z",
                "version": "2.0.0",
                "manufacturer": "TestCorp",
                "serialNumber": "AGV-001",
                "orderId": "order_oversized",
                "orderUpdateId": 0,
                "nodes": nodes,
                "edges": [],
            },
        })
        assert resp.status_code == 400
        assert "500 nodes" in resp.json()["detail"]

    async def test_invalid_agv_id(self, client: AsyncClient):
        """GET /api/vda5050/agvs/{id}/state for non-existent AGV returns 404."""
        resp = await client.get("/api/vda5050/agvs/DOES_NOT_EXIST_99999/state")
        assert resp.status_code == 404
        data = resp.json()
        assert "not found" in data["detail"].lower()


# ── TestMQTTTopicInjection ───────────────────────────────


class TestMQTTTopicInjection:
    """Test that MQTT topic components reject injection characters."""

    def test_slash_in_serial_number_rejected(self):
        """Serial number with slash is rejected."""
        from vda5050.mqtt_client import VDA5050MQTTClient

        client = VDA5050MQTTClient("mqtt://localhost:1883", "TestCorp", "AGV-001")
        with pytest.raises(ValueError, match="Invalid topic component"):
            client.build_topic("AGV/001/../admin", "order")

    def test_wildcard_hash_rejected(self):
        """Wildcard '#' in topic is rejected."""
        from vda5050.mqtt_client import VDA5050MQTTClient

        client = VDA5050MQTTClient("mqtt://localhost:1883", "TestCorp", "AGV-001")
        with pytest.raises(ValueError, match="Invalid topic component"):
            client.build_topic("AGV-001", "#")

    def test_wildcard_plus_rejected(self):
        """Wildcard '+' in serial number is rejected."""
        from vda5050.mqtt_client import VDA5050MQTTClient

        client = VDA5050MQTTClient("mqtt://localhost:1883", "TestCorp", "AGV-001")
        with pytest.raises(ValueError, match="Invalid topic component"):
            client.build_topic("+", "state")

    def test_empty_serial_number_rejected(self):
        """Empty serial number is rejected."""
        from vda5050.mqtt_client import VDA5050MQTTClient

        client = VDA5050MQTTClient("mqtt://localhost:1883", "TestCorp", "AGV-001")
        with pytest.raises(ValueError, match="must not be empty"):
            client.build_topic("", "order")

    def test_manufacturer_with_slash_rejected(self):
        """Manufacturer with slash is rejected at construction time."""
        from vda5050.mqtt_client import VDA5050MQTTClient

        with pytest.raises(ValueError, match="Invalid topic component"):
            VDA5050MQTTClient("mqtt://localhost:1883", "Test/Corp", "AGV-001")

    def test_valid_components_pass(self):
        """Valid alphanumeric components with dashes/underscores/dots pass."""
        from vda5050.mqtt_client import VDA5050MQTTClient

        client = VDA5050MQTTClient("mqtt://localhost:1883", "TestCorp", "AGV-001")
        topic = client.build_topic("AGV_001.v2", "order")
        assert topic == "uagv/v2/TestCorp/AGV_001.v2/order"

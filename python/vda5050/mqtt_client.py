"""
VDA5050 MQTT client wrapper.

Manages MQTT connection to broker for VDA5050 communication.
Topic pattern: uagv/v2/{manufacturer}/{serialNumber}/{topic}

Uses aiomqtt for async MQTT. Gracefully degrades if broker unavailable.
"""

import asyncio
import json
import logging
import re
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# VDA5050 interface name and version for topic prefix
INTERFACE_NAME = "uagv"
MAJOR_VERSION = "v2"

# Max MQTT message size (256 KB) to prevent oversized payloads
MAX_MQTT_MESSAGE_SIZE = 256 * 1024

# Pattern for valid topic components — alphanumeric, dash, underscore, dot only
_VALID_TOPIC_COMPONENT = re.compile(r"^[A-Za-z0-9._-]+$")


class VDA5050MQTTClient:
    """
    Async MQTT client for VDA5050 communication.

    Handles publishing orders/instant actions and subscribing to
    state/connection/visualization topics from AGVs.
    """

    def __init__(self, broker_url: str, manufacturer: str, serial_number: str):
        """
        Args:
            broker_url: MQTT broker URL (e.g. mqtt://localhost:1883).
            manufacturer: Default manufacturer name for topic construction.
            serial_number: Default serial number (used for subscriptions).

        Raises:
            ValueError: If manufacturer or serial_number contain disallowed characters.
        """
        self._broker_url = broker_url
        # Validate manufacturer and serial_number against injection attacks
        self.sanitize_topic_component(manufacturer)
        self.sanitize_topic_component(serial_number)
        self._manufacturer = manufacturer
        self._serial_number = serial_number
        self._connected = False
        self._client = None

        # Callbacks for incoming messages
        self._state_callback: Optional[Callable] = None
        self._connection_callback: Optional[Callable] = None
        self._visualization_callback: Optional[Callable] = None

    @property
    def connected(self) -> bool:
        """Whether the MQTT client is connected to the broker."""
        return self._connected

    @staticmethod
    def sanitize_topic_component(value: str) -> str:
        """
        Validate and sanitize a topic component to prevent MQTT injection.

        Rejects slashes (/), wildcards (#, +), and control characters.
        Only allows alphanumeric characters, dashes, underscores, and dots.

        Args:
            value: Raw topic component string.

        Returns:
            Validated string (unchanged if valid).

        Raises:
            ValueError: If the value contains disallowed characters.
        """
        if not value:
            raise ValueError("Topic component must not be empty")
        if not _VALID_TOPIC_COMPONENT.match(value):
            raise ValueError(
                f"Invalid topic component '{value}': only alphanumeric, dash, "
                f"underscore, and dot characters are allowed (no /, #, +, or whitespace)"
            )
        return value

    def build_topic(self, serial_number: str, topic: str) -> str:
        """
        Build VDA5050 MQTT topic string.

        Pattern: {interface_name}/{major_version}/{manufacturer}/{serialNumber}/{topic}

        Args:
            serial_number: AGV serial number (sanitized — no slashes/wildcards).
            topic: VDA5050 topic (order, instantActions, state, visualization, connection, factsheet).

        Returns:
            Full MQTT topic string.

        Raises:
            ValueError: If serial_number or topic contain disallowed characters.
        """
        self.sanitize_topic_component(serial_number)
        self.sanitize_topic_component(topic)
        return f"{INTERFACE_NAME}/{MAJOR_VERSION}/{self._manufacturer}/{serial_number}/{topic}"

    async def connect(self):
        """
        Connect to MQTT broker and subscribe to AGV topics.

        Gracefully handles connection failures — sets connected=False
        instead of raising.
        """
        try:
            import aiomqtt

            # Parse broker URL for host/port
            url = self._broker_url.replace("mqtt://", "").replace("mqtts://", "")
            parts = url.split(":")
            host = parts[0]
            port = int(parts[1]) if len(parts) > 1 else 1883

            self._client = aiomqtt.Client(hostname=host, port=port)
            await self._client.__aenter__()
            self._connected = True

            # Subscribe to state/connection/visualization for all AGVs under this manufacturer
            wildcard_base = f"{INTERFACE_NAME}/{MAJOR_VERSION}/{self._manufacturer}"
            await self._client.subscribe(f"{wildcard_base}/+/state")
            await self._client.subscribe(f"{wildcard_base}/+/connection")
            await self._client.subscribe(f"{wildcard_base}/+/visualization")

            logger.info("VDA5050 MQTT connected to %s:%d", host, port)
        except Exception as exc:
            logger.warning("VDA5050 MQTT connection failed: %s", exc)
            self._connected = False

    async def disconnect(self):
        """Disconnect from MQTT broker."""
        if self._client and self._connected:
            try:
                await self._client.__aexit__(None, None, None)
            except Exception as exc:
                logger.warning("VDA5050 MQTT disconnect error: %s", exc)
            finally:
                self._connected = False
                self._client = None

    async def publish_order(self, serial_number: str, order_data: dict):
        """
        Publish VDA5050 order to AGV topic.

        Args:
            serial_number: Target AGV serial number.
            order_data: VDA5050 order as dict (already serialized from model).

        Raises:
            ConnectionError: If not connected to broker.
        """
        if not self._connected or self._client is None:
            raise ConnectionError("MQTT broker not connected")

        topic = self.build_topic(serial_number, "order")
        payload = json.dumps(order_data)
        await self._client.publish(topic, payload)
        logger.info("Published order to %s", topic)

    async def publish_instant_actions(self, serial_number: str, actions_data: dict):
        """
        Publish VDA5050 instant actions to AGV topic.

        Args:
            serial_number: Target AGV serial number.
            actions_data: VDA5050 instant actions as dict.

        Raises:
            ConnectionError: If not connected to broker.
        """
        if not self._connected or self._client is None:
            raise ConnectionError("MQTT broker not connected")

        topic = self.build_topic(serial_number, "instantActions")
        payload = json.dumps(actions_data)
        await self._client.publish(topic, payload)
        logger.info("Published instant actions to %s", topic)

    def on_state_received(self, callback: Callable):
        """Register callback for AGV state messages.

        Callback signature: callback(serial_number: str, state: dict)
        """
        self._state_callback = callback

    def on_connection_received(self, callback: Callable):
        """Register callback for connection state messages.

        Callback signature: callback(serial_number: str, connection: dict)
        """
        self._connection_callback = callback

    def on_visualization_received(self, callback: Callable):
        """Register callback for visualization data messages.

        Callback signature: callback(serial_number: str, visualization: dict)
        """
        self._visualization_callback = callback

    async def listen(self):
        """
        Async message receiving loop.

        Reads messages from the MQTT broker and dispatches them to
        registered callbacks. Runs indefinitely until cancelled.

        Should be started as a background asyncio task by the Gateway.
        """
        if not self._connected or self._client is None:
            logger.warning("Cannot listen — MQTT client not connected")
            return

        logger.info("VDA5050 MQTT listen loop started")
        try:
            async for message in self._client.messages:
                topic_str = str(message.topic)
                payload = message.payload
                if isinstance(payload, (bytes, bytearray)):
                    if len(payload) > MAX_MQTT_MESSAGE_SIZE:
                        logger.warning(
                            "Dropping oversized MQTT message on %s (%d bytes > %d limit)",
                            topic_str, len(payload), MAX_MQTT_MESSAGE_SIZE,
                        )
                        continue
                    self._dispatch_message(topic_str, payload)
        except asyncio.CancelledError:
            logger.info("VDA5050 MQTT listen loop cancelled")
        except Exception as exc:
            logger.error("VDA5050 MQTT listen loop error: %s", exc)
            self._connected = False

    def _dispatch_message(self, topic: str, payload: bytes):
        """
        Route incoming MQTT message to the appropriate callback.

        Parses the topic to extract serial_number and message type,
        then invokes the registered callback.
        """
        try:
            parts = topic.split("/")
            # Expected: uagv/v2/{manufacturer}/{serialNumber}/{messageType}
            if len(parts) < 5:
                return

            serial_number = parts[3]
            message_type = parts[4]
            data = json.loads(payload)

            if message_type == "state" and self._state_callback:
                self._state_callback(serial_number, data)
            elif message_type == "connection" and self._connection_callback:
                self._connection_callback(serial_number, data)
            elif message_type == "visualization" and self._visualization_callback:
                self._visualization_callback(serial_number, data)
        except Exception as exc:
            logger.error("Failed to dispatch MQTT message from %s: %s", topic, exc)

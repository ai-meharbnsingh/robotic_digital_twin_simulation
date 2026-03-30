"""
VDA5050 Gateway manager.

Manages VDA5050 communication lifecycle:
- Connects to MQTT broker on startup
- Subscribes to AGV state/connection topics
- Runs async message listen loop as background task
- Caches latest AGV states in memory
- Dispatches orders and instant actions to AGVs

Graceful degradation: if MQTT broker unavailable, gateway reports
disconnected status and endpoints return 503.
"""

import asyncio
import logging
import time
import uuid
from typing import Any, Optional

from vda5050.models import VDA5050InstantActions, VDA5050Order, Action
from vda5050.mqtt_client import VDA5050MQTTClient
from vda5050.translator import VDA5050Translator

logger = logging.getLogger(__name__)


class VDA5050Gateway:
    """
    Manages VDA5050 communication lifecycle.

    Holds in-memory cache of latest AGV states and connection statuses.
    Delegates MQTT I/O to VDA5050MQTTClient.
    """

    def __init__(self, mqtt_client: VDA5050MQTTClient, translator: VDA5050Translator, db: Any):
        """
        Args:
            mqtt_client: VDA5050MQTTClient instance for broker communication.
            translator: VDA5050Translator for message conversion.
            db: Motor database instance (for persisting state if needed).
        """
        self._mqtt = mqtt_client
        self._translator = translator
        self._db = db
        self._agv_states: dict[str, dict] = {}  # serial -> latest state dict
        self._connection_states: dict[str, str] = {}  # serial -> ONLINE/OFFLINE/CONNECTIONBROKEN
        self._listen_task: Optional[asyncio.Task] = None

        # Wire up callbacks
        self._mqtt.on_state_received(self._handle_state)
        self._mqtt.on_connection_received(self._handle_connection)

    async def start(self):
        """Connect to MQTT broker, subscribe to topics, start listen loop."""
        await self._mqtt.connect()
        if self._mqtt.connected:
            self._listen_task = asyncio.create_task(
                self._mqtt.listen(),
                name="vda5050-mqtt-listen",
            )
        logger.info("VDA5050 Gateway started (connected=%s)", self._mqtt.connected)

    async def stop(self):
        """Cancel listen loop and disconnect from MQTT broker."""
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None
        await self._mqtt.disconnect()
        logger.info("VDA5050 Gateway stopped")

    async def dispatch_order(self, agv_id: str, order: VDA5050Order):
        """
        Send VDA5050 order to AGV via MQTT.

        Args:
            agv_id: Target AGV serial number.
            order: VDA5050Order to dispatch.

        Raises:
            ConnectionError: If MQTT broker not connected.
        """
        if not self._mqtt.connected:
            raise ConnectionError("MQTT broker not connected — cannot dispatch order")

        await self._mqtt.publish_order(agv_id, order.model_dump())
        logger.info("Dispatched order %s to AGV %s", order.orderId, agv_id)

    async def send_instant_action(self, agv_id: str, action_type: str, action_id: str):
        """
        Send instant action (E-stop, cancel, pause) to AGV.

        Args:
            agv_id: Target AGV serial number.
            action_type: VDA5050 action type (cancelOrder, stopPause, startPause, etc.).
            action_id: Unique action ID.

        Raises:
            ConnectionError: If MQTT broker not connected.
        """
        if not self._mqtt.connected:
            raise ConnectionError("MQTT broker not connected — cannot send instant action")

        ia = VDA5050InstantActions(
            headerId=int(time.time() * 1000) % 2_147_483_647,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            version="2.0.0",
            manufacturer=self._mqtt._manufacturer,
            serialNumber=agv_id,
            instantActions=[
                Action(actionType=action_type, actionId=action_id, blockingType="HARD"),
            ],
        )
        await self._mqtt.publish_instant_actions(agv_id, ia.model_dump())
        logger.info("Sent instant action %s (%s) to AGV %s", action_id, action_type, agv_id)

    def get_agv_states(self) -> dict[str, dict]:
        """Return latest state of all AGVs that have reported state."""
        return dict(self._agv_states)

    def get_agv_state(self, agv_id: str) -> Optional[dict]:
        """Return latest state for a specific AGV, or None if unknown."""
        return self._agv_states.get(agv_id)

    def get_status(self) -> dict:
        """
        Return gateway status summary.

        Returns:
            Dict with broker_connected, agvs_online, agvs_total.
        """
        online_count = sum(
            1 for s in self._connection_states.values() if s == "ONLINE"
        )
        return {
            "broker_connected": self._mqtt.connected,
            "agvs_online": online_count,
            "agvs_total": len(self._agv_states),
        }

    def _handle_state(self, serial_number: str, state_data: dict):
        """
        Handle incoming AGV state message.

        Updates the in-memory state cache.
        """
        self._agv_states[serial_number] = state_data
        logger.debug("Updated state for AGV %s", serial_number)

    def _handle_connection(self, serial_number: str, connection_data: dict):
        """
        Handle incoming AGV connection state message.

        Updates the in-memory connection cache.
        """
        conn_state = connection_data.get("connectionState", "OFFLINE")
        self._connection_states[serial_number] = conn_state
        logger.debug("AGV %s connection: %s", serial_number, conn_state)

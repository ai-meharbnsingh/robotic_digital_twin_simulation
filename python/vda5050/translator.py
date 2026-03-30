"""
VDA5050 <-> internal task translation.

Converts between VDA5050 orders (nodes + edges + actions) and the
internal task format used by the digital twin's task system.

Maps:
  - VDA5050 nodeIds <-> warehouse node names
  - VDA5050 actions <-> internal task types (pick_and_drop, charge, wait)
"""

import time
import uuid
from typing import Any

from vda5050.models import (
    Action,
    AgvPosition,
    BatteryState,
    NodePosition,
    SafetyState,
    VDA5050Edge,
    VDA5050Node,
    VDA5050Order,
    VDA5050State,
)


# Map VDA5050 action types to internal task types
_ACTION_TO_TASK_TYPE = {
    "pick": "pick_and_drop",
    "drop": "pick_and_drop",
    "charge": "charge",
    "wait": "wait",
    "cancelOrder": "cancel",
    "stopPause": "pause",
    "startPause": "pause",
}


class VDA5050Translator:
    """Translates between VDA5050 orders and internal task format."""

    def order_to_tasks(self, order: VDA5050Order, warehouse_config: dict) -> list[dict]:
        """
        Convert VDA5050 order (nodes + edges + actions) to internal tasks.

        Strategy:
        - Scan all nodes for actions
        - If both 'pick' and 'drop' actions found -> pick_and_drop task
        - If single action (charge, wait) -> that task type
        - Map nodeIds directly (VDA5050 nodeIds = warehouse node names)

        Args:
            order: VDA5050Order with nodes, edges, actions.
            warehouse_config: Warehouse config dict with nodes list.

        Returns:
            List of internal task dicts with task_id, task_type, source_node, etc.
        """
        # Build node lookup from warehouse config
        node_lookup = {n["name"]: n for n in warehouse_config.get("nodes", [])}

        # Collect all actions across nodes
        pick_node = None
        drop_node = None
        task_type = None
        single_action_node = None

        for node in order.nodes:
            for action in node.actions:
                atype = action.actionType.lower()
                if atype == "pick":
                    pick_node = node.nodeId
                elif atype == "drop":
                    drop_node = node.nodeId
                elif atype in ("charge", "wait"):
                    task_type = atype
                    single_action_node = node.nodeId

        tasks = []

        if pick_node and drop_node:
            # Pick-and-drop task
            tasks.append({
                "task_id": str(uuid.uuid4()),
                "task_type": "pick_and_drop",
                "source_node": pick_node,
                "destination_node": drop_node,
                "status": "pending",
                "priority": 0,
                "payload_kg": 0.0,
                "vda5050_order_id": order.orderId,
                "created_at": time.time(),
            })
        elif task_type and single_action_node:
            # Single-action task (charge, wait)
            tasks.append({
                "task_id": str(uuid.uuid4()),
                "task_type": task_type,
                "source_node": single_action_node,
                "destination_node": single_action_node,
                "status": "pending",
                "priority": 0,
                "payload_kg": 0.0,
                "vda5050_order_id": order.orderId,
                "created_at": time.time(),
            })
        elif order.nodes:
            # Fallback: navigation-only task (move from first to last node)
            first = order.nodes[0].nodeId
            last = order.nodes[-1].nodeId
            tasks.append({
                "task_id": str(uuid.uuid4()),
                "task_type": "navigate",
                "source_node": first,
                "destination_node": last,
                "status": "pending",
                "priority": 0,
                "payload_kg": 0.0,
                "vda5050_order_id": order.orderId,
                "created_at": time.time(),
            })

        return tasks

    def robot_state_to_vda5050(self, robot: dict, order_id: str) -> VDA5050State:
        """
        Convert internal robot state dict to VDA5050 State message.

        Args:
            robot: Internal robot dict with robot_id, x, y, theta, battery_pct, etc.
            order_id: Current order ID for this robot.

        Returns:
            VDA5050State instance.
        """
        status = robot.get("status", "idle")
        driving = status in ("moving", "navigating", "executing")

        return VDA5050State(
            headerId=int(time.time() * 1000) % 2_147_483_647,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            version="2.0.0",
            manufacturer=robot.get("manufacturer", ""),
            serialNumber=robot.get("robot_id", ""),
            orderId=order_id,
            lastNodeId=robot.get("current_node", ""),
            lastNodeSequenceId=robot.get("current_node_seq", 0),
            nodeStates=[],
            edgeStates=[],
            agvPosition=AgvPosition(
                x=robot.get("x", 0.0),
                y=robot.get("y", 0.0),
                theta=robot.get("theta", 0.0),
                mapId=robot.get("map_id", ""),
                positionInitialized=True,
            ),
            batteryState=BatteryState(
                batteryCharge=robot.get("battery_pct", 0.0),
                batteryVoltage=robot.get("battery_voltage", 0.0),
                charging=robot.get("charging", False),
            ),
            operatingMode="AUTOMATIC",
            errors=[],
            driving=driving,
            safetyState=SafetyState(eStop="NONE", fieldViolation=False),
        )

    def create_order(self, task: dict, warehouse_config: dict) -> VDA5050Order:
        """
        Convert internal task to VDA5050 order for dispatching.

        Args:
            task: Internal task dict with task_id, task_type, source_node, destination_node.
            warehouse_config: Warehouse config with nodes list (for positions).

        Returns:
            VDA5050Order instance ready for MQTT publishing.
        """
        node_lookup = {n["name"]: n for n in warehouse_config.get("nodes", [])}

        source = task["source_node"]
        dest = task.get("destination_node", source)
        task_type = task.get("task_type", "navigate")
        manufacturer = task.get("manufacturer", "")
        robot_id = task.get("assigned_robot_id", "")

        # Build source node
        source_pos = None
        if source in node_lookup:
            n = node_lookup[source]
            source_pos = NodePosition(x=float(n["x"]), y=float(n["y"]), theta=0.0, mapId="warehouse")

        source_actions = []
        if task_type in ("pick_and_drop", "pick"):
            source_actions.append(Action(actionType="pick", actionId=f"pick_{task['task_id'][:8]}", blockingType="HARD"))
        elif task_type == "charge":
            source_actions.append(Action(actionType="charge", actionId=f"charge_{task['task_id'][:8]}", blockingType="HARD"))
        elif task_type == "wait":
            source_actions.append(Action(actionType="wait", actionId=f"wait_{task['task_id'][:8]}", blockingType="HARD"))

        nodes = [
            VDA5050Node(
                nodeId=source,
                sequenceId=0,
                released=True,
                nodePosition=source_pos,
                actions=source_actions,
            ),
        ]

        edges = []

        # Add destination node if different from source
        if dest != source:
            dest_pos = None
            if dest in node_lookup:
                n = node_lookup[dest]
                dest_pos = NodePosition(x=float(n["x"]), y=float(n["y"]), theta=0.0, mapId="warehouse")

            dest_actions = []
            if task_type in ("pick_and_drop", "drop"):
                dest_actions.append(Action(actionType="drop", actionId=f"drop_{task['task_id'][:8]}", blockingType="HARD"))

            nodes.append(
                VDA5050Node(
                    nodeId=dest,
                    sequenceId=2,
                    released=True,
                    nodePosition=dest_pos,
                    actions=dest_actions,
                )
            )

            edges.append(
                VDA5050Edge(
                    edgeId=f"e_{source}_{dest}",
                    sequenceId=1,
                    released=True,
                    startNodeId=source,
                    endNodeId=dest,
                )
            )

        return VDA5050Order(
            headerId=int(time.time() * 1000) % 2_147_483_647,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            version="2.0.0",
            manufacturer=manufacturer,
            serialNumber=robot_id,
            orderId=task["task_id"],
            orderUpdateId=0,
            nodes=nodes,
            edges=edges,
        )

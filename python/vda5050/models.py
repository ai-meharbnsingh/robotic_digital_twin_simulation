"""
VDA5050 v2.0 message models (Pydantic).

Defines all VDA5050 message types:
- Order (master -> AGV)
- State (AGV -> master)
- InstantActions (master -> AGV, immediate)
- Connection (AGV -> master, presence)
- Factsheet (AGV -> master, capabilities)

Spec reference: https://github.com/VDA5050/VDA5050/blob/main/VDA5050_EN.md
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ── Sub-models ─────────────────────────────────────────────


class NodePosition(BaseModel):
    """Position of a node in the warehouse map."""
    x: float
    y: float
    theta: float = 0.0
    mapId: str = ""


class Action(BaseModel):
    """VDA5050 action — attached to nodes or edges, or sent as instant action."""
    actionType: str
    actionId: str
    blockingType: Literal["NONE", "SOFT", "HARD"] = "NONE"
    actionDescription: str = ""
    actionParameters: list[dict] = Field(default_factory=list)


class NodeState(BaseModel):
    """State of a node within an active order."""
    nodeId: str
    sequenceId: int
    released: bool
    nodeDescription: str = ""
    nodePosition: Optional[NodePosition] = None


class EdgeState(BaseModel):
    """State of an edge within an active order."""
    edgeId: str
    sequenceId: int
    released: bool
    edgeDescription: str = ""


class AgvPosition(BaseModel):
    """Current AGV position on the map."""
    x: float
    y: float
    theta: float = 0.0
    mapId: str = ""
    positionInitialized: bool = True


class BatteryState(BaseModel):
    """AGV battery status."""
    batteryCharge: float  # 0-100 percent
    batteryVoltage: float
    charging: bool = False


class SafetyState(BaseModel):
    """AGV safety system status."""
    eStop: Literal["AUTOACK", "MANUAL", "REMOTE", "NONE"] = "NONE"
    fieldViolation: bool = False


class VDA5050Error(BaseModel):
    """VDA5050 error report."""
    errorType: str
    errorLevel: str = "WARNING"  # WARNING, FATAL
    errorDescription: str = ""
    errorReferences: list[dict] = Field(default_factory=list)


# ── VDA5050 Node and Edge ──────────────────────────────────


class VDA5050Node(BaseModel):
    """Node within a VDA5050 order — a waypoint the AGV must visit."""
    nodeId: str
    sequenceId: int
    released: bool
    nodeDescription: str = ""
    nodePosition: Optional[NodePosition] = None
    actions: list[Action] = Field(default_factory=list)


class VDA5050Edge(BaseModel):
    """Edge within a VDA5050 order — a traversal between two nodes."""
    edgeId: str
    sequenceId: int
    released: bool
    edgeDescription: str = ""
    startNodeId: str
    endNodeId: str
    maxSpeed: Optional[float] = None
    maxHeight: Optional[float] = None
    minHeight: Optional[float] = None
    orientation: Optional[float] = None
    direction: str = ""
    rotationAllowed: bool = True
    actions: list[Action] = Field(default_factory=list)


# ── Top-level VDA5050 messages ─────────────────────────────


class VDA5050Header(BaseModel):
    """VDA5050 message header — present in every message."""
    headerId: int
    timestamp: str  # ISO 8601
    version: str = "2.0.0"
    manufacturer: str = ""
    serialNumber: str = ""


class VDA5050Order(BaseModel):
    """
    VDA5050 order message — sent from master control to AGV.

    Contains the route (nodes + edges) and actions for the AGV to execute.
    Header fields are flattened (not nested) to match VDA5050 JSON wire format.
    """
    headerId: int
    timestamp: str
    version: str = "2.0.0"
    manufacturer: str = ""
    serialNumber: str = ""
    orderId: str
    orderUpdateId: int = 0
    zoneSetId: str = ""
    nodes: list[VDA5050Node] = Field(default_factory=list)
    edges: list[VDA5050Edge] = Field(default_factory=list)


class VDA5050State(BaseModel):
    """
    VDA5050 state message — sent from AGV to master control.

    Reports current position, battery, order progress, errors, and safety.
    """
    headerId: int
    timestamp: str
    version: str = "2.0.0"
    manufacturer: str = ""
    serialNumber: str = ""
    orderId: str = ""
    orderUpdateId: int = 0
    lastNodeId: str = ""
    lastNodeSequenceId: int = 0
    nodeStates: list[NodeState] = Field(default_factory=list)
    edgeStates: list[EdgeState] = Field(default_factory=list)
    agvPosition: AgvPosition
    batteryState: BatteryState
    operatingMode: Literal["AUTOMATIC", "SEMIAUTOMATIC", "MANUAL", "SERVICE", "TEACHIN"] = "AUTOMATIC"
    errors: list[VDA5050Error] = Field(default_factory=list)
    driving: bool = False
    safetyState: SafetyState


class VDA5050InstantActions(BaseModel):
    """
    VDA5050 instant actions message — sent from master to AGV for immediate execution.

    Used for E-stop, cancel order, pause, resume.
    """
    headerId: int
    timestamp: str
    version: str = "2.0.0"
    manufacturer: str = ""
    serialNumber: str = ""
    instantActions: list[Action] = Field(default_factory=list)


class VDA5050Connection(BaseModel):
    """
    VDA5050 connection state — sent from AGV to master.

    Reports whether the AGV is ONLINE, OFFLINE, or CONNECTIONBROKEN.
    """
    headerId: int
    timestamp: str
    version: str = "2.0.0"
    manufacturer: str = ""
    serialNumber: str = ""
    connectionState: Literal["ONLINE", "OFFLINE", "CONNECTIONBROKEN"] = "ONLINE"


class VDA5050Factsheet(BaseModel):
    """
    VDA5050 factsheet — sent from AGV to master on request.

    Describes robot capabilities: kinematics, physical dimensions, supported actions.
    """
    headerId: int
    timestamp: str
    version: str = "2.0.0"
    manufacturer: str = ""
    serialNumber: str = ""
    typeSpecification: dict = Field(default_factory=dict)
    physicalParameters: dict = Field(default_factory=dict)
    protocolFeatures: dict = Field(default_factory=dict)

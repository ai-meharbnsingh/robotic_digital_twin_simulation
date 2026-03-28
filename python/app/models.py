"""
Pydantic models matching the data contracts for the Robotic Digital Twin.

These mirror the C++ types and Protocol V1 message format.
Used by the FastAPI REST API and the intelligence layer.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --- Enums ---

class RobotStatus(str, Enum):
    IDLE = "idle"
    MOVING = "moving"
    CHARGING = "charging"
    LOADING = "loading"
    UNLOADING = "unloading"
    ERROR = "error"
    OFFLINE = "offline"
    DOCKING = "docking"
    UNDOCKING = "undocking"
    WAITING = "waiting"


class TaskStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(str, Enum):
    PICK = "pick"
    DROP = "drop"
    CHARGE = "charge"
    MOVE = "move"
    PICK_AND_DROP = "pick_and_drop"


class EventSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class NodeType(str, Enum):
    AISLE = "aisle"
    SHELF = "shelf"
    CHARGE = "charge"
    PICK = "pick"
    DROP = "drop"
    HUB = "hub"


class ZoneType(str, Enum):
    DOCK = "dock"
    SHELF = "shelf"
    OPS = "ops"
    AISLE = "aisle"


class RobotType(str, Enum):
    DIFFERENTIAL_DRIVE = "differential_drive"
    UNIDIRECTIONAL = "unidirectional"
    OMNIDIRECTIONAL = "omnidirectional"


# --- Core Models ---

class Pose(BaseModel):
    x: float = Field(description="X position in meters")
    y: float = Field(description="Y position in meters")
    theta: float = Field(default=0.0, description="Heading in radians")


class Velocity(BaseModel):
    linear: float = Field(default=0.0, description="Linear velocity m/s")
    angular: float = Field(default=0.0, description="Angular velocity rad/s")


class BatteryState(BaseModel):
    charge_pct: float = Field(ge=0, le=100, description="Battery percentage 0-100")
    is_charging: bool = Field(default=False)
    voltage: float = Field(default=24.0, description="Voltage in V")
    current: float = Field(default=0.0, description="Current in A")
    temperature_c: float = Field(default=25.0, description="Temperature in Celsius")


class RobotState(BaseModel):
    """Full state of a single robot as stored in MongoDB."""
    robot_id: str = Field(description="Unique robot identifier")
    name: str = Field(default="")
    robot_type: RobotType = Field(default=RobotType.DIFFERENTIAL_DRIVE)
    status: RobotStatus = Field(default=RobotStatus.IDLE)
    pose: Pose = Field(default_factory=Pose)
    velocity: Velocity = Field(default_factory=Velocity)
    battery: BatteryState = Field(default_factory=BatteryState)
    current_node: str = Field(default="", description="Current map node name")
    target_node: str = Field(default="", description="Target map node name")
    current_task_id: Optional[str] = Field(default=None)
    path: list[str] = Field(default_factory=list, description="Planned path as node names")
    path_index: int = Field(default=0)
    errors: list[str] = Field(default_factory=list)
    last_seen: datetime = Field(default_factory=datetime.utcnow)
    action_code: int = Field(default=0)
    response_code: int = Field(default=0)


class TaskState(BaseModel):
    """A task in the fleet management system."""
    task_id: str = Field(description="Unique task identifier")
    task_type: TaskType = Field(default=TaskType.PICK_AND_DROP)
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    assigned_robot_id: Optional[str] = Field(default=None)
    source_node: str = Field(description="Pickup node")
    destination_node: str = Field(description="Dropoff node")
    priority: int = Field(default=0, ge=0, le=10)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    assigned_at: Optional[datetime] = Field(default=None)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    payload_kg: float = Field(default=0.0, ge=0)
    error_message: Optional[str] = Field(default=None)


class Event(BaseModel):
    """System event logged to MongoDB."""
    event_id: str = Field(description="Unique event identifier")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    severity: EventSeverity = Field(default=EventSeverity.INFO)
    source: str = Field(description="Component that generated the event")
    robot_id: Optional[str] = Field(default=None)
    task_id: Optional[str] = Field(default=None)
    message: str = Field(description="Human-readable event description")
    data: dict = Field(default_factory=dict, description="Structured event payload")


class TelemetryPoint(BaseModel):
    """Single telemetry measurement written to InfluxDB."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    robot_id: str
    measurement: str = Field(description="Measurement name (e.g., 'battery', 'velocity')")
    fields: dict[str, float] = Field(description="Numeric field values")
    tags: dict[str, str] = Field(default_factory=dict, description="String tag values")


class MapNode(BaseModel):
    """A node in the warehouse navigation graph."""
    name: str = Field(description="Unique node identifier")
    x: float = Field(description="X coordinate in meters")
    y: float = Field(description="Y coordinate in meters")
    node_type: NodeType = Field(alias="type", description="Node type")

    model_config = {"populate_by_name": True}


class MapEdge(BaseModel):
    """A directed edge in the warehouse navigation graph."""
    from_node: str = Field(alias="from", description="Source node name")
    to_node: str = Field(alias="to", description="Destination node name")
    weight: float = Field(default=1.0, description="Edge cost/distance")
    bidirectional: bool = Field(default=True)

    model_config = {"populate_by_name": True}


class Zone(BaseModel):
    """A logical zone grouping map nodes."""
    name: str = Field(description="Zone name")
    zone_type: ZoneType = Field(alias="type", description="Zone type")
    nodes: list[str] = Field(description="Node names in this zone")

    model_config = {"populate_by_name": True}


class ProtocolV1Message(BaseModel):
    """
    Protocol V1 TCP message format — 33 fields, pipe-delimited.
    Exchanged between the C++ FMS server and simulated robots at 15Hz.
    """
    # Identity
    msg_id: int = Field(description="Sequence number")
    timestamp: float = Field(description="Unix timestamp with ms precision")
    robot_id: str = Field(description="Robot identifier")

    # Action
    action_code: int = Field(default=0, description="Command from FMS")
    response_code: int = Field(default=0, description="Response from robot")

    # Position
    pos_x: float = Field(default=0.0, description="X position meters")
    pos_y: float = Field(default=0.0, description="Y position meters")
    heading: float = Field(default=0.0, description="Heading radians")

    # Velocity
    linear_velocity: float = Field(default=0.0, description="m/s")
    angular_velocity: float = Field(default=0.0, description="rad/s")

    # Navigation
    current_node: str = Field(default="", description="Current node name")
    target_node: str = Field(default="", description="Target node name")
    path_index: int = Field(default=0, description="Index in planned path")
    path_length: int = Field(default=0, description="Total path length")

    # Battery
    battery_pct: float = Field(default=100.0, ge=0, le=100)
    is_charging: bool = Field(default=False)
    battery_voltage: float = Field(default=24.0)
    battery_current: float = Field(default=0.0)

    # Status
    status: RobotStatus = Field(default=RobotStatus.IDLE)
    error_code: int = Field(default=0)
    error_message: str = Field(default="")

    # Task
    task_id: str = Field(default="")
    task_type: str = Field(default="")
    task_status: str = Field(default="")

    # Sensors
    lidar_min_range: float = Field(default=0.0, description="Min LiDAR range meters")
    lidar_front_range: float = Field(default=0.0, description="Front sector range")
    barcode_value: str = Field(default="", description="Last barcode read")
    barcode_valid: bool = Field(default=False)

    # Obstacle
    obstacle_distance: float = Field(default=999.0, description="Nearest obstacle meters")
    obstacle_angle: float = Field(default=0.0, description="Obstacle bearing radians")

    # Attachment
    attachment_active: bool = Field(default=False)
    payload_kg: float = Field(default=0.0, ge=0)

    # Integrity
    crc32: int = Field(default=0, description="CRC32 checksum of pipe-delimited fields")

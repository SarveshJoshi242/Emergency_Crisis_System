"""
Pydantic models for data validation and MongoDB document structure.
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime, timezone
from enum import Enum


class SessionStatus(str, Enum):
    """Possible states for a guest session."""
    ACTIVE = "active"
    EVACUATING = "evacuating"
    SAFE = "safe"
    ABANDONED = "abandoned"


class ActionType(str, Enum):
    """Types of actions guests can take."""
    COMPLETED = "completed"
    REROUTE = "reroute"
    HELP = "help"


class GuestSessionCreate(BaseModel):
    """Input model for creating a guest session."""
    room_id: str = Field(..., description="Starting room ID")

    class Config:
        json_schema_extra = {
            "example": {
                "room_id": "101"
            }
        }


class GuestSession(BaseModel):
    """MongoDB document for guest session."""
    session_id: str = Field(..., description="Unique session ID")
    room_id: str = Field(..., description="Starting room ID")
    floor_id: str = Field(..., description="Floor ID")
    current_node: str = Field(..., description="Current location node")
    status: SessionStatus = Field(default=SessionStatus.ACTIVE)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "sess_abc123",
                "room_id": "101",
                "floor_id": "floor_1",
                "current_node": "room_101",
                "status": "active",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:05:00Z"
            }
        }


class GuestSessionResponse(BaseModel):
    """Response model for successful session creation/retrieval."""
    session_id: str
    floor_id: str
    room_id: str
    current_node: str
    status: SessionStatus
    created_at: datetime


class NodeInfo(BaseModel):
    """Information about a graph node."""
    id: str = Field(..., description="Node ID")
    label: str = Field(..., description="Display label")
    type: Literal[
        "room",
        "corridor",
        "stairs",
        "stairwell",
        "lobby",
        "safe_zone",
        "exit"
    ] = Field(..., description="Node type")
    position: Optional[dict] = Field(default=None, description="Optional coordinates")


class AvailableNodeIdsResponse(BaseModel):
    """Response model containing available node IDs."""
    nodes: List[str] = Field(..., description="List of available node IDs")


class EdgeInfo(BaseModel):
    """Information about a graph edge."""
    from_node: str = Field(..., description="Source node ID", alias="from")
    to_node: str = Field(..., description="Target node ID", alias="to")
    weight: float = Field(default=1.0, description="Edge weight/distance")

    class Config:
        populate_by_name = True


class FloorGraph(BaseModel):
    """MongoDB document for floor graph/plan."""
    floor_id: str = Field(..., description="Floor identifier")
    nodes: List[NodeInfo] = Field(default=[], description="List of nodes")
    edges: List[EdgeInfo] = Field(default=[], description="List of edges")
    synced_from_staff: bool = Field(default=True, description="Synced from staff backend")
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    class Config:
        json_schema_extra = {
            "example": {
                "floor_id": "floor_1",
                "nodes": [
                    {"id": "room_101", "label": "Conference Room", "type": "room"},
                    {"id": "corridor_a", "label": "Main Corridor", "type": "corridor"},
                    {"id": "exit_south", "label": "South Exit", "type": "exit"}
                ],
                "edges": [
                    {"from": "room_101", "to": "corridor_a", "weight": 5},
                    {"from": "corridor_a", "to": "exit_south", "weight": 10}
                ]
            }
        }


class EmergencyState(BaseModel):
    """MongoDB document for current emergency state."""
    is_active: bool = Field(default=False, description="Is emergency active")
    emergency_type: Optional[str] = Field(default=None, description="Type of emergency")
    affected_floors: List[str] = Field(default_factory=list, description="Affected floor IDs")
    blocked_nodes: List[str] = Field(default_factory=list, description="Blocked node IDs")
    safe_exits: List[str] = Field(default_factory=list, description="Safe exit node IDs")
    # synced_from_staff: False by default — staff-written docs don't include this field
    synced_from_staff: bool = Field(default=False)
    updated_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    class Config:
        # Allow extra fields in the document (e.g. MongoDB _id stripped by service)
        extra = "ignore"


class EmergencyStatusResponse(BaseModel):
    """Response model for emergency status."""
    active: bool
    emergency_type: Optional[str] = None
    affected_floors: List[str] = Field(default_factory=list)
    blocked_nodes: List[str] = Field(default_factory=list)
    safe_exits: List[str] = Field(default_factory=list)
    updated_at: Optional[datetime] = None


class GuestLog(BaseModel):
    """MongoDB document for guest action logging."""
    session_id: str = Field(..., description="Session ID")
    step: int = Field(..., description="Step number in route")
    action: ActionType = Field(..., description="Action type")
    node_id: Optional[str] = Field(default=None, description="Associated node")
    details: Optional[str] = Field(default=None, description="Additional details")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class UpdateLocationRequest(BaseModel):
    """Request to update guest location."""
    session_id: str
    node_id: str


class EvacuationRouteResponse(BaseModel):
    """Response containing evacuation route."""
    path: List[str] = Field(..., description="List of node IDs forming the route")
    distance: float = Field(default=0, description="Total route distance")


class NavigationStepsResponse(BaseModel):
    """Response containing step-by-step navigation."""
    steps: List[str] = Field(..., description="Human-readable navigation instructions")


class StepUpdateRequest(BaseModel):
    """Request to update completion of a step."""
    session_id: str
    action: ActionType
    details: Optional[str] = None


class RequestHelpRequest(BaseModel):
    """Request for help during evacuation."""
    session_id: str
    issue: str = Field(..., description="Description of the issue")


class SafeZoneConfirmationRequest(BaseModel):
    """Confirmation that guest reached safe zone."""
    session_id: str


class NotificationMessage(BaseModel):
    """Message from staff to guests."""
    id: str
    message: str
    priority: Literal["info", "warning", "critical"] = "info"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AvailableNodesResponse(BaseModel):
    """Response with available nodes for location selection."""
    nodes: List[NodeInfo] = Field(..., description="List of available nodes")

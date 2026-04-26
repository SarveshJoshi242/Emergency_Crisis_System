# ============================================================
#  Emergency Backend · models/floor_plan.py
#  Purpose: Strict Pydantic schemas for staff floor-plan management.
#           These are the CANONICAL definitions consumed by both the
#           staff and guest routing systems.
# ============================================================

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Allowed node types ────────────────────────────────────────────────────────

ALLOWED_NODE_TYPES: set[str] = {
    "room", "corridor", "stairwell", "lobby", "exit"
}


# ── Node schema ───────────────────────────────────────────────────────────────

class FloorNode(BaseModel):
    """A single navigable node in the floor graph."""
    id: str = Field(..., min_length=1, description="Unique node identifier within the floor")
    label: str = Field(..., min_length=1, description="Human-readable name shown in UI")
    x: float = Field(..., description="X coordinate on the floor plan image")
    y: float = Field(..., description="Y coordinate on the floor plan image")
    type: Literal["room", "corridor", "stairwell", "lobby", "exit"] = Field(
        ..., description="Semantic type of the node"
    )
    camera_source: Optional[str] = Field(
        None,
        description="RTSP URL, video file path, or camera ID for YOLO monitoring",
    )
    model_enabled: bool = Field(
        False,
        description="Whether YOLO fire detection is active for this node",
    )

    @field_validator("x", "y")
    @classmethod
    def coordinates_must_be_finite(cls, v: float) -> float:
        import math
        if math.isnan(v) or math.isinf(v):
            raise ValueError("Coordinates must be finite numbers")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "id": "room_101",
                "label": "Room 101",
                "x": 220.0,
                "y": 100.0,
                "type": "room",
                "camera_source": "rtsp://192.168.1.10:554/stream1",
                "model_enabled": True,
            }
        }


# ── Edge schema ───────────────────────────────────────────────────────────────

class FloorEdge(BaseModel):
    """A directed/undirected connection between two nodes."""
    from_node: str = Field(..., alias="from", description="Source node ID")
    to_node: str = Field(..., alias="to", description="Destination node ID")
    weight: float = Field(..., gt=0, description="Traversal cost — must be > 0")
    type: str = Field("corridor", description="Edge type: corridor | stairwell | elevator")

    @model_validator(mode="after")
    def no_self_loop(self) -> "FloorEdge":
        if self.from_node == self.to_node:
            raise ValueError(
                f"Self-loop detected: node '{self.from_node}' cannot connect to itself"
            )
        return self

    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "from": "corridor_a",
                "to": "room_101",
                "weight": 0.5,
                "type": "corridor",
            }
        }


# ── Graph schema ──────────────────────────────────────────────────────────────

class FloorGraph(BaseModel):
    """Embedded graph document stored inside each floor document."""
    nodes: List[FloorNode] = Field(default_factory=list)
    edges: List[FloorEdge] = Field(default_factory=list)

    class Config:
        populate_by_name = True


# ── Request bodies ────────────────────────────────────────────────────────────

class AddNodeRequest(BaseModel):
    """Body for POST /staff/floors/{floor_id}/nodes"""
    id: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    x: float
    y: float
    type: Literal["room", "corridor", "stairwell", "lobby", "exit"]
    camera_source: Optional[str] = Field(
        None,
        description="RTSP URL, video file path, or camera ID for YOLO monitoring",
    )
    model_enabled: bool = Field(
        False,
        description="Whether YOLO fire detection is active for this node",
    )

    @field_validator("x", "y")
    @classmethod
    def coordinates_must_be_finite(cls, v: float) -> float:
        import math
        if math.isnan(v) or math.isinf(v):
            raise ValueError("Coordinates must be finite numbers")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "id": "exit_north",
                "label": "North Exit",
                "x": 500.0,
                "y": 10.0,
                "type": "exit",
                "camera_source": None,
                "model_enabled": False,
            }
        }


class AddEdgeRequest(BaseModel):
    """Body for POST /staff/floors/{floor_id}/edges"""
    from_node: str = Field(..., alias="from")
    to_node: str = Field(..., alias="to")
    weight: float = Field(..., gt=0)
    type: str = Field("corridor")

    @model_validator(mode="after")
    def no_self_loop(self) -> "AddEdgeRequest":
        if self.from_node == self.to_node:
            raise ValueError("Self-loop: 'from' and 'to' must be different nodes")
        return self

    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "from": "corridor_a",
                "to": "exit_north",
                "weight": 1.2,
                "type": "corridor",
            }
        }


# ── Response schemas ──────────────────────────────────────────────────────────

class GraphValidationResult(BaseModel):
    """Response from POST /staff/floors/{floor_id}/validate"""
    valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    unreachable_nodes: List[str] = Field(default_factory=list)
    dead_end_nodes: List[str] = Field(default_factory=list)
    stats: dict = Field(default_factory=dict)


class SuggestedEdge(BaseModel):
    from_node: str
    to_node: str
    weight: float
    reason: str


class SuggestedNode(BaseModel):
    id: str
    label: str
    x: float
    y: float
    type: str
    reason: str


class FixSuggestionResult(BaseModel):
    """Response from POST /staff/floors/{floor_id}/suggest-fixes"""
    has_suggestions: bool
    suggested_edges: List[SuggestedEdge] = Field(default_factory=list)
    suggested_nodes: List[SuggestedNode] = Field(default_factory=list)
    duplicate_node_groups: List[List[str]] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class FloorPlanResponse(BaseModel):
    """Full floor document response (GET /staff/floors/{floor_id}/graph)"""
    id: str
    name: str
    image_url: Optional[str] = None
    graph: Optional[dict] = None
    created_at: str

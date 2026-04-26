# ============================================================
#  Emergency Backend · models/floor.py
# ============================================================

from pydantic import BaseModel, Field
from typing import List, Optional


class NodeModel(BaseModel):
    id: str
    label: str
    x: float
    y: float
    type: str  # "room" | "exit" | "corridor"


class EdgeModel(BaseModel):
    from_node: str = Field(..., alias="from")
    to_node: str = Field(..., alias="to")
    weight: float
    type: str  # "corridor" | "stairwell"

    class Config:
        populate_by_name = True


class GraphModel(BaseModel):
    nodes: List[NodeModel] = []
    edges: List[EdgeModel] = []


class FloorCreate(BaseModel):
    name: str


class FloorResponse(BaseModel):
    id: str
    name: str
    image_url: Optional[str] = None
    graph: Optional[GraphModel] = None
    created_at: str

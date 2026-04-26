# ============================================================
#  Emergency Backend · models/graph.py
#  Purpose: Manual graph correction request schemas
# ============================================================

from pydantic import BaseModel
from typing import List, Optional


class NodePatch(BaseModel):
    """Upsert a single node — add it or overwrite if id already exists."""
    id: str
    label: str
    x: float
    y: float
    type: str  # room | corridor | exit | stairwell | lobby


class EdgePatch(BaseModel):
    """Upsert an edge — add it or overwrite if from+to already exists."""
    from_node: str  # node id
    to_node: str    # node id
    weight: float = 1.0
    type: str = "corridor"


class GraphPatch(BaseModel):
    """
    Full graph replacement for bulk corrections.
    Used when staff completely redraws the graph after reviewing Gemini output.
    """
    nodes: List[NodePatch]
    edges: List[EdgePatch]


class NodeDelete(BaseModel):
    node_id: str  # also removes all edges referencing this node


class EdgeDelete(BaseModel):
    from_node: str
    to_node: str

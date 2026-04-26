"""
Floor graph service.

Reads directly from the canonical 'floors' collection written by the staff backend.
Both backends share the same MongoDB database (emergency_db), so no HTTP sync
or local cache is needed — the guest always sees the latest graph.

Handles:
- Retrieving floor graph data from shared 'floors' collection
- Node existence checks for location validation
- Node filtering for guest UI selection
"""
from app.models.schemas import FloorGraph, NodeInfo, EdgeInfo
from app.core.database import get_db
from bson import ObjectId
from datetime import datetime, timezone
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


class FloorGraphService:
    """Service for managing floor graphs — reads directly from shared 'floors' collection."""

    def __init__(self, db):
        self.db = db
        # Canonical collection written by staff backend
        self.floors_collection = db.floors

    async def get_floor_graph(self, floor_id: str) -> Optional[FloorGraph]:
        """
        Retrieve floor graph from the shared 'floors' collection.

        Accepts:
        - ObjectId string (staff _id)
        - floor_id slug (e.g. "floor_1")
        - floor name (e.g. "Floor 1")

        Returns None if not found.
        """
        query: dict = {"$or": [{"floor_id": floor_id}, {"name": floor_id}]}
        if ObjectId.is_valid(floor_id):
            query["$or"].append({"_id": ObjectId(floor_id)})

        doc = await self.floors_collection.find_one(query)
        if doc:
            return self._normalize_floor_doc(doc)
        return None

    def _normalize_floor_doc(self, doc: dict) -> FloorGraph:
        """
        Normalize a staff floor document to the guest FloorGraph model.

        Staff stores graph as:  doc.graph.nodes / doc.graph.edges
        Guest FloorGraph needs: floor_id, nodes (NodeInfo), edges (EdgeInfo)
        """
        graph_raw = doc.get("graph") or {}
        raw_nodes = graph_raw.get("nodes", [])
        raw_edges = graph_raw.get("edges", [])

        nodes: List[NodeInfo] = []
        for n in raw_nodes:
            # Map staff x/y coords into optional position dict for guest schema
            position = None
            if "x" in n and "y" in n:
                position = {"x": n["x"], "y": n["y"]}

            # Normalise node type — guest also accepts "stairs"/"safe_zone" but
            # staff canonical types are: room, corridor, stairwell, lobby, exit
            node_type = n.get("type", "corridor")
            if node_type not in {"room", "corridor", "stairs", "stairwell", "lobby", "safe_zone", "exit"}:
                node_type = "corridor"

            nodes.append(NodeInfo(
                id=n["id"],
                label=n.get("label", n["id"]),
                type=node_type,
                position=position,
            ))

        edges: List[EdgeInfo] = []
        for e in raw_edges:
            from_node = e.get("from") or e.get("from_node")
            to_node = e.get("to") or e.get("to_node")
            if from_node and to_node:
                edges.append(EdgeInfo(**{"from": from_node, "to": to_node, "weight": e.get("weight", 1.0)}))

        floor_id_value = (
            doc.get("floor_id")          # slug field (new)
            or str(doc.get("_id", ""))   # ObjectId string fallback
        )

        return FloorGraph(
            floor_id=floor_id_value,
            nodes=nodes,
            edges=edges,
            synced_from_staff=True,
            updated_at=doc.get("updated_at") or doc.get("created_at") or datetime.now(timezone.utc),
        )

    async def get_graph_nodes(self, floor_id: str) -> List[NodeInfo]:
        """Get all nodes in a floor graph."""
        graph = await self.get_floor_graph(floor_id)
        return graph.nodes if graph else []

    async def get_available_nodes_for_selection(self, floor_id: str) -> List[NodeInfo]:
        """
        Get nodes suitable for manual location selection by guests.
        Returns rooms, corridors, lobbies, stairwells, and exits.
        """
        graph = await self.get_floor_graph(floor_id)
        if not graph:
            raise ValueError(f"Floor '{floor_id}' not found")
        if not graph.nodes:
            raise ValueError("No nodes defined on this floor")

        selectable_types = {"room", "corridor", "lobby", "stairwell", "stairs", "safe_zone", "exit"}
        return [node for node in graph.nodes if node.type in selectable_types]

    async def node_exists(self, floor_id: str, node_id: str) -> bool:
        """Check if a node exists in the floor graph."""
        graph = await self.get_floor_graph(floor_id)
        if not graph:
            return False
        return any(node.id == node_id for node in graph.nodes)

    # save_floor_graph kept for backward compat but is now a no-op.
    # The canonical source is db.floors (written by staff).
    async def save_floor_graph(self, floor_graph: dict) -> bool:
        """
        Deprecated — no longer writes a local cache.
        Both backends share the same DB; staff writes to 'floors' directly.
        Kept to avoid import errors in existing route code.
        """
        logger.debug("save_floor_graph() called — no-op (reads directly from shared floors collection)")
        return True

    async def delete_floor_graph(self, floor_id: str) -> bool:
        """Placeholder — floor deletion is staff-only."""
        logger.warning("delete_floor_graph() called on guest service — ignored (staff-only operation)")
        return False


async def get_floor_graph_service() -> FloorGraphService:
    """Dependency injection for floor graph service."""
    db = get_db()
    return FloorGraphService(db)

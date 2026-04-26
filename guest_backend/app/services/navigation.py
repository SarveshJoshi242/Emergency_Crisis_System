"""
Navigation service.

Handles:
- Route generation and computation
- Step-by-step navigation instructions
- Route recalculation/rerouting

IMPORTANT:
- Reads ONLY from db.floors (canonical, written by staff)
- db.floor_graphs is NEVER queried (legacy stale cache — removed)
- When start node is blocked, attempts to route via nearest safe neighbour
"""
from app.models.schemas import EvacuationRouteResponse, NavigationStepsResponse
from app.core.database import get_db
from app.utils.pathfinding import build_graph, dijkstra, get_exit_nodes
from bson import ObjectId
from typing import List, Optional, Set
import logging

logger = logging.getLogger(__name__)


def _floor_query(floor_id: str) -> dict:
    """Build a multi-field lookup query for a floor document."""
    query: dict = {"$or": [{"floor_id": floor_id}, {"name": floor_id}]}
    if ObjectId.is_valid(floor_id):
        query["$or"].append({"_id": ObjectId(floor_id)})
    return query


class NavigationService:
    """Service for navigation and pathfinding."""

    def __init__(self, db):
        self.db = db
        # Single canonical source — staff writes here, guest reads here
        self.floors_collection = db.floors
        self.emergency_collection = db.emergency_state

    async def _fetch_floor_doc(self, floor_id: str) -> Optional[dict]:
        """Fetch floor document from the canonical floors collection."""
        try:
            doc = await self.floors_collection.find_one(
                _floor_query(floor_id),
                max_time_ms=3000,
            )
            return doc
        except Exception as e:
            logger.error(f"Failed to fetch floor document for '{floor_id}': {e}")
            return None

    async def generate_evacuation_route(
        self,
        current_node: str,
        floor_id: str,
        blocked_nodes: Optional[Set[str]] = None,
        safe_exits: Optional[List[str]] = None,
    ) -> EvacuationRouteResponse:
        """
        Generate evacuation route from current position to the nearest safe exit.

        If current_node itself is blocked, attempts to route via the nearest
        unblocked adjacent node before raising an error.
        """
        floor_doc = await self._fetch_floor_doc(floor_id)
        if not floor_doc:
            raise ValueError(
                f"Floor '{floor_id}' not found. "
                "Ensure staff has created this floor via POST /staff/floors."
            )

        graph_source = floor_doc.get("graph", {})
        floor_graph = build_graph(graph_source)
        node_ids = {n.get("id") for n in floor_graph["nodes"] if n.get("id")}

        if not node_ids:
            raise ValueError(f"Floor '{floor_id}' has no nodes defined in its graph.")

        if current_node not in node_ids:
            raise ValueError(
                f"Current location '{current_node}' not found in floor graph. "
                "Update your location before requesting a route."
            )

        if blocked_nodes is None:
            blocked_nodes = set()

        # Resolve exits
        if safe_exits:
            # Keep only exits that exist in the graph; drop None values
            safe_exits = [e for e in safe_exits if e and e in node_ids]
        if not safe_exits:
            safe_exits = [e for e in get_exit_nodes(graph_source) if e]  # drop None

        if not safe_exits:
            raise ValueError(
                f"Floor '{floor_id}' has no exit nodes defined. "
                "Staff must add at least one node with type='exit' to the floor graph."
            )

        # ── Primary route attempt ─────────────────────────────────────────────
        path, distance, _ = dijkstra(
            floor_graph,
            start=current_node,
            targets=safe_exits,
            blocked_nodes=blocked_nodes,
        )

        # ── Fallback: no path found — try via nearest safe neighbour ─────────
        # Triggered when current_node is blocked OR surrounded by blocked nodes.
        if not path:
            if current_node in blocked_nodes:
                logger.warning(
                    "Current node '%s' is blocked. Attempting route via nearest "
                    "unblocked adjacent node. floor='%s'",
                    current_node, floor_id,
                )
            else:
                logger.warning(
                    "No direct path from '%s' (exits may be blocked). "
                    "Attempting route via nearest adjacent node. floor='%s'",
                    current_node, floor_id,
                )
            adjacency = floor_graph.get("adjacency", {})
            neighbours = adjacency.get(current_node, [])
            for neighbour_id, _ in sorted(neighbours, key=lambda x: x[1]):
                if neighbour_id not in blocked_nodes:
                    alt_path, alt_dist, _ = dijkstra(
                        floor_graph,
                        start=neighbour_id,
                        targets=safe_exits,
                        blocked_nodes=blocked_nodes,
                    )
                    if alt_path:
                        path = [current_node] + alt_path
                        distance = alt_dist
                        logger.info(
                            "Rerouted via neighbour '%s' from '%s'. floor='%s'",
                            neighbour_id, current_node, floor_id,
                        )
                        break

        if not path:
            raise ValueError(
                f"No valid evacuation path found from '{current_node}' on floor '{floor_id}'. "
                "All exits may be blocked or unreachable. "
                "Contact staff for manual assistance."
            )

        logger.info("Evacuation route: %s", " → ".join(path))
        return EvacuationRouteResponse(path=path, distance=distance)

    async def get_navigation_steps(
        self, path: List[str], floor_id: str
    ) -> NavigationStepsResponse:
        """Convert a path of node IDs into human-readable navigation steps."""
        if not path or len(path) < 2:
            return NavigationStepsResponse(steps=["You are at the destination."])

        floor_doc = await self._fetch_floor_doc(floor_id)
        if not floor_doc:
            return self._fallback_navigation_steps(path)

        graph_source = floor_doc.get("graph", {})
        node_map = {
            node["id"]: node.get("label", node["id"])
            for node in graph_source.get("nodes", [])
        }
        type_map = {
            node["id"]: node.get("type", "location")
            for node in graph_source.get("nodes", [])
        }

        steps = []

        # First step — leave starting location
        start_label = node_map.get(path[0], path[0])
        if type_map.get(path[0]) == "room":
            steps.append(f"Exit from {start_label}")
        else:
            steps.append(f"Leave {start_label}")

        # Middle steps
        for i in range(1, len(path) - 1):
            current_id = path[i]
            next_id = path[i + 1]
            current_label = node_map.get(current_id, current_id)
            next_type = type_map.get(next_id, "location")

            if next_type in ("stairs", "stairwell"):
                next_label = node_map.get(next_id, next_id)
                steps.append(f"Move through {current_label}, then use stairs ({next_label})")
            elif next_type == "exit":
                steps.append(f"Continue through {current_label} toward exit")
            else:
                steps.append(f"Move to {current_label}")

        # Final step — reach destination
        final_id = path[-1]
        final_label = node_map.get(final_id, final_id)
        final_type = type_map.get(final_id, "location")

        if final_type == "exit":
            steps.append(f"Exit through {final_label} — you are safe")
        elif final_type == "safe_zone":
            steps.append(f"Proceed to the safe zone at {final_label}")
        else:
            steps.append(f"Reach {final_label}")

        return NavigationStepsResponse(steps=steps)

    def _fallback_navigation_steps(self, path: List[str]) -> NavigationStepsResponse:
        """Generate steps using raw node IDs when floor doc is unavailable."""
        if len(path) < 2:
            return NavigationStepsResponse(steps=["Check your current location."])
        steps = [f"Leave {path[0]}"]
        for node in path[1:-1]:
            steps.append(f"Move toward {node}")
        steps.append(f"Proceed to {path[-1]}")
        return NavigationStepsResponse(steps=steps)


async def get_navigation_service() -> NavigationService:
    """Dependency injection for navigation service."""
    db = get_db()
    return NavigationService(db)

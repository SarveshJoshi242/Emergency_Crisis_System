# ============================================================
#  Emergency Backend · services/floor_service.py
#  Purpose: Deterministic graph stub seeded from any floor image
# ============================================================

from datetime import datetime, timezone
from typing import Optional
import logging
from bson import ObjectId
from database import get_collection

logger = logging.getLogger(__name__)



# ── Seeded graph ──────────────────────────────────────────────────────────────
# Any uploaded image produces this realistic hotel-floor graph.
# Replace build_stub_graph() with CV/LLM call when ready.

STUB_NODES = [
    # Core navigation spine
    {"id": "lobby",       "label": "Lobby",       "x": 300, "y": 300, "type": "lobby"},
    {"id": "corridor_a",  "label": "Corridor A",  "x": 200, "y": 300, "type": "corridor"},
    {"id": "corridor_b",  "label": "Corridor B",  "x": 400, "y": 300, "type": "corridor"},
    {"id": "stairwell_1", "label": "Stairwell",   "x": 50,  "y": 300, "type": "stairwell"},
    # Guest rooms
    {"id": "room_101",    "label": "Room 101",    "x": 200, "y": 150, "type": "room"},
    {"id": "room_102",    "label": "Room 102",    "x": 400, "y": 150, "type": "room"},
    {"id": "room_103",    "label": "Room 103",    "x": 200, "y": 450, "type": "room"},
    {"id": "room_104",    "label": "Room 104",    "x": 400, "y": 450, "type": "room"},
    # ── EXITS — required for evacuation routing ──────────────────────────────
    {"id": "exit_main",       "label": "Main Exit",       "x": 600, "y": 300, "type": "exit"},
    {"id": "exit_stair_left", "label": "Stair Exit Left", "x": 50,  "y": 300, "type": "exit"},
]

STUB_EDGES = [
    # Spine connections
    {"from": "lobby",       "to": "corridor_a",  "weight": 1.0, "type": "corridor"},
    {"from": "lobby",       "to": "corridor_b",  "weight": 1.0, "type": "corridor"},
    # Rooms off corridor A
    {"from": "corridor_a",  "to": "room_101",    "weight": 0.5, "type": "corridor"},
    {"from": "corridor_a",  "to": "room_103",    "weight": 0.5, "type": "corridor"},
    # Rooms off corridor B
    {"from": "corridor_b",  "to": "room_102",    "weight": 0.5, "type": "corridor"},
    {"from": "corridor_b",  "to": "room_104",    "weight": 0.5, "type": "corridor"},
    # Stairwell connected to corridor A
    {"from": "corridor_a",  "to": "stairwell_1", "weight": 1.5, "type": "stairwell"},
    # EXIT connections (evacuation routes)
    {"from": "corridor_b",  "to": "exit_main",       "weight": 1.2, "type": "corridor"},
    {"from": "stairwell_1", "to": "exit_stair_left", "weight": 0.8, "type": "stairwell"},
]


def build_stub_graph() -> dict:
    return {"nodes": STUB_NODES, "edges": STUB_EDGES}


# ── Service functions ─────────────────────────────────────────────────────────

async def create_floor(name: str, image_url: Optional[str]) -> dict:
    col = get_collection("floors")
    doc = {
        "name": name,
        "image_url": image_url,
        "graph": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await col.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    doc.pop("_id", None)
    return doc


async def process_floor(floor_id: str) -> dict:
    """
    Analyze the floor plan image with Gemini Vision → generate graph.
    Falls back to stub graph if image missing or Gemini unavailable.
    """
    from services.gemini_service import generate_graph_from_image

    col = get_collection("floors")
    floor_doc = await col.find_one({"_id": ObjectId(floor_id)})

    floor_name = floor_doc.get("name", floor_id) if floor_doc else floor_id
    image_path = floor_doc.get("image_url") if floor_doc else None

    if image_path:
        graph = await generate_graph_from_image(image_path, floor_name)
    else:
        logger.warning(f"No image found for floor {floor_id} — using stub graph")
        graph = build_stub_graph()

    await col.update_one(
        {"_id": ObjectId(floor_id)},
        {"$set": {"graph": graph}},
    )
    return graph


async def get_floor(floor_id: str) -> Optional[dict]:
    col = get_collection("floors")
    doc = await col.find_one({"_id": ObjectId(floor_id)})
    if doc:
        doc["id"] = str(doc.pop("_id"))
    return doc


# ── Manual graph correction ───────────────────────────────────────────────────

async def upsert_node(floor_id: str, node: dict) -> bool:
    """Add or overwrite a node by id. Returns False if floor not found."""
    col = get_collection("floors")
    # Remove existing node with same id, then push new one
    result = await col.update_one(
        {"_id": ObjectId(floor_id)},
        {"$pull": {"graph.nodes": {"id": node["id"]}}},
    )
    if result.matched_count == 0:
        return False
    await col.update_one(
        {"_id": ObjectId(floor_id)},
        {"$push": {"graph.nodes": node}},
    )
    return True


async def upsert_edge(floor_id: str, edge: dict) -> str:
    """
    Add or overwrite an edge. Returns 'ok', 'floor_not_found', or 'node_not_found'.
    Validates that both from_node and to_node exist as node ids in the graph.
    """
    col = get_collection("floors")
    doc = await col.find_one({"_id": ObjectId(floor_id)}, {"graph.nodes": 1})
    if not doc:
        return "floor_not_found"

    node_ids = {n["id"] for n in (doc.get("graph") or {}).get("nodes", [])}
    from_id = edge.get("from_node") or edge.get("from")
    to_id   = edge.get("to_node")   or edge.get("to")

    if from_id not in node_ids or to_id not in node_ids:
        return "node_not_found"

    edge_doc = {
        "from":   from_id,
        "to":     to_id,
        "weight": edge.get("weight", 1.0),
        "type":   edge.get("type", "corridor"),
    }
    # Remove existing edge in either direction, then add
    await col.update_one(
        {"_id": ObjectId(floor_id)},
        {"$pull": {"graph.edges": {
            "$or": [
                {"from": from_id, "to": to_id},
                {"from": to_id,   "to": from_id},
            ]
        }}},
    )
    await col.update_one(
        {"_id": ObjectId(floor_id)},
        {"$push": {"graph.edges": edge_doc}},
    )
    return "ok"


async def remove_node(floor_id: str, node_id: str) -> bool:
    """Remove a node AND all edges that reference it."""
    col = get_collection("floors")
    result = await col.update_one(
        {"_id": ObjectId(floor_id)},
        {
            "$pull": {
                "graph.nodes": {"id": node_id},
                "graph.edges": {"$or": [{"from": node_id}, {"to": node_id}]},
            }
        },
    )
    return result.matched_count == 1


async def remove_edge(floor_id: str, from_id: str, to_id: str) -> bool:
    """Remove an edge (checks both directions)."""
    col = get_collection("floors")
    result = await col.update_one(
        {"_id": ObjectId(floor_id)},
        {"$pull": {"graph.edges": {
            "$or": [
                {"from": from_id, "to": to_id},
                {"from": to_id,   "to": from_id},
            ]
        }}},
    )
    return result.matched_count == 1


async def replace_graph(floor_id: str, graph: dict) -> bool:
    """Replace the entire graph document (bulk correction)."""
    col = get_collection("floors")
    result = await col.update_one(
        {"_id": ObjectId(floor_id)},
        {"$set": {"graph": graph}},
    )
    return result.matched_count == 1


# ============================================================
#  Emergency Backend · services/floor_plan_service.py
#  Purpose: DB-level operations for the staff floor-plan system.
#           Enforces all data-integrity rules before writing.
# ============================================================

from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from bson.errors import InvalidId

from config import settings
from database import get_collection

logger = logging.getLogger(__name__)

FLOORS_COL = "floors"


# ── Internal helpers ──────────────────────────────────────────────────────────

def _safe_object_id(floor_id: str) -> ObjectId:
    try:
        return ObjectId(floor_id)
    except (InvalidId, TypeError):
        raise ValueError(f"Invalid floor_id format: '{floor_id}'")


def _floor_to_response(doc: dict) -> dict:
    """Convert a raw Mongo document to a clean API response dict."""
    doc["id"] = str(doc.pop("_id"))
    return doc


# ── Floor CRUD ────────────────────────────────────────────────────────────────

async def create_floor(name: str, image_url: Optional[str]) -> dict:
    """
    Create a new floor document with an empty graph.
    Returns the created document.
    """
    col = get_collection(FLOORS_COL)
    now = datetime.now(timezone.utc)
    doc = {
        "name": name.strip(),
        "floor_id": name.strip().lower().replace(" ", "_"),
        "image_url": image_url,
        "graph": {
            "nodes": [],
            "edges": [],
        },
        "created_at": now,
        "updated_at": now,
    }
    result = await col.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    doc.pop("_id", None)
    doc["created_at"] = now.isoformat()
    logger.info(f"✅ Created floor '{name}' → id={doc['id']}")
    return doc


async def get_floor(floor_id: str) -> Optional[dict]:
    """Fetch a floor by ID. Returns None if not found."""
    col = get_collection(FLOORS_COL)
    oid = _safe_object_id(floor_id)
    doc = await col.find_one({"_id": oid})
    if doc:
        doc = _floor_to_response(doc)
        # Serialize datetime
        if isinstance(doc.get("created_at"), datetime):
            doc["created_at"] = doc["created_at"].isoformat()
    return doc


async def list_floors() -> list[dict]:
    """Return all floors (lightweight — no full graph)."""
    col = get_collection(FLOORS_COL)
    cursor = col.find({}, {"graph": 0})  # omit graph for performance
    floors = []
    async for doc in cursor:
        doc = _floor_to_response(doc)
        if isinstance(doc.get("created_at"), datetime):
            doc["created_at"] = doc["created_at"].isoformat()
        floors.append(doc)
    return floors


async def delete_floor(floor_id: str) -> bool:
    """
    Delete a floor document from MongoDB and remove its uploaded image (if any).
    Returns True if deleted, False if not found.
    """
    col = get_collection(FLOORS_COL)
    oid = _safe_object_id(floor_id)

    # Fetch first so we can clean up the image file
    doc = await col.find_one({"_id": oid}, {"image_url": 1})
    if doc is None:
        return False

    # Delete from DB
    result = await col.delete_one({"_id": oid})
    if result.deleted_count == 0:
        return False

    # Attempt to remove the image file from disk (non-fatal)
    image_url: str = doc.get("image_url") or ""
    if image_url:
        # image_url is like "/uploads/floorplans/foo.png" — map to filesystem
        rel = image_url.lstrip("/")  # "uploads/floorplans/foo.png"
        abs_path = os.path.join(settings.UPLOAD_DIR, *rel.split("/")[1:])
        try:
            if os.path.isfile(abs_path):
                os.remove(abs_path)
                logger.info("Deleted floor image: %s", abs_path)
        except OSError as e:
            logger.warning("Could not delete floor image '%s': %s", abs_path, e)

    logger.info("Deleted floor '%s'", floor_id)
    return True


async def get_floor_graph(floor_id: str) -> Optional[dict]:
    """Return only the graph sub-document for a floor.
    Accepts either a MongoDB ObjectId string OR a floor_id slug (e.g. 'third_floor').
    """
    col = get_collection(FLOORS_COL)

    # Try ObjectId lookup first; fall back to floor_id slug search
    doc = None
    try:
        oid = ObjectId(floor_id)
        doc = await col.find_one({"_id": oid})
    except (InvalidId, TypeError):
        pass

    if not doc:
        # Slug match — case-insensitive to handle "Third Floor" vs "third_floor"
        doc = await col.find_one({
            "$or": [
                {"floor_id": floor_id},
                {"floor_id": floor_id.lower().replace(" ", "_")},
                {"name": floor_id},
            ]
        })

    if not doc:
        return None

    graph = doc.get("graph") or {"nodes": [], "edges": []}
    return {
        "floor_id": floor_id,
        "name": doc.get("name"),
        "image_url": doc.get("image_url"),
        "nodes": graph.get("nodes", []),
        "edges": graph.get("edges", []),
        "graph": graph,
    }


# ── Node operations ───────────────────────────────────────────────────────────

async def add_node(floor_id: str, node: dict) -> dict:
    """
    Add a node to a floor's graph.

    Raises:
        ValueError: if floor not found OR node ID already exists in the floor.
    """
    col = get_collection(FLOORS_COL)
    oid = _safe_object_id(floor_id)

    # Fetch current node list to check uniqueness
    doc = await col.find_one({"_id": oid}, {"graph.nodes": 1})
    if not doc:
        raise ValueError(f"Floor '{floor_id}' not found.")

    existing_ids: set[str] = {
        n["id"] for n in (doc.get("graph") or {}).get("nodes", [])
    }
    if node["id"] in existing_ids:
        raise ValueError(
            f"Node ID '{node['id']}' already exists in floor '{floor_id}'. "
            "Node IDs must be unique within a floor."
        )

    # Persist
    await col.update_one(
        {"_id": oid},
        {"$push": {"graph.nodes": node}},
    )
    logger.info(f"Added node '{node['id']}' to floor {floor_id}")
    return node


async def get_nodes(floor_id: str) -> Optional[list[dict]]:
    """Return all nodes for a floor, or None if floor does not exist."""
    doc = await get_floor_graph(floor_id)
    if doc is None:
        return None
    return doc["graph"].get("nodes", [])


async def delete_node(floor_id: str, node_id: str) -> bool:
    """Remove a node and all edges that reference it."""
    col = get_collection(FLOORS_COL)
    oid = _safe_object_id(floor_id)
    result = await col.update_one(
        {"_id": oid},
        {
            "$pull": {
                "graph.nodes": {"id": node_id},
                "graph.edges": {"$or": [{"from": node_id}, {"to": node_id}]},
            }
        },
    )
    return result.matched_count == 1


# ── Edge operations ───────────────────────────────────────────────────────────

async def add_edge(floor_id: str, edge: dict) -> dict:
    """
    Add a validated edge to a floor's graph.

    Validation enforced here (in addition to Pydantic schema):
    - Both 'from' and 'to' node IDs must exist.
    - No self-loops.
    - No duplicate edges (directional OR undirected).

    Raises:
        ValueError on any violation.
    """
    col = get_collection(FLOORS_COL)
    oid = _safe_object_id(floor_id)

    doc = await col.find_one({"_id": oid}, {"graph": 1})
    if not doc:
        raise ValueError(f"Floor '{floor_id}' not found.")

    graph = doc.get("graph") or {"nodes": [], "edges": []}
    node_ids: set[str] = {n["id"] for n in graph.get("nodes", [])}
    existing_edges = graph.get("edges", [])

    f = edge["from"]
    t = edge["to"]

    # Self-loop check (belt-and-suspenders after Pydantic)
    if f == t:
        raise ValueError(f"Self-loop: node '{f}' cannot connect to itself.")

    # Node existence
    if f not in node_ids:
        raise ValueError(f"Edge source node '{f}' does not exist in floor '{floor_id}'.")
    if t not in node_ids:
        raise ValueError(f"Edge destination node '{t}' does not exist in floor '{floor_id}'.")

    # Duplicate check (treat as undirected)
    for existing in existing_edges:
        ef, et = existing.get("from"), existing.get("to")
        if (ef == f and et == t) or (ef == t and et == f):
            raise ValueError(
                f"Duplicate edge: a connection between '{f}' and '{t}' already exists."
            )

    # Persist
    await col.update_one(
        {"_id": oid},
        {"$push": {"graph.edges": edge}},
    )
    logger.info(f"Added edge {f}→{t} to floor {floor_id}")
    return edge


async def get_edges(floor_id: str) -> Optional[list[dict]]:
    """Return all edges for a floor, or None if floor does not exist."""
    doc = await get_floor_graph(floor_id)
    if doc is None:
        return None
    return doc["graph"].get("edges", [])


async def delete_edge(floor_id: str, from_node: str, to_node: str) -> bool:
    """Remove an edge (checks both directions)."""
    col = get_collection(FLOORS_COL)
    oid = _safe_object_id(floor_id)
    result = await col.update_one(
        {"_id": oid},
        {
            "$pull": {
                "graph.edges": {
                    "$or": [
                        {"from": from_node, "to": to_node},
                        {"from": to_node, "to": from_node},
                    ]
                }
            }
        },
    )
    return result.matched_count == 1


# ── Graph replacement ─────────────────────────────────────────────────────────

async def replace_graph(floor_id: str, graph: dict) -> bool:
    """Overwrite the entire graph. Returns False if floor not found."""
    col = get_collection(FLOORS_COL)
    oid = _safe_object_id(floor_id)
    result = await col.update_one(
        {"_id": oid},
        {"$set": {"graph": graph, "updated_at": datetime.now(timezone.utc)}},
    )
    return result.matched_count == 1


# ── Image upload helper ───────────────────────────────────────────────────────

def save_floor_image(filename: str, file_obj: Any) -> str:
    """
    Save an uploaded floor image to UPLOAD_DIR.
    Returns the saved file path.
    """
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    filepath = os.path.join(settings.UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        shutil.copyfileobj(file_obj, f)
    return filepath


async def update_floor_image(floor_id: str, image_url: str) -> bool:
    """Update the image_url field of a floor."""
    col = get_collection(FLOORS_COL)
    oid = _safe_object_id(floor_id)
    result = await col.update_one(
        {"_id": oid},
        {"$set": {"image_url": image_url}},
    )
    return result.matched_count == 1

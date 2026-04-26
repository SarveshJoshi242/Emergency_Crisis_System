# ============================================================
#  Emergency Backend · routers/floor.py
# ============================================================

import os
import shutil
import asyncio
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from config import settings
from services import floor_service
from models.graph import NodePatch, EdgePatch, GraphPatch, NodeDelete, EdgeDelete

router = APIRouter(prefix="/floor", tags=["Floor"])


@router.post("/upload", summary="Upload a floor plan image (auto-generates graph via Gemini Vision)")
async def upload_floor(
    name: str = Form(...),
    image: UploadFile = File(...),
):
    """
    Upload a floor plan image.
    Gemini Vision automatically analyzes the image and generates the navigation graph.
    No need to call /process separately.
    """
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    filename = image.filename or "floor_image.jpg"
    filepath = os.path.join(settings.UPLOAD_DIR, filename)

    # Use asyncio.to_thread so blocking file I/O doesn't stall the event loop
    def _write_file():
        with open(filepath, "wb") as f:
            shutil.copyfileobj(image.file, f)

    await asyncio.to_thread(_write_file)

    floor = await floor_service.create_floor(name=name, image_url=filepath)
    graph = await floor_service.process_floor(floor["id"])
    floor["graph"] = graph
    return floor


@router.post("/{floor_id}/process", summary="Re-run Gemini Vision on the floor image")
async def process_floor(floor_id: str):
    """Re-analyze the floor plan image and regenerate the graph."""
    graph = await floor_service.process_floor(floor_id)
    return {"floor_id": floor_id, "graph": graph}


@router.get("/{floor_id}", summary="Get floor with embedded graph")
async def get_floor(floor_id: str):
    floor = await floor_service.get_floor(floor_id)
    if not floor:
        raise HTTPException(status_code=404, detail="Floor not found")
    return floor


# ── Manual graph correction endpoints ────────────────────────────────────────

@router.patch("/{floor_id}/graph/node", summary="Add or update a node (manual correction)")
async def patch_node(floor_id: str, body: NodePatch):
    """
    Upsert a node in the floor's graph.
    If a node with the same id already exists, it is overwritten.
    Use this to fix Gemini Vision mistakes.
    """
    updated = await floor_service.upsert_node(floor_id, body.model_dump())
    if not updated:
        raise HTTPException(status_code=404, detail="Floor not found")
    return {"floor_id": floor_id, "node": body}


@router.patch("/{floor_id}/graph/edge", summary="Add or update an edge (manual correction)")
async def patch_edge(floor_id: str, body: EdgePatch):
    """
    Upsert an edge between two nodes.
    Validates that both node IDs exist in the floor graph.
    """
    result = await floor_service.upsert_edge(floor_id, body.model_dump())
    if result == "floor_not_found":
        raise HTTPException(status_code=404, detail="Floor not found")
    if result == "node_not_found":
        raise HTTPException(status_code=400, detail="One or both node IDs not found in this floor's graph")
    return {"floor_id": floor_id, "edge": body}


@router.delete("/{floor_id}/graph/node", summary="Remove a node and its edges (manual correction)")
async def delete_node(floor_id: str, body: NodeDelete):
    """Remove a node and all edges that reference it."""
    ok = await floor_service.remove_node(floor_id, body.node_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Floor or node not found")
    return {"floor_id": floor_id, "removed_node": body.node_id}


@router.delete("/{floor_id}/graph/edge", summary="Remove an edge (manual correction)")
async def delete_edge(floor_id: str, body: EdgeDelete):
    """Remove a specific edge between two nodes."""
    ok = await floor_service.remove_edge(floor_id, body.from_node, body.to_node)
    if not ok:
        raise HTTPException(status_code=404, detail="Floor or edge not found")
    return {"floor_id": floor_id, "removed_edge": {"from": body.from_node, "to": body.to_node}}


@router.put("/{floor_id}/graph", summary="Replace the full graph (bulk correction)")
async def replace_graph(floor_id: str, body: GraphPatch):
    """
    Replace the entire graph with a corrected version.
    Use when staff has reviewed and fully redrawn the graph.
    """
    graph = {
        "nodes": [n.model_dump() for n in body.nodes],
        "edges": [
            {**e.model_dump(), "from": e.from_node, "to": e.to_node}
            for e in body.edges
        ],
    }
    ok = await floor_service.replace_graph(floor_id, graph)
    if not ok:
        raise HTTPException(status_code=404, detail="Floor not found")
    return {"floor_id": floor_id, "graph": graph}


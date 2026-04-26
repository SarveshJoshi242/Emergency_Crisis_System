# ============================================================
#  Emergency Backend · routers/staff_floors.py
#  Purpose: Unified floor plan management API (staff-side).
#           All floor operations live here under /staff/floors.
#
#  Public API surface (intentionally minimal):
#    POST   /staff/floors                    – create floor (auto-generates graph)
#    GET    /staff/floors                    – list floors
#    GET    /staff/floors/{id}/graph         – get full graph
#    PUT    /staff/floors/{id}/graph         – replace full graph (primary write path)
#    POST   /staff/floors/{id}/process       – Gemini Vision auto-generate / re-run
#    POST   /staff/floors/{id}/validate      – full validation
#    POST   /staff/floors/{id}/suggest-fixes – AI fix suggestions
#    GET    /staff/floors/{id}/heatmap       – congestion heatmap
# ============================================================

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from config import settings
from models.floor_plan import AddEdgeRequest, AddNodeRequest
from services import floor_plan_service, floor_service
from services.graph_advisor import build_heatmap, suggest_fixes
from services.graph_validator import validate_graph

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/staff/floors", tags=["Floor Plan Management"])


# ─────────────────────────────────────────────────────────────────────────────
#  CREATE FLOOR  ·  POST /staff/floors
# ─────────────────────────────────────────────────────────────────────────────

@router.post("", status_code=201, summary="Upload floor image & create floor (auto-generates graph)")
async def create_floor(
    name: str = Form(...),
    image: Optional[UploadFile] = File(None),
):
    """
    Upload a floor plan image and create a new floor.

    Graph is auto-generated immediately after creation:
    - If GEMINI_API_KEY is set: Gemini Vision analyzes the uploaded image.
    - Fallback (no key / no image / Gemini error): a complete realistic hotel
      stub graph is used (room_101..room_104, corridors, stairwells, exits)
      so the floor is always usable for pathfinding without manual setup.

    To re-run graph generation on an existing floor:
      POST /staff/floors/{id}/process
    """
    image_url: Optional[str] = None

    if image and image.filename:
        # Save under uploads/floorplans/ so static serving works cleanly
        floorplans_dir = os.path.join(settings.UPLOAD_DIR, "floorplans")
        os.makedirs(floorplans_dir, exist_ok=True)

        # Sanitize filename: spaces → underscores, no path traversal
        safe_filename = os.path.basename(image.filename).replace(" ", "_")
        filepath = os.path.join(floorplans_dir, safe_filename)

        def _save():
            with open(filepath, "wb") as f:
                shutil.copyfileobj(image.file, f)

        await asyncio.to_thread(_save)

        # Always store a URL-safe forward-slash path — NEVER a filesystem path
        image_url = f"/uploads/floorplans/{safe_filename}"

    # 1. Create the floor record (graph starts empty inside floor_plan_service)
    floor = await floor_plan_service.create_floor(name=name, image_url=image_url)
    floor_id = floor["id"]

    # 2. Immediately generate the graph (Gemini Vision → stub fallback)
    try:
        graph = await floor_service.process_floor(floor_id)
        floor["graph"] = graph
        logger.info(
            "Graph auto-generated for floor '%s' | nodes=%d edges=%d",
            floor_id,
            len(graph.get("nodes", [])),
            len(graph.get("edges", [])),
        )
    except Exception as e:
        logger.warning(
            "Graph auto-generation failed for floor '%s' (non-fatal): %s — "
            "call POST /staff/floors/%s/process to retry.",
            floor_id, e, floor_id,
        )

    return floor


# ─────────────────────────────────────────────────────────────────────────────
#  LIST FLOORS  ·  GET /staff/floors
# ─────────────────────────────────────────────────────────────────────────────

@router.get("", summary="List all floors")
async def list_floors():
    return await floor_plan_service.list_floors()


# ─────────────────────────────────────────────────────────────────────────────
#  DELETE FLOOR  ·  DELETE /staff/floors/{floor_id}
# ─────────────────────────────────────────────────────────────────────────────

@router.delete("/{floor_id}", status_code=200, summary="Delete a floor and its image")
async def delete_floor(floor_id: str):
    """
    Permanently delete a floor document from MongoDB and remove the uploaded
    image file from disk. Broadcasts a `floor_deleted` WebSocket event to all
    connected staff dashboards for instant UI removal.
    """
    ok = await floor_plan_service.delete_floor(floor_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Floor '{floor_id}' not found.")

    # Real-time broadcast — staff dashboards remove this floor instantly
    try:
        from services.websocket_manager import manager
        await manager.broadcast("floor_deleted", {"floor_id": floor_id})
    except Exception as ws_err:
        logger.warning("floor_deleted WS broadcast failed (non-fatal): %s", ws_err)

    return {"floor_id": floor_id, "deleted": True}


# ─────────────────────────────────────────────────────────────────────────────
#  GET FLOOR GRAPH  ·  GET /staff/floors/{floor_id}/graph
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{floor_id}/graph", summary="Get full floor graph for UI rendering")
async def get_floor_graph(floor_id: str):
    doc = await floor_plan_service.get_floor_graph(floor_id)
    if doc is None:
        raise HTTPException(404, f"Floor '{floor_id}' not found.")
    return doc


# ─────────────────────────────────────────────────────────────────────────────
#  PROCESS (Gemini Vision)  ·  POST /staff/floors/{floor_id}/process
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{floor_id}/process", summary="Re-run Gemini Vision to auto-generate graph (stub fallback)")
async def process_floor(floor_id: str):
    """
    Re-analyze the uploaded floor plan image with Gemini Vision and regenerate
    the graph. If Gemini is unavailable, the realistic stub graph is used.
    Saves the result directly to the floor document.
    """
    graph = await floor_service.process_floor(floor_id)
    return {
        "floor_id": floor_id,
        "graph": graph,
        "nodes_count": len(graph.get("nodes", [])),
        "edges_count": len(graph.get("edges", [])),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  VALIDATE  ·  POST /staff/floors/{floor_id}/validate
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{floor_id}/validate", summary="🚨 Validate floor graph")
async def validate_floor_graph(floor_id: str):
    """
    Runs full validation: node uniqueness, edge integrity, BFS connectivity,
    exit existence, per-room exit reachability, dead-end detection.
    """
    doc = await floor_plan_service.get_floor_graph(floor_id)
    if doc is None:
        raise HTTPException(404, f"Floor '{floor_id}' not found.")
    return validate_graph(doc.get("graph") or {"nodes": [], "edges": []})


# ─────────────────────────────────────────────────────────────────────────────
#  SUGGEST FIXES  ·  POST /staff/floors/{floor_id}/suggest-fixes
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{floor_id}/suggest-fixes", summary="Auto-fix suggestions")
async def suggest_graph_fixes(floor_id: str):
    """Missing exits, disconnected nodes, proximity edges, corridor gaps."""
    doc = await floor_plan_service.get_floor_graph(floor_id)
    if doc is None:
        raise HTTPException(404, f"Floor '{floor_id}' not found.")
    return suggest_fixes(doc.get("graph") or {"nodes": [], "edges": []})


# ─────────────────────────────────────────────────────────────────────────────
#  HEATMAP  ·  GET /staff/floors/{floor_id}/heatmap
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{floor_id}/heatmap", summary="Congestion heatmap & critical path analysis")
async def floor_heatmap(floor_id: str):
    doc = await floor_plan_service.get_floor_graph(floor_id)
    if doc is None:
        raise HTTPException(404, f"Floor '{floor_id}' not found.")
    return build_heatmap(doc.get("graph") or {"nodes": [], "edges": []})


# ─────────────────────────────────────────────────────────────────────────────
#  BULK REPLACE GRAPH  ·  PUT /staff/floors/{floor_id}/graph
# ─────────────────────────────────────────────────────────────────────────────

class BulkGraphRequest(BaseModel):
    nodes: List[AddNodeRequest] = Field(default_factory=list)
    edges: List[AddEdgeRequest] = Field(default_factory=list)

    class Config:
        populate_by_name = True


@router.put("/{floor_id}/graph", summary="Replace full graph (bulk import — validates first)")
async def replace_floor_graph(floor_id: str, body: BulkGraphRequest):
    graph = {
        "nodes": [{"id": n.id, "label": n.label, "x": n.x, "y": n.y, "type": n.type, "camera_source": n.camera_source, "model_enabled": n.model_enabled} for n in body.nodes],
        "edges": [{"from": e.from_node, "to": e.to_node, "weight": e.weight, "type": e.type} for e in body.edges],
    }
    result = validate_graph(graph)
    if not result["valid"]:
        raise HTTPException(422, detail={
            "message": "Graph failed validation — not saved.",
            "errors": result["errors"],
            "warnings": result["warnings"],
        })
    ok = await floor_plan_service.replace_graph(floor_id, graph)
    if not ok:
        raise HTTPException(404, f"Floor '{floor_id}' not found.")
    return {"floor_id": floor_id, "message": "Graph replaced.", "validation": result}

"""
Guest-side API routes for emergency evacuation system.

Public endpoints (no JWT):
- POST /guest/check-in      — create session from room_id
- GET  /guest/rooms         — list all rooms from all floors

Authenticated endpoints:
- GET  /guest/path          — combined pathfinding + steps (session_id query param)
- GET  /guest/emergency-status — current emergency state
... (original endpoints preserved below)
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from app.models.schemas import (
    GuestSessionCreate, GuestSessionResponse, EvacuationRouteResponse,
    NavigationStepsResponse, UpdateLocationRequest, StepUpdateRequest,
    RequestHelpRequest, SafeZoneConfirmationRequest, AvailableNodeIdsResponse,
    AvailableNodesResponse, EmergencyStatusResponse, NotificationMessage,
    SessionStatus
)
from app.services.guest_session import GuestSessionService, get_guest_session_service
from app.services.floor_graph import FloorGraphService, get_floor_graph_service
from app.services.navigation import NavigationService, get_navigation_service
from app.services.emergency import EmergencyService, get_emergency_service
from app.services.interaction import InteractionService, get_interaction_service
from app.services.integration import get_integration_service
from app.core.database import get_db
from app.models.schemas import ActionType
from datetime import datetime, timezone
from bson import ObjectId
from typing import Optional
import logging
# JWT guards — imported after sys.path is patched in main.py
from auth.dependencies import require_guest, require_staff_or_guest  # noqa: E402

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/guest", tags=["guest"])


# ============================================================================
# PUBLIC: CHECK-IN (no JWT required)
# ============================================================================
@router.post("/check-in", summary="Public: Check in to a room and create guest session")
async def check_in(data: dict):
    """
    Public endpoint — no JWT required.

    Accepts { room_id } and:
    1. Searches all floors for a node with that ID
    2. Creates a guest_sessions document
    3. Returns { session_id, room_id, floor_id, status }

    Works for ANY room_id that exists in any floor graph.
    """
    room_id = (data.get("room_id") or "").strip()
    if not room_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="room_id is required"
        )

    db = get_db()

    # ── Search across ALL floors for a node with this id ─────────────────────
    floor_id: Optional[str] = None

    # Primary: search graph.nodes (staff-written floor documents)
    cursor = db.floors.find(
        {"graph.nodes": {"$elemMatch": {"id": room_id}}}
    ).sort("created_at", -1)

    best_doc = None
    async for doc in cursor:
        if not best_doc:
            best_doc = doc
        if doc.get("floor_id"):  # prefer floor docs with a human slug
            best_doc = doc
            break

    # Fallback: top-level nodes array (legacy schema)
    if not best_doc:
        best_doc = await db.floors.find_one(
            {"nodes": {"$elemMatch": {"id": room_id, "type": "room"}}}
        )

    if not best_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Room '{room_id}' not found in any floor graph. "
                   "Ensure the floor has been created via staff portal."
        )

    # Prefer human slug, fall back to ObjectId string
    floor_id = best_doc.get("floor_id") or str(best_doc["_id"])

    # ── Create session ────────────────────────────────────────────────────────
    session_service = GuestSessionService(db)
    try:
        session = await session_service.create_session(
            room_id=room_id,
            floor_id=floor_id,
        )
    except Exception as e:
        logger.error("check-in: session creation failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create session"
        )

    logger.info("[check-in] room=%s floor=%s session=%s", room_id, floor_id, session.session_id)

    return {
        "session_id": session.session_id,
        "room_id":    session.room_id,
        "floor_id":   session.floor_id,
        "status":     "active",
    }


# ============================================================================
# PUBLIC: LIST ALL ROOMS (no JWT required)
# ============================================================================
@router.get("/rooms", summary="Public: List all rooms from all floor graphs")
async def list_all_rooms():
    """
    Public endpoint — no JWT required.

    Scans ALL floor documents and returns every node with type='room'.
    Frontend uses this to populate the room picker on check-in.

    Response:
        [ { room_id, floor_id, label, floor_name } ]
    """
    db = get_db()
    rooms = []

    async for floor_doc in db.floors.find({}, {"_id": 1, "name": 1, "floor_id": 1, "graph": 1}).sort("created_at", -1):
        floor_oid_str = str(floor_doc["_id"])
        # Prefer human-readable slug; fall back to ObjectId string
        fid = floor_doc.get("floor_id") or floor_oid_str
        fname = floor_doc.get("name", fid)

        graph = floor_doc.get("graph") or {}
        for node in graph.get("nodes", []):
            if node.get("type") == "room" and node.get("id"):
                rooms.append({
                    "room_id":    node["id"],
                    "floor_id":   fid,
                    "label":      node.get("label") or node["id"],
                    "floor_name": fname,
                })

    logger.debug("[rooms] returned %d rooms across all floors", len(rooms))
    return rooms


# ============================================================================
# COMBINED PATH ENDPOINT — GET /guest/path?session_id=...
# ============================================================================
@router.get("/path", summary="Get evacuation path + steps for a session (no JWT required)")
async def get_evacuation_path(session_id: str = Query(..., description="Guest session ID")):
    """
    Combined pathfinding + navigation steps endpoint.

    Designed for the frontend polling loop:
      GET /guest/path?session_id=<id>

    Behavior:
    1. Fetch session (room, floor, current_node)
    2. Fetch emergency state (blocked_nodes, safe_exits)
    3. Run Dijkstra pathfinding
    4. Convert path → human-readable steps
    5. Return { steps: [{ instruction, node }] }

    Returns empty steps if no emergency is active (not an error).
    Falls back to raw node IDs if floor doc is unavailable.
    """
    db = get_db()

    # ── 1. Fetch session ──────────────────────────────────────────────────────
    session_doc = await db.guest_sessions.find_one({"session_id": session_id})
    if not session_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found"
        )

    current_node = session_doc.get("current_node") or session_doc.get("room_id")
    floor_id     = session_doc.get("floor_id", "")

    # ── 2. Fetch emergency state ──────────────────────────────────────────────
    state_doc = await db.emergency_state.find_one({}, sort=[("updated_at", -1)])
    blocked_nodes: set = set()
    safe_exits: list   = []
    is_active          = False

    if state_doc:
        is_active     = bool(state_doc.get("is_active", False))
        blocked_nodes = set(state_doc.get("blocked_nodes") or [])
        safe_exits    = state_doc.get("safe_exits") or []

    # If no active emergency, return empty steps (normal / safe state)
    if not is_active:
        return {"steps": [], "is_active": False}

    # ── 3. Fetch floor graph ──────────────────────────────────────────────────
    floor_doc = None
    if ObjectId.is_valid(floor_id):
        floor_doc = await db.floors.find_one({"_id": ObjectId(floor_id)})
    if not floor_doc:
        floor_doc = await db.floors.find_one(
            {"$or": [{"floor_id": floor_id}, {"name": floor_id}]}
        )

    if not floor_doc:
        logger.warning("[path] floor '%s' not found — returning fallback steps", floor_id)
        return {
            "steps": [
                {"instruction": "Emergency active. Follow floor signage to nearest exit.", "node": current_node}
            ],
            "is_active": True,
        }

    graph_source = floor_doc.get("graph") or {}
    nodes_list   = graph_source.get("nodes", [])
    edges_list   = graph_source.get("edges", [])

    # ── 4. Resolve exits ─────────────────────────────────────────────────────
    graph_exit_nodes = [
        n.get("id") for n in nodes_list
        if n.get("type") == "exit" and n.get("id")
    ]
    resolved_exits = [e for e in safe_exits if e] or graph_exit_nodes

    if not resolved_exits:
        logger.warning("[path] no exits found for floor '%s' — returning fallback", floor_id)
        return {
            "steps": [
                {"instruction": "No exits defined. Contact staff immediately.", "node": current_node}
            ],
            "is_active": True,
        }

    # ── 5. Run pathfinding ────────────────────────────────────────────────────
    from app.utils.pathfinding import build_graph, dijkstra

    node_ids = {n.get("id") for n in nodes_list if n.get("id")}

    # If current_node is not in graph, try to find nearest known node
    actual_start = current_node if current_node in node_ids else None
    if not actual_start:
        # Attempt to use room_id as fallback start
        room_id_fallback = session_doc.get("room_id", "")
        actual_start = room_id_fallback if room_id_fallback in node_ids else None

    if not actual_start:
        return {
            "steps": [
                {"instruction": "Could not locate your position. Follow emergency signage.", "node": "unknown"}
            ],
            "is_active": True,
        }

    floor_graph = build_graph(graph_source)
    path, _distance, _target = dijkstra(
        floor_graph,
        start=actual_start,
        targets=resolved_exits,
        blocked_nodes=blocked_nodes,
    )

    # ── 5b. Fallback path via adjacent node if blocked ────────────────────────
    if not path and actual_start in blocked_nodes:
        adjacency = floor_graph.get("adjacency", {})
        for neighbour_id, _ in sorted(adjacency.get(actual_start, []), key=lambda x: x[1]):
            if neighbour_id not in blocked_nodes:
                alt_path, alt_dist, _ = dijkstra(
                    floor_graph, start=neighbour_id,
                    targets=resolved_exits, blocked_nodes=blocked_nodes,
                )
                if alt_path:
                    path = [actual_start] + alt_path
                    break

    if not path:
        return {
            "steps": [
                {"instruction": "No clear path found. Stay put and call for help.", "node": actual_start}
            ],
            "is_active": True,
        }

    # ── 6. Convert path → step instructions ──────────────────────────────────
    node_label = {n.get("id"): n.get("label") or n.get("id") for n in nodes_list}
    node_type  = {n.get("id"): n.get("type", "location") for n in nodes_list}

    steps = []

    # Step 0: leave starting point
    start_label = node_label.get(path[0], path[0])
    if node_type.get(path[0]) == "room":
        steps.append({"instruction": f"Exit {start_label}", "node": path[0]})
    else:
        steps.append({"instruction": f"Leave {start_label}", "node": path[0]})

    # Middle steps
    for i in range(1, len(path) - 1):
        nid   = path[i]
        nlbl  = node_label.get(nid, nid)
        ntype = node_type.get(nid, "location")
        nxtid = path[i + 1]
        nxttype = node_type.get(nxtid, "location")

        if ntype in ("stairs", "stairwell"):
            steps.append({"instruction": f"Use {nlbl}", "node": nid})
        elif nxttype == "exit":
            steps.append({"instruction": f"Continue through {nlbl} toward exit", "node": nid})
        else:
            steps.append({"instruction": f"Move to {nlbl}", "node": nid})

    # Final step
    final_id  = path[-1]
    final_lbl = node_label.get(final_id, final_id)
    ftype     = node_type.get(final_id, "location")
    if ftype == "exit":
        steps.append({"instruction": f"EXIT through {final_lbl} — you are safe!", "node": final_id})
    else:
        steps.append({"instruction": f"Reach {final_lbl}", "node": final_id})

    logger.info("[path] session=%s path=%s", session_id, " → ".join(path))
    return {"steps": steps, "is_active": True}


# ============================================================================
# 1. START GUEST SESSION
# ============================================================================
@router.post("/session/start", response_model=GuestSessionResponse)
async def start_session(
    data: GuestSessionCreate,
    _auth: dict = Depends(require_guest),            # 🔒 must be checked-in guest
    session_service: GuestSessionService = Depends(get_guest_session_service),
    integration_service = Depends(get_integration_service)
):
    """
    Start a new guest evacuation session.
    
    Steps:
    1. Get room-to-floor mapping from staff backend
    2. Create session with initial node = room
    3. Return session ID and floor ID
    
    Input:
    - room_id: The guest's starting room
    
    Output:
    - session_id, floor_id, room_id, current_node, status, created_at
    """
    try:
        logger.info("Looking up room: %s", data.room_id)

        # Try staff backend mapping first
        floor_id = await integration_service.get_room_floor_mapping(data.room_id)

        if not floor_id:
            logger.info("Staff backend unavailable or room not mapped; falling back to local DB lookup")
            db = get_db()
            query = {
                "$or": [
                    {
                        "graph.nodes": {
                            "$elemMatch": {
                                "id": data.room_id,
                                "type": "room"
                            }
                        }
                    },
                    {
                        "nodes": {
                            "$elemMatch": {
                                "id": data.room_id,
                                "type": "room"
                            }
                        }
                    }
                ]
            }
            floor = await db.floors.find_one(query)
            logger.debug("Local floor lookup result for room %s: %s", data.room_id, floor)

            if floor:
                floor_id = floor.get("floor_id") or floor.get("name") or str(floor.get("_id"))

        if not floor_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Room {data.room_id} not found in any floor"
            )

        session = await session_service.create_session(
            room_id=data.room_id,
            floor_id=floor_id
        )

        logger.info(f"Session started: {session.session_id}")
        return session
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create session"
        )


# ============================================================================
# 2. GET FLOOR PLAN (GRAPH)
# ============================================================================
@router.get("/floor/{floor_id}")
async def get_floor_plan(
    floor_id: str,
    _auth: dict = Depends(require_staff_or_guest),   # 🔒 staff or guest
    floor_graph_service: FloorGraphService = Depends(get_floor_graph_service),
    integration_service = Depends(get_integration_service)
):
    """
    Get the floor plan/graph for a floor.

    Primary path: reads shared 'floors' collection directly (same DB as staff).
    Fallback:     calls staff bridge if local lookup fails (e.g. first boot).

    Returns nodes (rooms, corridors, exits) and edges (connections).
    """
    try:
        # Primary: direct DB read (staff writes to this same collection)
        floor_graph = await floor_graph_service.get_floor_graph(floor_id)

        if floor_graph is None:
            # Fallback: sync from staff bridge (only when direct read fails)
            graph_data = await integration_service.sync_floor_plan(floor_id)
            if graph_data is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Floor {floor_id} not found"
                )
            # save_floor_graph is now a no-op — data lives in shared floors collection
            floor_graph = await floor_graph_service.get_floor_graph(floor_id)

        if floor_graph is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Floor {floor_id} not found"
            )

        return {
            "floor_id": floor_graph.floor_id,
            "nodes": [
                {
                    "id": node.id,
                    "label": node.label,
                    "type": node.type,
                    "position": node.position
                }
                for node in floor_graph.nodes
            ],
            "edges": [
                {
                    "from": edge.from_node,
                    "to": edge.to_node,
                    "weight": edge.weight
                }
                for edge in floor_graph.edges
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting floor plan: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve floor plan"
        )


# ============================================================================
# 3. SELECT / UPDATE CURRENT POSITION
# ============================================================================
@router.post("/update-location")
async def update_location(
    data: UpdateLocationRequest,
    _auth: dict = Depends(require_guest),            # 🔒 guest only
    session_service: GuestSessionService = Depends(get_guest_session_service),
    floor_graph_service: FloorGraphService = Depends(get_floor_graph_service)
):
    """
    Update the guest's current location.
    
    This endpoint allows guests to manually select their current position
    from a list of available nodes (rooms, corridors).
    
    Input:
    - session_id: Guest session ID
    - node_id: Selected node ID
    
    Output:
    - message: "location updated"
    """
    try:
        # Get session
        session = await session_service.get_session(data.session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        # Validate node exists
        if not await floor_graph_service.node_exists(session.floor_id, data.node_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Node {data.node_id} not found in floor {session.floor_id}"
            )
        
        # Update location
        success = await session_service.update_current_node(data.session_id, data.node_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update location"
            )
        
        return {"message": "location updated", "node_id": data.node_id}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating location: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update location"
        )


# ============================================================================
# 4. GET EMERGENCY STATUS  (public — no JWT for demo compatibility)
# ============================================================================
@router.get("/emergency-status")
async def get_emergency_status(
    emergency_service: EmergencyService = Depends(get_emergency_service),
):
    """
    Get the current emergency status.

    Public endpoint — no JWT required for demo compatibility.

    Returns BOTH:
      active: bool      — machine-readable
      status: str       — 'active' | 'inactive'  (frontend-compatible)

    Primary path: reads db.emergency_state directly (written through by staff
    alert_service on every alert create/resolve — no HTTP call needed).
    """
    try:
        state = await emergency_service.get_current_emergency_state()
        if not state:
            state = {
                "is_active": False,
                "emergency_type": None,
                "affected_floors": [],
                "blocked_nodes": [],
                "safe_exits": [],
                "updated_at": datetime.now(timezone.utc),
            }

        is_active = bool(state.get("is_active", False))
        return {
            "active":          is_active,
            "status":          "active" if is_active else "inactive",
            "emergency_type":  state.get("emergency_type"),
            "affected_floors": state.get("affected_floors", []),
            "blocked_nodes":   state.get("blocked_nodes", []),
            "safe_exits":      state.get("safe_exits", []),
            "updated_at":      (
                state.get("updated_at").isoformat()
                if hasattr(state.get("updated_at"), "isoformat")
                else str(state.get("updated_at", ""))
            ),
        }

    except Exception as e:
        logger.error(f"Error getting emergency status: {e}")
        # Safe default: do NOT assume emergency in non-emergency baseline
        return {
            "active":          False,
            "status":          "inactive",
            "emergency_type":  None,
            "affected_floors": [],
            "blocked_nodes":   [],
            "safe_exits":      [],
            "updated_at":      datetime.now(timezone.utc).isoformat(),
        }


# ============================================================================
# 5. GENERATE EVACUATION ROUTE (CORE ENGINE)
# ============================================================================
@router.post("/evacuation-route", response_model=EvacuationRouteResponse)
async def generate_evacuation_route(
    data: dict,  # {"session_id": "..."}
    _auth: dict = Depends(require_guest),            # 🔒 guest only
    session_service: GuestSessionService = Depends(get_guest_session_service),
    navigation_service: NavigationService = Depends(get_navigation_service),
    emergency_service: EmergencyService = Depends(get_emergency_service)
):
    """
    Generate evacuation route to safe zone.
    
    Logic:
    1. Get current session and current node
    2. Get emergency state (blocked nodes, safe exits)
    3. Run pathfinding (Dijkstra)
    4. Return path
    
    Input:
    - session_id: Guest session ID
    
    Output:
    - path: List of node IDs [room_101, corridor_a, stairs_1, exit_south]
    - distance: Total route distance
    """
    try:
        session_id = data.get("session_id")
        if not session_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="session_id required"
            )
        
        # Get session
        session = await session_service.get_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        # Get emergency state (returns dict from shared emergency_state collection)
        emergency_status = await emergency_service.get_current_emergency_state()
        blocked_nodes = set(emergency_status.get("blocked_nodes", [])) if emergency_status else set()
        safe_exits = emergency_status.get("safe_exits", []) if emergency_status else []
        
        # Generate route
        route = await navigation_service.generate_evacuation_route(
            current_node=session.current_node,
            floor_id=session.floor_id,
            blocked_nodes=blocked_nodes,
            safe_exits=safe_exits
        )
        
        logger.info(f"Generated route for session {session_id}: {route.path}")
        return route
    
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Evacuation route validation error: {e}")
        status_code = status.HTTP_404_NOT_FOUND if "not found" in str(e).lower() else status.HTTP_400_BAD_REQUEST
        return JSONResponse(status_code=status_code, content={"error": str(e)})
    except Exception as e:
        logger.error(f"Error generating evacuation route: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate evacuation route"
        )


# ============================================================================
# 6. STEP-BY-STEP NAVIGATION
# ============================================================================
@router.post("/navigation-steps", response_model=NavigationStepsResponse)
async def get_navigation_steps(
    data: dict,  # {"session_id": "...", "path": [...]}
    _auth: dict = Depends(require_guest),            # 🔒 guest only
    session_service: GuestSessionService = Depends(get_guest_session_service),
    navigation_service: NavigationService = Depends(get_navigation_service)
):
    """
    Convert evacuation path into human-readable navigation steps.
    
    Input:
    - session_id: Guest session ID
    - path: List of node IDs (from evacuation-route endpoint)
    
    Output:
    - steps: List of instructions ["Exit your room", "Move to Corridor A", ...]
    """
    try:
        session_id = data.get("session_id")
        path = data.get("path", [])
        
        if not session_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="session_id required"
            )
        
        # Get session to find floor
        session = await session_service.get_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        # Convert path to steps
        steps = await navigation_service.get_navigation_steps(path, session.floor_id)
        
        return steps
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating navigation steps: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate navigation steps"
        )


# ============================================================================
# 7. STEP RESPONSE HANDLING
# ============================================================================
@router.post("/step-update")
async def step_update(
    data: StepUpdateRequest,
    _auth: dict = Depends(require_guest),            # 🔒 guest only
    session_service: GuestSessionService = Depends(get_guest_session_service),
    interaction_service: InteractionService = Depends(get_interaction_service)
):
    """
    Handle guest response to each step.
    
    After each step, guest responds with:
    - completed: Move to next step
    - reroute: Recalculate route
    - help: Send help request to staff
    
    Input:
    - session_id: Guest session ID
    - action: "completed" | "reroute" | "help"
    - details: Optional additional details
    
    Output:
    - message: Action confirmation
    - next_action: For frontend (generate-route, next-step, contact-staff)
    """
    try:
        # Get session
        session = await session_service.get_session(data.session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        # Log action
        success = await interaction_service.log_action(
            session_id=data.session_id,
            step=0,  # Step counter managed by frontend
            action=data.action,
            details=data.details
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to log action"
            )
        
        # Determine next action based on guest response
        next_action = None
        if data.action == ActionType.COMPLETED:
            next_action = "next-step"
        elif data.action == ActionType.REROUTE:
            next_action = "generate-route"
        elif data.action == ActionType.HELP:
            next_action = "contact-staff"
        
        return {
            "message": f"Action {data.action.value} recorded",
            "next_action": next_action
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing step update: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process step update"
        )


# ============================================================================
# 8. REROUTE API
# ============================================================================
@router.post("/reroute", response_model=EvacuationRouteResponse)
async def reroute(
    data: dict,  # {"session_id": "..."}
    _auth: dict = Depends(require_guest),            # 🔒 guest only
    session_service: GuestSessionService = Depends(get_guest_session_service),
    navigation_service: NavigationService = Depends(get_navigation_service),
    emergency_service: EmergencyService = Depends(get_emergency_service)
):
    """
    Request route recalculation from current position.
    
    Same as generate_evacuation_route but from updated current position.
    """
    try:
        session_id = data.get("session_id")
        if not session_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="session_id required"
            )
        
        # Get session
        session = await session_service.get_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        # Get updated emergency state (returns dict from shared emergency_state collection)
        emergency_status = await emergency_service.get_current_emergency_state()
        blocked_nodes = set(emergency_status.get("blocked_nodes", [])) if emergency_status else set()
        safe_exits = emergency_status.get("safe_exits", []) if emergency_status else []

        # Generate new route from current position
        route = await navigation_service.generate_evacuation_route(
            current_node=session.current_node,
            floor_id=session.floor_id,
            blocked_nodes=blocked_nodes,
            safe_exits=safe_exits
        )
        
        logger.info(f"Reroute generated for session {session_id}: {route.path}")
        return route
    
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Reroute validation error: {e}")
        status_code = status.HTTP_404_NOT_FOUND if "not found" in str(e).lower() else status.HTTP_400_BAD_REQUEST
        return JSONResponse(status_code=status_code, content={"error": str(e)})
    except Exception as e:
        logger.error(f"Error rerouting: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate reroute"
        )


# ============================================================================
# 9. EMERGENCY HELP REQUEST
# ============================================================================
@router.post("/request-help")
async def request_help(
    data: RequestHelpRequest,
    session_service: GuestSessionService = Depends(get_guest_session_service),
    interaction_service: InteractionService = Depends(get_interaction_service),
    integration_service = Depends(get_integration_service)
):
    """
    Guest requests help from staff.
    
    Sends help request to staff backend with current location and issue.
    
    Input:
    - session_id: Guest session ID
    - issue: Description of the issue (e.g., "trapped", "injured", "lost")
    
    Output:
    - message: "Help request sent"
    - request_id: For tracking
    """
    try:
        # Get session
        session = await session_service.get_session(data.session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        # Log the help request locally
        await interaction_service.log_action(
            session_id=data.session_id,
            step=0,
            action=ActionType.HELP,
            node_id=session.current_node,
            details=data.issue
        )
        
        # Send to staff backend (includes floor_id for better dashboard filtering)
        success = await integration_service.send_help_request(
            session_id=data.session_id,
            current_node=session.current_node,
            issue=data.issue,
            floor_id=session.floor_id
        )
        
        if not success:
            logger.warning(f"Help request may not have reached staff for {data.session_id}")
            # Don't fail - we logged it locally
        
        return {
            "message": "help request sent",
            "session_id": data.session_id,
            "status": "pending"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error requesting help: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to request help"
        )


# ============================================================================
# 10. SAFE ZONE CONFIRMATION
# ============================================================================
@router.post("/reached-safe-zone")
async def reached_safe_zone(
    data: SafeZoneConfirmationRequest,
    session_service: GuestSessionService = Depends(get_guest_session_service),
    integration_service = Depends(get_integration_service)
):
    """
    Confirm that guest has reached safe zone.
    
    Updates session status and notifies staff backend for headcount and
    accountability.
    
    Input:
    - session_id: Guest session ID
    
    Output:
    - message: "Safe zone confirmed"
    """
    try:
        # Get session
        session = await session_service.get_session(data.session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        # Mark as safe locally
        success = await session_service.mark_safe(data.session_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update session status"
            )
        
        # Notify staff backend
        await integration_service.notify_safe_reached(
            session_id=data.session_id,
            final_location=session.current_node
        )
        
        logger.info(f"Guest {data.session_id} marked as safe")
        
        return {
            "message": "safe zone confirmed",
            "session_id": data.session_id,
            "status": SessionStatus.SAFE.value
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error confirming safe zone: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to confirm safe zone"
        )


# ============================================================================
# 11. GET NOTIFICATIONS
# ============================================================================
@router.get("/notifications")
async def get_notifications(
    floor_id: str,
    _auth: dict = Depends(require_staff_or_guest),   # 🔒 staff or guest
    integration_service = Depends(get_integration_service)
):
    """
    Get notifications/alerts from staff backend.
    
    Examples:
    - "Do not use lifts"
    - "Fire spreading to floor 2"
    - "Evacuate via south exit only"
    
    Query Params:
    - floor_id: Filter notifications for specific floor
    
    Output:
    - notifications: List of messages with priority
    """
    try:
        notifications = await integration_service.get_notifications(floor_id)
        
        return {
            "floor_id": floor_id,
            "notifications": notifications,
            "count": len(notifications)
        }
    
    except Exception as e:
        logger.error(f"Error getting notifications: {e}")
        return {
            "floor_id": floor_id,
            "notifications": [],
            "count": 0
        }


# ============================================================================
# HELPER ENDPOINTS
# ============================================================================

@router.get("/available-nodes/{floor_id}", response_model=AvailableNodeIdsResponse)
async def get_available_nodes(
    floor_id: str,
    _auth: dict = Depends(require_staff_or_guest),   # 🔒 staff or guest
    floor_graph_service: FloorGraphService = Depends(get_floor_graph_service)
):
    """
    Get list of available nodes for manual location selection.
    
    Returns rooms, corridors, and other selectable nodes on a floor.
    Useful for UI dropdowns when guests need to select their position.
    """
    try:
        nodes = await floor_graph_service.get_available_nodes_for_selection(floor_id)
        return AvailableNodeIdsResponse(nodes=[node.id for node in nodes])
    
    except ValueError as e:
        logger.warning(f"Available nodes validation error: {e}")
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"error": str(e)})
    except Exception as e:
        logger.error(f"Error getting available nodes: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve available nodes"
        )


@router.get("/session/{session_id}")
async def get_session_details(
    session_id: str,
    _auth: dict = Depends(require_guest),            # 🔒 guest only
    session_service: GuestSessionService = Depends(get_guest_session_service)
):
    """Get current session details."""
    try:
        session = await session_service.get_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found"
            )
        
        return {
            "session_id": session.session_id,
            "room_id": session.room_id,
            "floor_id": session.floor_id,
            "current_node": session.current_node,
            "status": session.status,
            "created_at": session.created_at,
            "updated_at": session.updated_at
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve session"
        )

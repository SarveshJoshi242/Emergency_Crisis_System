# ============================================================
#  Emergency Backend · services/gemini_service.py
#  Purpose: Gemini 2.5 Flash — task formatting + alert enrichment + floor vision
# ============================================================
#
#  1. format_tasks()           — enriches raw task names with actionable sentences
#  2. format_alert_message()   — professional alert summary text
#  3. generate_graph_from_image() — Gemini Vision analyzes floor plan → graph JSON
#
#  Fallback: if GEMINI_API_KEY is not set or any call fails,
#  raw strings / stub graph are returned — no crash, no hang.
# ============================================================

import json
import logging
from typing import List, Optional
import google.generativeai as genai
from config import settings

logger = logging.getLogger(__name__)

# ── Model init ────────────────────────────────────────────────────────────────
_model: Optional[genai.GenerativeModel] = None


def _get_model() -> Optional[genai.GenerativeModel]:
    global _model
    if _model is not None:
        return _model
    if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY == "your_gemini_api_key_here":
        return None
    try:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _model = genai.GenerativeModel("gemini-2.5-flash")
        return _model
    except Exception as e:
        logger.warning(f"Gemini init failed: {e}")
        return None


# ── Task formatting ───────────────────────────────────────────────────────────

async def format_tasks(
    raw_tasks: List[str],
    floor_name: str,
    risk_level: str,
    density_label: str,
    people_count: int,
    fire_conf: float,
    source_room: Optional[str] = None,
) -> List[str]:
    """
    Takes raw task names (e.g. "Evacuate Floor") and returns rich,
    context-aware actionable sentences for hotel staff.

    Falls back to raw names if Gemini is unavailable.
    """
    model = _get_model()
    if not model:
        return raw_tasks  # graceful fallback

    tasks_json = json.dumps(raw_tasks)
    location_str = f"Room {source_room} on {floor_name}" if source_room else f"Floor {floor_name}"
    avoidance_str = f"Staff should direct guests AWAY from Room {source_room}." if source_room else ""
    prompt = f"""You are an emergency management assistant for a hotel.

A fire emergency has been detected. Here is the situation:
- Location: {location_str}
- Risk Level: {risk_level}
- People detected: {people_count}
- Crowd density: {density_label}
- Fire confidence score: {fire_conf:.0%}
{avoidance_str}

You have been given these raw task names that staff must complete:
{tasks_json}

Rewrite each task as a clear, urgent, actionable instruction (1-2 sentences max).
Use imperative tone. Include the specific location and any relevant urgency.
If a room is specified, mention it explicitly (e.g. "Room 101").
Do NOT add new tasks or change their meaning.

Return ONLY a valid JSON array of strings in the same order as input.
Example format: ["Immediately evacuate all guests from Room 101...", "Check rooms 101-104..."]"""

    try:
        response = await model.generate_content_async(prompt)
        text = response.text.strip()
        # Strip markdown code fences if Gemini wraps in ```json
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        formatted = json.loads(text.strip())
        if isinstance(formatted, list) and len(formatted) == len(raw_tasks):
            return [str(t) for t in formatted]
        return raw_tasks  # shape mismatch — safe fallback
    except Exception as e:
        logger.warning(f"Gemini task formatting failed: {e}")
        return raw_tasks


# ── Alert message formatting ──────────────────────────────────────────────────

async def format_alert_message(
    floor_name: str,
    risk_level: str,
    action: str,
    people_count: int,
    fire_conf: float,
    density_label: str,
    source_room: Optional[str] = None,
) -> str:
    """
    Generates a clear, professional alert summary message.
    Falls back to a templated string if Gemini is unavailable.
    """
    model = _get_model()

    location_str = f"Room {source_room} on {floor_name}" if source_room else floor_name
    avoidance_note = f" Guests should avoid Room {source_room}." if source_room else ""
    fallback = (
        f"{risk_level} risk detected at {location_str}. "
        f"Action required: {action}. "
        f"{people_count} people detected, density: {density_label}.{avoidance_note}"
    )

    if not model:
        return fallback

    location_str = f"Room {source_room} on {floor_name}" if source_room else floor_name
    room_instruction = f"Guests should avoid Room {source_room} and use alternate routes." if source_room else ""
    prompt = f"""You are an emergency management system for a hotel.

Write a brief (2-3 sentence max), professional emergency alert message for staff dashboards.
Use clear, calm language — no panic words. Include key facts only.
If a specific room is mentioned, include it and advise guests to avoid it.

Situation:
- Location: {location_str}
- Risk Level: {risk_level}
- Recommended Action: {action}
- People Detected: {people_count}
- Crowd Density: {density_label}
- Fire Confidence: {fire_conf:.0%}
{room_instruction}

Return only the alert message text, no labels or formatting."""

    try:
        response = await model.generate_content_async(prompt)
        return response.text.strip()
    except Exception as e:
        logger.warning(f"Gemini alert message failed: {e}")
        return fallback



# ── Floor plan → Graph (Gemini Vision, two-step) ─────────────────────────────
#
# Step 1: Gemini extracts rooms+connections (simpler, more reliable)
# Step 2: Our backend converts to nodes+edges with normalization
#
# This is more reliable than asking Gemini to produce final nodes/edges directly
# because Gemini is better at describing what it sees than computing coordinates.

_EXTRACTION_PROMPT = """You are a floor plan reader for a hotel emergency system.

Look at this floor plan image carefully and extract:
1. All labeled areas: rooms, corridors, lobbies, stairwells, exits, fire exits
2. Which areas are physically connected (share a wall opening, door, or passageway)

Return ONLY a valid JSON object — no explanation, no markdown fences:
{
  "rooms": [
    {"name": "Lobby",       "type": "room",      "approx_position": "center-left"},
    {"name": "Corridor A",  "type": "corridor",  "approx_position": "center"},
    {"name": "Room 101",    "type": "room",      "approx_position": "top-left"},
    {"name": "Exit A",      "type": "exit",      "approx_position": "top-right"},
    {"name": "Stairwell 1", "type": "stairwell", "approx_position": "bottom-right"}
  ],
  "connections": [
    {"from": "Lobby",      "to": "Corridor A"},
    {"from": "Corridor A", "to": "Room 101"},
    {"from": "Corridor A", "to": "Exit A"},
    {"from": "Lobby",      "to": "Stairwell 1"}
  ]
}

Rules:
- Use the EXACT name as written on the floor plan (preserve capitalization)
- If no label visible, use descriptive name like "Unlabeled Room 1", "Exit North"
- type must be one of: room, corridor, exit, stairwell, lobby
- MUST include at least 2 exit-type areas (emergency exits, fire exits, stairwells count)
- Only list connections that are clearly passable (door/opening between areas)
- Return ONLY the JSON"""

# Position grid → approximate x,y coordinates
_POSITION_MAP = {
    "top-left":      (80,  80),
    "top-center":    (300, 80),
    "top-right":     (520, 80),
    "center-left":   (80,  300),
    "center":        (300, 300),
    "center-right":  (520, 300),
    "bottom-left":   (80,  520),
    "bottom-center": (300, 520),
    "bottom-right":  (520, 520),
}
_DEFAULT_POSITIONS = list(_POSITION_MAP.values())


def _slugify(name: str) -> str:
    """Convert 'Corridor A' → 'corridor_a' for use as node IDs."""
    import re
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def _normalize_label(name: str) -> str:
    """Title-case normalize: 'LOBBY' → 'Lobby', 'lobby' → 'Lobby'."""
    return " ".join(w.capitalize() for w in name.strip().split())


def _weight_for_type(edge_type: str) -> float:
    return {"stairwell": 2.0, "corridor": 1.0}.get(edge_type, 1.0)


def _build_graph_from_extraction(raw: dict) -> dict:
    """
    Convert Gemini extraction output (rooms + connections) into
    a normalized nodes + edges graph.

    Post-processing:
      - Label normalization (Lobby == LOBBY == lobby → "Lobby")
      - ID slugification  (Corridor A → corridor_a)
      - Deduplication of rooms by normalized name
      - Coordinate assignment from position grid
      - Orphan connection filtering (both ends must exist as nodes)
      - Duplicate edge removal
      - Exit guarantee (inject one if none found)
    """
    rooms = raw.get("rooms", [])
    connections = raw.get("connections", [])

    # ── Build node map ────────────────────────────────────────────────────────
    seen_labels: dict = {}      # normalized_label → node dict
    fallback_pos_idx = 0

    for room in rooms:
        raw_name = str(room.get("name", "Unknown"))
        normalized = _normalize_label(raw_name)
        node_id    = _slugify(normalized)
        node_type  = room.get("type", "room").lower()
        position   = str(room.get("approx_position", "center")).lower()

        # Deduplicate by normalized name
        if normalized in seen_labels:
            continue

        x, y = _POSITION_MAP.get(position, _DEFAULT_POSITIONS[fallback_pos_idx % len(_DEFAULT_POSITIONS)])
        fallback_pos_idx += 1

        seen_labels[normalized] = {
            "id":    node_id,
            "label": normalized,
            "x":     x,
            "y":     y,
            "type":  node_type,
        }

    # Resolve name → id mapping (case-insensitive)
    label_to_id: dict = {}
    for norm_label, node in seen_labels.items():
        label_to_id[norm_label.lower()] = node["id"]

    # ── Build edge list ───────────────────────────────────────────────────────
    seen_edges: set = set()
    edges = []

    for conn in connections:
        raw_from = _normalize_label(str(conn.get("from", "")))
        raw_to   = _normalize_label(str(conn.get("to",   "")))

        from_id = label_to_id.get(raw_from.lower())
        to_id   = label_to_id.get(raw_to.lower())

        # Skip orphan connections (node doesn't exist in our map)
        if not from_id or not to_id or from_id == to_id:
            continue

        # Dedup: treat A→B == B→A
        edge_key = tuple(sorted([from_id, to_id]))
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)

        # Determine type from connected node types
        from_node = seen_labels.get(raw_from)
        to_node   = seen_labels.get(raw_to)
        both_types = {
            (from_node or {}).get("type", ""),
            (to_node   or {}).get("type", ""),
        }
        edge_type = "stairwell" if "stairwell" in both_types else "corridor"

        edges.append({
            "from":   from_id,
            "to":     to_id,
            "weight": _weight_for_type(edge_type),
            "type":   edge_type,
        })

    nodes = list(seen_labels.values())

    # ── Exit guarantee ────────────────────────────────────────────────────────
    # IMPORTANT: only type=="exit" counts — stairwells are navigation nodes,
    # not evacuation destinations. Guest pathfinding looks for type=="exit".
    has_exit = any(n["type"] == "exit" for n in nodes)
    if not has_exit:
        # Find the corridor/lobby anchor for wiring
        anchor = next(
            (n["id"] for n in nodes if n["type"] in ("corridor", "lobby")),
            nodes[0]["id"] if nodes else None,
        )
        # Inject two exits at opposite ends (far east and near stairwell)
        exits_to_add = [
            {"id": "exit_main",       "label": "Main Exit",       "x": 600, "y": 300, "type": "exit"},
            {"id": "exit_stair_left", "label": "Stair Exit Left", "x": 50,  "y": 300, "type": "exit"},
        ]
        for ex in exits_to_add:
            nodes.append(ex)
            if anchor:
                edges.append({"from": anchor, "to": ex["id"], "weight": 1.2, "type": "corridor"})

    return {"nodes": nodes, "edges": edges}


async def generate_graph_from_image(image_path: str, floor_name: str) -> dict:
    """
    Two-step pipeline:
      1. Gemini Vision extracts rooms + connections from image
      2. Our post-processing converts to normalized nodes + edges

    Falls back to stub graph if Gemini unavailable or image unreadable.
    """
    from services.floor_service import build_stub_graph

    model = _get_model()
    if not model:
        logger.info("Gemini not configured — using stub graph")
        return build_stub_graph()

    try:
        import PIL.Image
        img = PIL.Image.open(image_path)

        # Step 1: Extraction
        response = await model.generate_content_async([_EXTRACTION_PROMPT, img])
        text = response.text.strip()

        # Strip markdown fences
        if text.startswith("```"):
            parts = text.split("```")
            text = parts[1] if len(parts) > 1 else text
            if text.startswith("json"):
                text = text[4:]

        raw = json.loads(text.strip())

        # Step 2: Post-processing
        graph = _build_graph_from_extraction(raw)

        if len(graph["nodes"]) >= 2:
            logger.info(
                f"Gemini Vision graph built: "
                f"{len(graph['nodes'])} nodes, {len(graph['edges'])} edges "
                f"for floor '{floor_name}'"
            )
            return graph

        logger.warning("Post-processing produced too few nodes — using stub")
        return build_stub_graph()

    except json.JSONDecodeError as e:
        logger.warning(f"Gemini Vision JSON parse failed: {e} — using stub")
        return build_stub_graph()
    except Exception as e:
        logger.warning(f"Gemini Vision floor analysis failed: {e} — using stub")
        return build_stub_graph()

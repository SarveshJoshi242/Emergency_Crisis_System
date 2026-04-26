# ============================================================
#  Emergency Backend · services/graph_advisor.py
#  Purpose: Auto-fix suggestions — analyzes a floor graph and
#           returns actionable recommendations for staff.
#           No DB access — pure logic.
# ============================================================

from __future__ import annotations

import logging
import math
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)

NodeList = list[dict[str, Any]]
EdgeList = list[dict[str, Any]]

# ── Tuning constants ──────────────────────────────────────────────────────────

# Nodes closer than this distance (coordinate units) are "close" → suggest edge
AUTO_EDGE_DISTANCE_THRESHOLD = 150.0

# Ideal exit placement: exits should be at least this far from floor centroid
EXIT_MIN_DISTANCE_FROM_CENTER = 100.0


# ── Internal helpers ──────────────────────────────────────────────────────────

def _distance(a: dict, b: dict) -> float:
    dx = (a.get("x") or 0) - (b.get("x") or 0)
    dy = (a.get("y") or 0) - (b.get("y") or 0)
    return math.sqrt(dx * dx + dy * dy)


def _build_adj(nodes: NodeList, edges: EdgeList) -> dict[str, set[str]]:
    adj: dict[str, set[str]] = {n["id"]: set() for n in nodes}
    for e in edges:
        f, t = e.get("from"), e.get("to")
        if f in adj and t in adj:
            adj[f].add(t)
            adj[t].add(f)
    return adj


def _connected_components(nodes: NodeList, adj: dict[str, set[str]]) -> list[set[str]]:
    visited: set[str] = set()
    components: list[set[str]] = []
    for node in nodes:
        nid = node["id"]
        if nid not in visited:
            component: set[str] = set()
            queue: deque[str] = deque([nid])
            while queue:
                cur = queue.popleft()
                if cur in visited:
                    continue
                visited.add(cur)
                component.add(cur)
                for neighbor in adj.get(cur, set()):
                    if neighbor not in visited:
                        queue.append(neighbor)
            components.append(component)
    return components


def _existing_edge_set(edges: EdgeList) -> set[tuple[str, str]]:
    result: set[tuple[str, str]] = set()
    for e in edges:
        f, t = e.get("from", ""), e.get("to", "")
        result.add((f, t))
        result.add((t, f))  # undirected
    return result


def _floor_centroid(nodes: NodeList) -> tuple[float, float]:
    if not nodes:
        return 0.0, 0.0
    cx = sum(n.get("x", 0) for n in nodes) / len(nodes)
    cy = sum(n.get("y", 0) for n in nodes) / len(nodes)
    return cx, cy


def _floor_bbox(nodes: NodeList) -> tuple[float, float, float, float]:
    """Return (min_x, min_y, max_x, max_y) bounding box."""
    xs = [n.get("x", 0) for n in nodes]
    ys = [n.get("y", 0) for n in nodes]
    return min(xs), min(ys), max(xs), max(ys)


# ── Public API ────────────────────────────────────────────────────────────────

def suggest_fixes(graph: dict[str, Any]) -> dict[str, Any]:
    """
    Analyze the graph and return actionable fix suggestions.

    Returns dict matching FixSuggestionResult:
    {
        "has_suggestions": bool,
        "suggested_edges": [...],
        "suggested_nodes": [...],
        "duplicate_node_groups": [...],
        "notes": [...],
    }
    """
    nodes: NodeList = graph.get("nodes") or []
    edges: EdgeList = graph.get("edges") or []

    suggested_edges: list[dict] = []
    suggested_nodes: list[dict] = []
    duplicate_node_groups: list[list[str]] = []
    notes: list[str] = []

    # Quick exit for empty graph
    if not nodes:
        return {
            "has_suggestions": False,
            "suggested_edges": [],
            "suggested_nodes": [],
            "duplicate_node_groups": [],
            "notes": ["Graph has no nodes yet — nothing to suggest."],
        }

    node_map: dict[str, dict] = {n["id"]: n for n in nodes}
    existing_edges = _existing_edge_set(edges)
    adj = _build_adj(nodes, edges)
    node_ids = list(node_map.keys())

    # ── 1. Duplicate node detection (by label similarity) ─────────────────
    label_groups: dict[str, list[str]] = {}
    for n in nodes:
        key = n.get("label", "").strip().lower()
        label_groups.setdefault(key, []).append(n["id"])
    for label, ids in label_groups.items():
        if len(ids) > 1:
            duplicate_node_groups.append(ids)
            notes.append(
                f"Possible duplicate nodes with label '{label}': {ids}. "
                "Consider merging them into one node."
            )

    # ── 2. Disconnected nodes → suggest connecting edges ──────────────────
    components = _connected_components(nodes, adj)
    if len(components) > 1:
        notes.append(
            f"Graph has {len(components)} disconnected sub-graphs. "
            "Suggesting bridge edges to connect them."
        )
        # Connect successive components by finding the closest pair of nodes
        for i in range(len(components) - 1):
            comp_a = list(components[i])
            comp_b = list(components[i + 1])
            best_dist = float("inf")
            best_a, best_b = comp_a[0], comp_b[0]
            for a in comp_a:
                for b in comp_b:
                    if a not in node_map or b not in node_map:
                        continue
                    d = _distance(node_map[a], node_map[b])
                    if d < best_dist:
                        best_dist = d
                        best_a, best_b = a, b

            if (best_a, best_b) not in existing_edges:
                suggested_edges.append({
                    "from_node": best_a,
                    "to_node": best_b,
                    "weight": round(best_dist / 100.0, 2) or 1.0,
                    "reason": f"Bridge between disconnected sub-graphs (distance ≈ {round(best_dist, 1)})",
                })

    # ── 3. Auto-edge generator: suggest edges for nearby nodes ────────────
    for i, id_a in enumerate(node_ids):
        for id_b in node_ids[i + 1:]:
            if (id_a, id_b) in existing_edges or (id_b, id_a) in existing_edges:
                continue
            na = node_map[id_a]
            nb = node_map[id_b]
            d = _distance(na, nb)
            if d <= AUTO_EDGE_DISTANCE_THRESHOLD and d > 0:
                suggested_edges.append({
                    "from_node": id_a,
                    "to_node": id_b,
                    "weight": round(d / 100.0, 2) or 0.5,
                    "reason": f"Nodes are close (distance ≈ {round(d, 1)} units) — likely navigable",
                })

    # ── 4. Missing exit → suggest placement ───────────────────────────────
    exit_nodes = [n for n in nodes if n.get("type") == "exit"]
    stairwell_nodes = [n for n in nodes if n.get("type") == "stairwell"]

    if not exit_nodes:
        notes.append("No exit nodes found. Suggesting exit placements at extremities.")

        # Strategy: place exits at far ends of the floor bounding box
        if nodes:
            min_x, min_y, max_x, max_y = _floor_bbox(nodes)
            cx, cy = _floor_centroid(nodes)
            mid_y = (min_y + max_y) / 2.0

            candidates = [
                {
                    "id": "suggested_exit_east",
                    "label": "Exit (East)",
                    "x": round(max_x + 30, 1),
                    "y": round(mid_y, 1),
                    "type": "exit",
                    "reason": "East extremity — far from floor center, good evacuation spread",
                },
                {
                    "id": "suggested_exit_west",
                    "label": "Exit (West)",
                    "x": round(min_x - 30, 1),
                    "y": round(mid_y, 1),
                    "type": "exit",
                    "reason": "West extremity — far from floor center, good evacuation spread",
                },
            ]

            # If stairwells exist, suggest an exit near each stairwell
            for sw in stairwell_nodes[:2]:
                candidates.append({
                    "id": f"suggested_exit_near_{sw['id']}",
                    "label": f"Exit near {sw.get('label', sw['id'])}",
                    "x": round((sw.get("x") or 0) + 40, 1),
                    "y": round(sw.get("y") or 0, 1),
                    "type": "exit",
                    "reason": f"Near stairwell '{sw['id']}' — stairwells are natural evacuation endpoints",
                })

            suggested_nodes.extend(candidates)

    # ── 5. Exit placement helper: warn if exits are clustered ─────────────
    elif len(exit_nodes) >= 2:
        cx, cy = _floor_centroid(exit_nodes)
        # If all exits are within a tight cluster, warn
        max_spread = max(_distance(a, b) for i, a in enumerate(exit_nodes) for b in exit_nodes[i + 1:])
        if max_spread < 100:
            notes.append(
                f"All {len(exit_nodes)} exits are tightly clustered (max spread ≈ {round(max_spread, 1)} units). "
                "Exits should be spread across the floor for effective evacuation."
            )

    # ── 6. Corridor connectivity: rooms with no corridor neighbour ─────────
    room_nodes = [n for n in nodes if n.get("type") == "room"]
    corridor_ids = {n["id"] for n in nodes if n.get("type") in ("corridor", "lobby")}
    if corridor_ids:
        for room in room_nodes:
            rid = room["id"]
            has_corridor_neighbour = bool(adj.get(rid, set()) & corridor_ids)
            if not has_corridor_neighbour:
                # Find the nearest corridor
                nearest_corridor_id = None
                nearest_dist = float("inf")
                for cid in corridor_ids:
                    if cid not in node_map:
                        continue
                    d = _distance(room, node_map[cid])
                    if d < nearest_dist:
                        nearest_dist = d
                        nearest_corridor_id = cid

                if nearest_corridor_id and (rid, nearest_corridor_id) not in existing_edges:
                    suggested_edges.append({
                        "from_node": rid,
                        "to_node": nearest_corridor_id,
                        "weight": round(nearest_dist / 100.0, 2) or 0.5,
                        "reason": (
                            f"Room '{rid}' has no corridor connection. "
                            f"Nearest corridor: '{nearest_corridor_id}' "
                            f"(distance ≈ {round(nearest_dist, 1)} units)"
                        ),
                    })

    # ── Deduplicate suggested edges ────────────────────────────────────────
    seen: set[tuple[str, str]] = set()
    deduped: list[dict] = []
    for se in suggested_edges:
        key = (min(se["from_node"], se["to_node"]), max(se["from_node"], se["to_node"]))
        if key not in seen and key not in {(min(a, b), max(a, b)) for a, b in existing_edges}:
            seen.add(key)
            deduped.append(se)
    suggested_edges = deduped

    has_suggestions = bool(suggested_edges or suggested_nodes or duplicate_node_groups)

    return {
        "has_suggestions": has_suggestions,
        "suggested_edges": suggested_edges,
        "suggested_nodes": suggested_nodes,
        "duplicate_node_groups": duplicate_node_groups,
        "notes": notes,
    }


# ── Graph heatmap (congestion analysis) ───────────────────────────────────────

def build_heatmap(graph: dict[str, Any]) -> dict[str, Any]:
    """
    Identify congestion hotspots and critical evacuation paths.

    Heuristic:
    - Nodes with high degree (many edges) are potential bottlenecks.
    - Nodes ON the only path to an exit are "critical" — losing them
      could strand guests.
    - Returns per-node congestion scores.
    """
    nodes: NodeList = graph.get("nodes") or []
    edges: EdgeList = graph.get("edges") or []

    if not nodes:
        return {"heatmap": [], "critical_nodes": [], "notes": ["Graph is empty."]}

    adj = _build_adj(nodes, edges)
    exit_ids = {n["id"] for n in nodes if n.get("type") == "exit"}

    heatmap = []
    critical_nodes = []

    max_degree = max((len(neighbors) for neighbors in adj.values()), default=1)

    for node in nodes:
        nid = node["id"]
        degree = len(adj.get(nid, set()))
        congestion_score = round(degree / max(max_degree, 1), 3)

        # Check if this node is a cut vertex (naively: if removing it disconnects any room from exits)
        is_critical = False
        if exit_ids and node.get("type") not in ("exit",):
            # Temporarily remove node and check reachability
            reduced_adj = {
                k: (v - {nid}) for k, v in adj.items() if k != nid
            }
            for room in nodes:
                rid = room["id"]
                if rid == nid or room.get("type") != "room":
                    continue
                # BFS to any exit without nid
                from collections import deque as dq
                visited: set[str] = set()
                queue: dq = dq([rid])
                found = False
                while queue:
                    cur = queue.popleft()
                    if cur in visited:
                        continue
                    visited.add(cur)
                    if cur in exit_ids:
                        found = True
                        break
                    for nb in reduced_adj.get(cur, set()):
                        if nb not in visited:
                            queue.append(nb)
                if not found and rid != nid:
                    is_critical = True
                    break

        if is_critical:
            critical_nodes.append(nid)

        heatmap.append({
            "node_id": nid,
            "label": node.get("label", nid),
            "type": node.get("type"),
            "degree": degree,
            "congestion_score": congestion_score,
            "is_critical_path": is_critical,
        })

    # Sort by congestion score descending
    heatmap.sort(key=lambda h: h["congestion_score"], reverse=True)

    return {
        "heatmap": heatmap,
        "critical_nodes": critical_nodes,
        "notes": [
            f"Found {len(critical_nodes)} critical bottleneck node(s). "
            "Removing these would strand guests in emergencies."
            if critical_nodes else
            "No critical single-point bottlenecks detected — good redundancy."
        ],
    }

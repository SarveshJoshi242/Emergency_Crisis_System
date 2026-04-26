# ============================================================
#  Emergency Backend · services/graph_validator.py
#  Purpose: Self-contained graph validation engine.
#           Runs ALL correctness checks on a floor graph and returns
#           a structured result. No DB access — pure logic.
# ============================================================

from __future__ import annotations

import logging
import math
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)


# ── Type aliases ──────────────────────────────────────────────────────────────

NodeList = list[dict[str, Any]]
EdgeList = list[dict[str, Any]]


# ── Internal helpers ──────────────────────────────────────────────────────────

def _adjacency(nodes: NodeList, edges: EdgeList) -> dict[str, set[str]]:
    """Build undirected adjacency set for connectivity/reachability checks."""
    adj: dict[str, set[str]] = {n["id"]: set() for n in nodes}
    for e in edges:
        f, t = e.get("from"), e.get("to")
        if f in adj and t in adj:
            adj[f].add(t)
            adj[t].add(f)  # treat as undirected for evacuation reachability
    return adj


def _bfs_reachable(start: str, adj: dict[str, set[str]]) -> set[str]:
    """Return all node IDs reachable from `start` via BFS."""
    visited: set[str] = set()
    queue: deque[str] = deque([start])
    while queue:
        node = queue.popleft()
        if node in visited:
            continue
        visited.add(node)
        for neighbor in adj.get(node, set()):
            if neighbor not in visited:
                queue.append(neighbor)
    return visited


def _has_path_to_exit(
    start: str,
    exit_ids: set[str],
    adj: dict[str, set[str]],
) -> bool:
    """BFS: return True if any exit is reachable from `start`."""
    visited: set[str] = set()
    queue: deque[str] = deque([start])
    while queue:
        node = queue.popleft()
        if node in visited:
            continue
        visited.add(node)
        if node in exit_ids:
            return True
        for neighbor in adj.get(node, set()):
            if neighbor not in visited:
                queue.append(neighbor)
    return False


# ── Public validation entry point ─────────────────────────────────────────────

ALLOWED_NODE_TYPES = {"room", "corridor", "stairwell", "lobby", "exit"}


def validate_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """
    Full graph validation.

    Returns a dict matching GraphValidationResult:
    {
        "valid": bool,
        "errors": [...],
        "warnings": [...],
        "unreachable_nodes": [...],
        "dead_end_nodes": [...],
        "stats": {...},
    }
    """
    nodes: NodeList = graph.get("nodes") or []
    edges: EdgeList = graph.get("edges") or []

    errors: list[str] = []
    warnings: list[str] = []
    unreachable_nodes: list[str] = []
    dead_end_nodes: list[str] = []

    # ── 0. Empty graph short-circuit ────────────────────────────────────────
    if not nodes:
        return {
            "valid": False,
            "errors": ["Graph has no nodes — add at least one node before validating."],
            "warnings": [],
            "unreachable_nodes": [],
            "dead_end_nodes": [],
            "stats": {"node_count": 0, "edge_count": 0, "exit_count": 0},
        }

    # ── 1. Node validation ──────────────────────────────────────────────────
    seen_ids: set[str] = set()
    duplicate_ids: list[str] = []
    invalid_type_nodes: list[str] = []

    for node in nodes:
        nid = node.get("id", "")
        ntype = node.get("type", "")

        # 1a. Duplicate IDs
        if nid in seen_ids:
            duplicate_ids.append(nid)
        seen_ids.add(nid)

        # 1b. Invalid type
        if ntype not in ALLOWED_NODE_TYPES:
            invalid_type_nodes.append(f"{nid} (type='{ntype}')")

        # 1c. Coordinate sanity
        x = node.get("x")
        y = node.get("y")
        if x is None or y is None:
            errors.append(f"Node '{nid}' is missing coordinates (x, y).")
        elif not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            errors.append(f"Node '{nid}' has non-numeric coordinates.")
        elif math.isnan(float(x)) or math.isinf(float(x)) or math.isnan(float(y)) or math.isinf(float(y)):
            errors.append(f"Node '{nid}' has non-finite coordinates (NaN or Inf).")

    if duplicate_ids:
        errors.append(
            f"Duplicate node IDs detected: {duplicate_ids}. "
            "Each node ID must be unique within the floor."
        )

    if invalid_type_nodes:
        errors.append(
            f"Nodes with invalid type: {invalid_type_nodes}. "
            f"Allowed types: {sorted(ALLOWED_NODE_TYPES)}."
        )

    # Build lookup set using only the first occurrence of each id
    all_node_ids: set[str] = seen_ids

    # ── 2. Edge validation ──────────────────────────────────────────────────
    seen_edges: set[tuple[str, str]] = set()
    duplicate_edges: list[str] = []
    orphan_edges: list[str] = []
    self_loops: list[str] = []
    zero_weight_edges: list[str] = []

    for edge in edges:
        f = edge.get("from", "")
        t = edge.get("to", "")
        w = edge.get("weight")

        # 2a. Self-loop
        if f == t:
            self_loops.append(f"({f} → {t})")
            continue

        # 2b. Orphan edges (points to non-existent node)
        if f not in all_node_ids:
            orphan_edges.append(f"Edge from='{f}' — node does not exist.")
        if t not in all_node_ids:
            orphan_edges.append(f"Edge to='{t}' — node does not exist.")

        # 2c. Duplicate edges
        canonical = (min(f, t), max(f, t))
        if canonical in seen_edges:
            duplicate_edges.append(f"({f} ↔ {t})")
        seen_edges.add(canonical)

        # 2d. Weight check
        if w is None or (isinstance(w, (int, float)) and w <= 0):
            zero_weight_edges.append(f"({f} → {t}) weight={w}")

    if self_loops:
        errors.append(f"Self-loop edges detected: {self_loops}.")
    if orphan_edges:
        errors.append(f"Edges reference non-existent nodes: {orphan_edges}.")
    if duplicate_edges:
        errors.append(f"Duplicate edges detected: {duplicate_edges}.")
    if zero_weight_edges:
        errors.append(f"Edges with invalid weight (must be > 0): {zero_weight_edges}.")

    # Build adjacency only with valid, existing nodes
    adj = _adjacency(nodes, edges)

    # ── 3. Dead-end detection ───────────────────────────────────────────────
    # Nodes with degree 0 (completely isolated — no edges at all)
    for node in nodes:
        nid = node.get("id", "")
        if not adj.get(nid):
            dead_end_nodes.append(nid)

    if dead_end_nodes:
        warnings.append(
            f"Dead-end / isolated nodes (no edges): {dead_end_nodes}. "
            "These nodes are unreachable and should be connected or removed."
        )

    # ── 4. Connectivity check (entire graph) ────────────────────────────────
    # BFS from the first node — all nodes should be reachable
    connected_nodes: set[str] = set()
    if nodes:
        start_node = nodes[0]["id"]
        connected_nodes = _bfs_reachable(start_node, adj)
        isolated_from_main = all_node_ids - connected_nodes
        if isolated_from_main:
            errors.append(
                f"Graph is NOT fully connected. "
                f"These nodes form isolated sub-graphs: {sorted(isolated_from_main)}."
            )

    # ── 5. Exit validation ──────────────────────────────────────────────────
    exit_ids = {n["id"] for n in nodes if n.get("type") == "exit"}
    exit_count = len(exit_ids)

    if exit_count == 0:
        warnings.append(
            "No exit nodes defined. "
            "At least one node with type='exit' is required for evacuation routing."
        )

    # ── 6. Reachability to exit (per room node) ─────────────────────────────
    if exit_ids:
        room_nodes = [n for n in nodes if n.get("type") == "room"]
        for node in room_nodes:
            nid = node.get("id", "")
            if not _has_path_to_exit(nid, exit_ids, adj):
                unreachable_nodes.append(nid)

        if unreachable_nodes:
            errors.append(
                f"Rooms with NO path to any exit: {unreachable_nodes}. "
                "These rooms cannot be safely evacuated."
            )

    # ── 7. Corridor reachability check ──────────────────────────────────────
    # Every room should be reachable from at least one corridor
    corridor_ids = {n["id"] for n in nodes if n.get("type") in ("corridor", "lobby")}
    if corridor_ids and nodes:
        all_reachable_from_corridors: set[str] = set()
        for cid in corridor_ids:
            all_reachable_from_corridors |= _bfs_reachable(cid, adj)

        unreachable_from_corridor = all_node_ids - all_reachable_from_corridors
        if unreachable_from_corridor:
            warnings.append(
                f"Nodes NOT reachable from any corridor/lobby: "
                f"{sorted(unreachable_from_corridor)}."
            )

    # ── Determine overall validity ──────────────────────────────────────────
    valid = len(errors) == 0

    return {
        "valid": valid,
        "errors": errors,
        "warnings": warnings,
        "unreachable_nodes": unreachable_nodes,
        "dead_end_nodes": dead_end_nodes,
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "exit_count": exit_count,
            "room_count": len([n for n in nodes if n.get("type") == "room"]),
            "corridor_count": len([n for n in nodes if n.get("type") in ("corridor", "lobby")]),
            "stairwell_count": len([n for n in nodes if n.get("type") == "stairwell"]),
            "connected": len(errors) == 0 or all("NOT fully connected" not in e for e in errors),
        },
    }

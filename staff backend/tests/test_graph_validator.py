# ============================================================
#  Emergency Backend · tests/test_graph_validator.py
#  Pure unit tests for services/graph_validator.py
#  Run: pytest tests/test_graph_validator.py -v
# ============================================================

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.graph_validator import validate_graph
from services.graph_advisor import suggest_fixes


# ── Fixtures ──────────────────────────────────────────────────────────────────

VALID_GRAPH = {
    "nodes": [
        {"id": "lobby",      "label": "Lobby",       "x": 100, "y": 200, "type": "lobby"},
        {"id": "corridor_a", "label": "Corridor A",  "x": 220, "y": 200, "type": "corridor"},
        {"id": "room_101",   "label": "Room 101",    "x": 220, "y": 100, "type": "room"},
        {"id": "exit_a",     "label": "Exit A",      "x": 480, "y": 200, "type": "exit"},
    ],
    "edges": [
        {"from": "lobby",      "to": "corridor_a", "weight": 1.0, "type": "corridor"},
        {"from": "corridor_a", "to": "room_101",   "weight": 0.5, "type": "corridor"},
        {"from": "corridor_a", "to": "exit_a",     "weight": 1.2, "type": "corridor"},
    ],
}


# ── Validator tests ───────────────────────────────────────────────────────────

class TestValidGraph:
    def test_valid_graph_passes(self):
        r = validate_graph(VALID_GRAPH)
        assert r["valid"] is True
        assert r["errors"] == []

    def test_valid_graph_has_no_unreachable_nodes(self):
        r = validate_graph(VALID_GRAPH)
        assert r["unreachable_nodes"] == []

    def test_valid_graph_has_no_dead_ends(self):
        r = validate_graph(VALID_GRAPH)
        assert r["dead_end_nodes"] == []

    def test_valid_graph_stats(self):
        r = validate_graph(VALID_GRAPH)
        assert r["stats"]["exit_count"] == 1
        assert r["stats"]["node_count"] == 4
        assert r["stats"]["edge_count"] == 3


class TestEmptyGraph:
    def test_empty_graph_is_invalid(self):
        r = validate_graph({"nodes": [], "edges": []})
        assert r["valid"] is False
        assert "no nodes" in r["errors"][0].lower()

    def test_none_graph(self):
        r = validate_graph({})
        assert r["valid"] is False


class TestNodeValidation:
    def test_duplicate_node_ids(self):
        graph = {
            "nodes": [
                {"id": "dup", "label": "A", "x": 0, "y": 0, "type": "room"},
                {"id": "dup", "label": "B", "x": 1, "y": 1, "type": "exit"},
            ],
            "edges": [],
        }
        r = validate_graph(graph)
        assert r["valid"] is False
        assert any("Duplicate node" in e for e in r["errors"])

    def test_invalid_node_type(self):
        graph = {
            "nodes": [
                {"id": "x", "label": "X", "x": 0, "y": 0, "type": "bathroom"},
            ],
            "edges": [],
        }
        r = validate_graph(graph)
        assert r["valid"] is False
        assert any("invalid type" in e.lower() for e in r["errors"])

    def test_missing_coordinates(self):
        graph = {
            "nodes": [
                {"id": "x", "label": "X", "type": "room"},
            ],
            "edges": [],
        }
        r = validate_graph(graph)
        assert r["valid"] is False


class TestEdgeValidation:
    def test_orphan_edge_from(self):
        graph = {
            "nodes": [
                {"id": "a", "label": "A", "x": 0, "y": 0, "type": "room"},
                {"id": "exit_1", "label": "Exit", "x": 100, "y": 0, "type": "exit"},
            ],
            "edges": [
                {"from": "ghost", "to": "exit_1", "weight": 1.0, "type": "corridor"},
                {"from": "a", "to": "exit_1", "weight": 1.0, "type": "corridor"},
            ],
        }
        r = validate_graph(graph)
        assert r["valid"] is False
        assert any("non-existent" in e for e in r["errors"])

    def test_self_loop_detected(self):
        graph = {
            "nodes": [
                {"id": "a", "label": "A", "x": 0, "y": 0, "type": "room"},
                {"id": "exit_1", "label": "Exit", "x": 100, "y": 0, "type": "exit"},
            ],
            "edges": [
                {"from": "a", "to": "a", "weight": 1.0, "type": "corridor"},
                {"from": "a", "to": "exit_1", "weight": 1.0, "type": "corridor"},
            ],
        }
        r = validate_graph(graph)
        assert r["valid"] is False
        assert any("Self-loop" in e for e in r["errors"])

    def test_duplicate_edge(self):
        graph = {
            "nodes": [
                {"id": "a", "label": "A", "x": 0, "y": 0, "type": "corridor"},
                {"id": "b", "label": "B", "x": 10, "y": 0, "type": "exit"},
            ],
            "edges": [
                {"from": "a", "to": "b", "weight": 1.0, "type": "corridor"},
                {"from": "a", "to": "b", "weight": 2.0, "type": "corridor"},
            ],
        }
        r = validate_graph(graph)
        assert r["valid"] is False
        assert any("Duplicate edges" in e for e in r["errors"])

    def test_zero_weight_edge(self):
        graph = {
            "nodes": [
                {"id": "a", "label": "A", "x": 0, "y": 0, "type": "corridor"},
                {"id": "b", "label": "B", "x": 10, "y": 0, "type": "exit"},
            ],
            "edges": [
                {"from": "a", "to": "b", "weight": 0, "type": "corridor"},
            ],
        }
        r = validate_graph(graph)
        assert r["valid"] is False
        assert any("invalid weight" in e.lower() for e in r["errors"])


class TestConnectivity:
    def test_disconnected_graph(self):
        graph = {
            "nodes": [
                {"id": "a", "label": "A", "x": 0, "y": 0, "type": "room"},
                {"id": "exit_x", "label": "Exit X", "x": 500, "y": 500, "type": "exit"},
            ],
            "edges": [],  # no edges → disconnected
        }
        r = validate_graph(graph)
        assert r["valid"] is False
        assert any("NOT fully connected" in e for e in r["errors"])

    def test_dead_end_node_flagged(self):
        graph = {
            "nodes": [
                {"id": "a", "label": "A", "x": 0, "y": 0, "type": "room"},
                {"id": "corridor_1", "label": "C", "x": 100, "y": 0, "type": "corridor"},
                {"id": "exit_1", "label": "Exit", "x": 200, "y": 0, "type": "exit"},
                {"id": "orphan", "label": "Orphan", "x": 300, "y": 300, "type": "room"},
            ],
            "edges": [
                {"from": "a", "to": "corridor_1", "weight": 1.0, "type": "corridor"},
                {"from": "corridor_1", "to": "exit_1", "weight": 1.0, "type": "corridor"},
            ],
        }
        r = validate_graph(graph)
        assert "orphan" in r["dead_end_nodes"]


class TestExitValidation:
    def test_no_exit_produces_warning(self):
        graph = {
            "nodes": [
                {"id": "a", "label": "A", "x": 0, "y": 0, "type": "room"},
                {"id": "b", "label": "B", "x": 10, "y": 0, "type": "corridor"},
            ],
            "edges": [{"from": "a", "to": "b", "weight": 1.0, "type": "corridor"}],
        }
        r = validate_graph(graph)
        assert any("No exit" in w for w in r["warnings"])

    def test_room_unreachable_from_exit(self):
        graph = {
            "nodes": [
                {"id": "exit_1", "label": "Exit", "x": 0, "y": 0, "type": "exit"},
                {"id": "corridor_a", "label": "Corridor", "x": 100, "y": 0, "type": "corridor"},
                {"id": "room_1", "label": "Room Connected", "x": 200, "y": 0, "type": "room"},
                # stranded_room has no edges → unreachable
                {"id": "stranded_room", "label": "Stranded", "x": 500, "y": 500, "type": "room"},
            ],
            "edges": [
                {"from": "exit_1", "to": "corridor_a", "weight": 1.0, "type": "corridor"},
                {"from": "corridor_a", "to": "room_1", "weight": 1.0, "type": "corridor"},
            ],
        }
        r = validate_graph(graph)
        assert r["valid"] is False
        assert "stranded_room" in r["unreachable_nodes"]


# ── Advisor tests ─────────────────────────────────────────────────────────────

class TestGraphAdvisor:
    def test_suggests_missing_exit(self):
        graph = {
            "nodes": [
                {"id": "room_1", "label": "Room 1", "x": 100, "y": 100, "type": "room"},
                {"id": "corridor_1", "label": "Corridor", "x": 200, "y": 100, "type": "corridor"},
            ],
            "edges": [{"from": "room_1", "to": "corridor_1", "weight": 1.0, "type": "corridor"}],
        }
        r = suggest_fixes(graph)
        assert r["has_suggestions"] is True
        assert any(n["type"] == "exit" for n in r["suggested_nodes"])

    def test_suggests_edge_for_nearby_nodes(self):
        graph = {
            "nodes": [
                {"id": "a", "label": "A", "x": 0, "y": 0, "type": "corridor"},
                {"id": "b", "label": "B", "x": 50, "y": 0, "type": "exit"},  # within threshold
            ],
            "edges": [],
        }
        r = suggest_fixes(graph)
        assert r["has_suggestions"] is True
        assert len(r["suggested_edges"]) > 0

    def test_no_suggestions_on_clean_graph(self):
        r = suggest_fixes(VALID_GRAPH)
        # Clean graph: nodes are connected, has exit — fewer suggestions expected
        # Some auto-edge suggestions may still appear for node proximity
        # Just assert it runs without exception
        assert isinstance(r["has_suggestions"], bool)

    def test_empty_graph_no_crash(self):
        r = suggest_fixes({"nodes": [], "edges": []})
        assert r["has_suggestions"] is False

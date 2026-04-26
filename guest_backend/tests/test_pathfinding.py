"""
Tests for pathfinding algorithms.

Run with: pytest tests/test_pathfinding.py -v
"""

import pytest
from app.utils.pathfinding import PathfindingEngine


class TestPathfindingEngine:
    """Tests for Dijkstra and BFS algorithms."""
    
    @pytest.fixture
    def engine(self, sample_floor_graph):
        """Create pathfinding engine with sample graph."""
        return PathfindingEngine(
            sample_floor_graph["nodes"],
            sample_floor_graph["edges"]
        )
    
    def test_dijkstra_simple_path(self, engine):
        """Test Dijkstra finds shortest path."""
        path, distance = engine.dijkstra("room_101", "exit_south")
        
        assert path is not None
        assert len(path) > 0
        assert path[0] == "room_101"
        assert path[-1] == "exit_south"
        assert distance > 0
    
    def test_dijkstra_with_blocked_nodes(self, engine):
        """Test Dijkstra avoids blocked nodes."""
        # Block direct route
        blocked = {"corridor_a"}
        path, distance = engine.dijkstra("room_101", "exit_south", blocked)
        
        # Should find alternative or no path
        if path:
            assert "corridor_a" not in path
    
    def test_bfs_simple_path(self, engine):
        """Test BFS finds path (unweighted)."""
        path, hops = engine.bfs("room_101", "exit_south")
        
        assert path is not None
        assert path[0] == "room_101"
        assert path[-1] == "exit_south"
    
    def test_no_path_exists(self, engine):
        """Test when no path exists between nodes."""
        # Create isolated node
        engine.nodes["isolated"] = {"id": "isolated", "label": "Isolated", "type": "room"}
        
        path, distance = engine.dijkstra("room_101", "isolated")
        
        assert path is None
        assert distance == 0
    
    def test_start_equals_end(self, engine):
        """Test path when start and end are same."""
        path, distance = engine.dijkstra("room_101", "room_101")
        
        assert path is not None
        assert len(path) == 1
        assert path[0] == "room_101"
        assert distance == 0
    
    def test_find_path_to_safe_exits(self, engine, sample_emergency_state):
        """Test finding path to any safe exit."""
        path, distance, exit_node = engine.find_path_to_safe_exits(
            "room_101",
            sample_emergency_state["safe_exits"]
        )
        
        assert path is not None
        assert exit_node == "exit_south"
        assert path[-1] == exit_node
    
    def test_get_possible_next_nodes(self, engine):
        """Test getting adjacent nodes."""
        neighbors = engine.get_possible_next_nodes("room_101")
        
        assert len(neighbors) > 0
        assert neighbors[0]["id"] == "corridor_a"


class TestPathfindingEdgeCases:
    """Test edge cases in pathfinding."""
    
    def test_empty_graph(self):
        """Test with empty graph."""
        engine = PathfindingEngine([], [])
        path, distance = engine.dijkstra("room_1", "room_2")
        
        assert path is None
    
    def test_single_node_graph(self):
        """Test with single node."""
        nodes = [{"id": "room_1", "label": "Room 1", "type": "room"}]
        edges = []
        engine = PathfindingEngine(nodes, edges)
        
        path, distance = engine.dijkstra("room_1", "room_1")
        assert path == ["room_1"]
    
    def test_weighted_vs_unweighted(self):
        """Test that Dijkstra respects weights."""
        nodes = [
            {"id": "a", "label": "A", "type": "room"},
            {"id": "b", "label": "B", "type": "room"},
            {"id": "c", "label": "C", "type": "room"},
            {"id": "d", "label": "D", "type": "room"},
        ]
        edges = [
            {"from": "a", "to": "b", "weight": 1},
            {"from": "b", "to": "d", "weight": 1},
            {"from": "a", "to": "c", "weight": 1},
            {"from": "c", "to": "d", "weight": 100},  # Heavy weight
        ]
        
        engine = PathfindingEngine(nodes, edges)
        path, distance = engine.dijkstra("a", "d")
        
        # Should prefer lighter path through b
        assert path == ["a", "b", "d"]

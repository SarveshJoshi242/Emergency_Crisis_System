"""
Pathfinding utilities for evacuation route computation.

Provides two algorithms:
1. Dijkstra's algorithm - for weighted shortest path (PREFERRED)
2. BFS - for unweighted shortest path (fallback)
"""
from collections import deque, defaultdict
import heapq
from typing import List, Set, Dict, Tuple, Optional


def build_graph(floor: dict) -> dict:
    """Build a floor graph from embedded floor data."""
    graph = floor.get("graph", floor)
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    adjacency: Dict[str, List[Tuple[str, float]]] = defaultdict(list)

    for edge in edges:
        from_node = edge.get("from")
        to_node = edge.get("to")
        weight = float(edge.get("weight", 1.0) or 1.0)
        if not from_node or not to_node:
            continue

        adjacency[from_node].append((to_node, weight))
        adjacency[to_node].append((from_node, weight))

    return {
        "nodes": nodes,
        "edges": edges,
        "adjacency": {node: neighbors for node, neighbors in adjacency.items()}
    }


def get_exit_nodes(floor: dict) -> List[str]:
    """Return exit node IDs defined in a floor graph."""
    graph = floor.get("graph", floor)
    return [
        node.get("id")
        for node in graph.get("nodes", [])
        if node.get("type") == "exit"
    ]


def dijkstra(
    graph: dict,
    start: str,
    targets: List[str],
    blocked_nodes: Optional[Set[str]] = None
) -> Tuple[Optional[List[str]], float, Optional[str]]:
    """Find shortest path from a start node to the nearest target exit."""
    engine = PathfindingEngine(graph.get("nodes", []), graph.get("edges", []))
    if blocked_nodes is None:
        blocked_nodes = set()

    best_path = None
    best_distance = float("inf")
    best_target = None

    for target in targets:
        path, distance = engine.dijkstra(start, target, blocked_nodes)
        if path is not None and distance < best_distance:
            best_path = path
            best_distance = distance
            best_target = target

    return best_path, best_distance, best_target


class PathfindingEngine:
    """Graph-based pathfinding engine for emergency evacuation."""
    
    def __init__(self, nodes: List[dict], edges: List[dict]):
        """
        Initialize pathfinding engine with graph.
        
        Args:
            nodes: List of node dicts with 'id', 'label', 'type'
            edges: List of edge dicts with 'from', 'to', 'weight'
        """
        self.nodes = {node['id']: node for node in nodes}
        self.graph = self._build_adjacency_list(edges)
        self.edges = edges
    
    def _build_adjacency_list(self, edges: List[dict]) -> Dict[str, List[Tuple[str, float]]]:
        """Build adjacency list from edges."""
        graph = defaultdict(list)
        for edge in edges:
            from_node = edge.get('from')
            to_node = edge.get('to')
            weight = edge.get('weight', 1.0)

            if not from_node or not to_node:
                continue

            graph[from_node].append((to_node, weight))
            graph[to_node].append((from_node, weight))

        return graph
    
    def dijkstra(
        self,
        start: str,
        end: str,
        blocked_nodes: Optional[Set[str]] = None
    ) -> Tuple[Optional[List[str]], float]:
        """
        Find shortest path using Dijkstra's algorithm.
        
        Args:
            start: Starting node ID
            end: Destination node ID
            blocked_nodes: Set of node IDs to avoid
        
        Returns:
            Tuple of (path as list of node IDs, total distance)
            Returns (None, 0) if no path exists
        """
        if blocked_nodes is None:
            blocked_nodes = set()
        
        # Validate nodes exist
        if start not in self.nodes or end not in self.nodes:
            return None, 0
        
        # If start or end is blocked, return no path
        if start in blocked_nodes or end in blocked_nodes:
            return None, 0
        
        # Initialize
        distances = {node_id: float('inf') for node_id in self.nodes}
        distances[start] = 0
        previous = {node_id: None for node_id in self.nodes}
        pq = [(0, start)]  # (distance, node)
        visited = set()
        
        while pq:
            current_dist, current = heapq.heappop(pq)
            
            if current in visited:
                continue
            
            visited.add(current)
            
            # Reached destination
            if current == end:
                path = []
                node = end
                while node is not None:
                    path.append(node)
                    node = previous[node]
                return path[::-1], distances[end]
            
            # Explore neighbors
            for neighbor, weight in self.graph.get(current, []):
                if neighbor in blocked_nodes or neighbor in visited:
                    continue
                
                new_dist = current_dist + weight
                if new_dist < distances[neighbor]:
                    distances[neighbor] = new_dist
                    previous[neighbor] = current
                    heapq.heappush(pq, (new_dist, neighbor))
        
        return None, 0
    
    def bfs(
        self,
        start: str,
        end: str,
        blocked_nodes: Optional[Set[str]] = None
    ) -> Tuple[Optional[List[str]], float]:
        """
        Find shortest path using BFS (unweighted).
        
        Args:
            start: Starting node ID
            end: Destination node ID
            blocked_nodes: Set of node IDs to avoid
        
        Returns:
            Tuple of (path as list of node IDs, hop count)
            Returns (None, 0) if no path exists
        """
        if blocked_nodes is None:
            blocked_nodes = set()
        
        # Validate
        if start not in self.nodes or end not in self.nodes:
            return None, 0
        
        if start in blocked_nodes or end in blocked_nodes:
            return None, 0
        
        # BFS
        queue = deque([start])
        visited = {start}
        parent = {start: None}
        
        while queue:
            current = queue.popleft()
            
            if current == end:
                path = []
                node = end
                while node is not None:
                    path.append(node)
                    node = parent[node]
                return path[::-1], float(len(path) - 1)
            
            for neighbor, _ in self.graph.get(current, []):
                if neighbor not in visited and neighbor not in blocked_nodes:
                    visited.add(neighbor)
                    parent[neighbor] = current
                    queue.append(neighbor)
        
        return None, 0
    
    def find_path_to_safe_exits(
        self,
        start: str,
        safe_exits: List[str],
        blocked_nodes: Optional[Set[str]] = None,
        algorithm: str = "dijkstra"
    ) -> Tuple[Optional[List[str]], float, Optional[str]]:
        """
        Find shortest path to any of the safe exits.
        
        Args:
            start: Starting node ID
            safe_exits: List of safe exit node IDs
            blocked_nodes: Set of node IDs to avoid
            algorithm: "dijkstra" or "bfs"
        
        Returns:
            Tuple of (path, distance, destination_exit)
        """
        best_path = None
        best_distance = float('inf')
        best_exit = None
        
        pathfind_func = self.dijkstra if algorithm == "dijkstra" else self.bfs
        
        for exit_node in safe_exits:
            path, distance = pathfind_func(start, exit_node, blocked_nodes)
            if path and distance < best_distance:
                best_path = path
                best_distance = distance
                best_exit = exit_node
        
        return best_path, best_distance, best_exit
    
    def get_possible_next_nodes(self, current: str) -> List[dict]:
        """
        Get list of possible next nodes from current position.
        Useful for UI node selection.
        """
        if current not in self.graph:
            return []
        
        result = []
        for neighbor, _ in self.graph.get(current, []):
            if neighbor in self.nodes:
                result.append(self.nodes[neighbor])
        
        return result


def create_pathfinding_engine(floor_graph: dict) -> PathfindingEngine:
    """Factory function to create PathfindingEngine from floor graph."""
    return PathfindingEngine(floor_graph.get('nodes', []), floor_graph.get('edges', []))

"""
Testing configuration and fixtures for the guest backend.

To run tests:
    pytest tests/
    pytest tests/ -v
    pytest tests/test_pathfinding.py -v
"""

import pytest
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient as MotorAsyncClient
from app.core.config import settings


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def mock_db():
    """
    Fixture providing a mock database for testing.
    
    In production, use mongomock or testcontainers.
    """
    # For development, you can use in-memory MongoDB with mongomock
    # or a real test MongoDB instance
    pass


@pytest.fixture
def sample_floor_graph():
    """Sample floor graph for testing."""
    return {
        "floor_id": "floor_1",
        "nodes": [
            {"id": "room_101", "label": "Room 101", "type": "room"},
            {"id": "room_102", "label": "Room 102", "type": "room"},
            {"id": "corridor_a", "label": "Corridor A", "type": "corridor"},
            {"id": "stairs_1", "label": "Stairs", "type": "stairs"},
            {"id": "exit_south", "label": "South Exit", "type": "exit"},
        ],
        "edges": [
            {"from": "room_101", "to": "corridor_a", "weight": 5},
            {"from": "room_102", "to": "corridor_a", "weight": 3},
            {"from": "corridor_a", "to": "stairs_1", "weight": 10},
            {"from": "stairs_1", "to": "exit_south", "weight": 8},
        ]
    }


@pytest.fixture
def sample_emergency_state():
    """Sample emergency state for testing."""
    return {
        "is_active": True,
        "emergency_type": "fire",
        "affected_floors": ["floor_1"],
        "blocked_nodes": ["room_102"],
        "safe_exits": ["exit_south"]
    }

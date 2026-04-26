# ============================================================
#  tests/conftest.py
#  Shared fixtures and mock helpers for the entire test suite.
# ============================================================

import pytest
import pytest_asyncio
from bson import ObjectId
from unittest.mock import AsyncMock, MagicMock, patch


# ── Async cursor mock (for Motor's `async for doc in col.find(...)`) ──────────

class AsyncCursorMock:
    """Mimics a Motor AsyncCursor with optional pre-loaded documents."""

    def __init__(self, items=None):
        self._items = list(items or [])
        self._idx   = 0

    def sort(self, *args, **kwargs):
        return self   # fluent — Motor cursor supports .sort() chaining

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self._items):
            raise StopAsyncIteration
        doc = self._items[self._idx]
        self._idx += 1
        return doc


# ── Collection mock factory ───────────────────────────────────────────────────

def make_mock_col(find_one_result=None, find_items=None, insert_id=None):
    """Create a mock Motor collection with sensible async defaults."""
    col = MagicMock()
    col.insert_one  = AsyncMock(
        return_value=MagicMock(inserted_id=insert_id or ObjectId())
    )
    col.find_one    = AsyncMock(return_value=find_one_result)
    col.update_one  = AsyncMock(
        return_value=MagicMock(modified_count=1, matched_count=1)
    )
    col.create_index = AsyncMock()
    col.find         = MagicMock(
        side_effect=lambda *a, **kw: AsyncCursorMock(find_items or [])
    )
    return col


# ── Auto-reset danger state between every test ────────────────────────────────

@pytest.fixture(autouse=True)
def reset_danger_states():
    """Isolate in-memory state — prevent bleed between tests."""
    from services import danger_tracker
    danger_tracker._danger_states.clear()
    yield
    danger_tracker._danger_states.clear()


# ── HTTP test client ──────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client():
    """
    Async HTTP test client with all database and Gemini calls mocked.

    Returns (AsyncClient, mock_col) so individual tests can inspect DB calls.

    Patches applied:
    - database.get_db          → mock database object (for ensure_indexes)
    - services.*.get_collection → same mock collection
    - services.gemini_service._get_model → None (graceful fallback path)
    - services.websocket_manager.manager.broadcast → AsyncMock (capture WS)
    """
    from httpx import AsyncClient, ASGITransport

    mock_col = make_mock_col()
    mock_db  = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_col)

    # Patch every import site for get_collection so service functions receive mock
    col_patches = {
        "database.get_db":                        mock_db,
        "services.alert_service.get_collection":  mock_col,
        "services.fire_service.get_collection":   mock_col,
        "services.task_service.get_collection":   mock_col,
        "services.staff_service.get_collection":  mock_col,
        "services.danger_tracker.get_collection": mock_col,
        "services.floor_service.get_collection":  mock_col,
    }

    with patch("database.get_db", return_value=mock_db), \
         patch("services.alert_service.get_collection",  return_value=mock_col), \
         patch("services.fire_service.get_collection",   return_value=mock_col), \
         patch("services.task_service.get_collection",   return_value=mock_col), \
         patch("services.staff_service.get_collection",  return_value=mock_col), \
         patch("services.danger_tracker.get_collection", return_value=mock_col), \
         patch("services.floor_service.get_collection",  return_value=mock_col), \
         patch("services.gemini_service._get_model",     return_value=None):

        from main import app
        async with AsyncClient(transport=ASGITransport(app=app),
                               base_url="http://test") as c:
            yield c, mock_col

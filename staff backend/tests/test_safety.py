# ============================================================
#  tests/test_safety.py
#
#  Tests 10 (spec):
#    10. Restart safety — cleared state = no immediate false trigger
#    +   get_all_states() — debug snapshot includes danger_zones
#    +   source_room backward compat — derived from first zone
#    +   Zone-less evacuation message — no crashes when zones={}
# ============================================================

import time
import pytest
from unittest.mock import AsyncMock, patch

from services.danger_tracker import (
    process_danger_event,
    get_all_states,
    _danger_states,
)
from config import settings

FLOOR = "safety_test_floor"
TS    = "2026-04-11T14:00:00Z"


# ── TEST 10: Restart safety ───────────────────────────────────────────────────

class TestRestartSafety:

    async def test_cleared_state_does_not_immediately_trigger(self):
        """
        Server restart scenario:
        1. Build up 6 seconds of sustained danger
        2. Clear state (simulates restart / pod replacement)
        3. First event after restart must NOT trigger action
        """
        with patch("services.danger_tracker._persist_event",  new_callable=AsyncMock), \
             patch("services.danger_tracker._notify_staff",   new_callable=AsyncMock) as mock_n:

            # Build sustained state
            await process_danger_event(FLOOR, "medium", TS, "room_101")
            state = _danger_states[FLOOR]
            state.started_at = time.monotonic() - 6.0   # simulated 6s

            # Simulate server restart — in-memory state cleared
            _danger_states.clear()

            # First post-restart event — timer starts fresh
            await process_danger_event(FLOOR, "medium", TS, "room_101")
            mock_n.assert_not_awaited()   # NO false positive ✓

    async def test_state_restarted_requires_full_5s_again(self):
        """After restart, the full 5s window must elapse before any action."""
        with patch("services.danger_tracker._persist_event",  new_callable=AsyncMock), \
             patch("services.danger_tracker._notify_staff",   new_callable=AsyncMock) as mock_n:

            _danger_states.clear()
            await process_danger_event(FLOOR, "medium", TS)
            # 4 seconds — still not enough post-restart
            state = _danger_states[FLOOR]
            state.started_at = time.monotonic() - (settings.DANGER_SUSTAIN_SECONDS - 1)
            state.last_seen  = time.monotonic()
            await process_danger_event(FLOOR, "medium", TS)
            mock_n.assert_not_awaited()


# ── get_all_states() debug snapshot ──────────────────────────────────────────

class TestDebugSnapshot:

    async def test_snapshot_contains_active_floor(self):
        with patch("services.danger_tracker._persist_event", new_callable=AsyncMock):
            await process_danger_event(FLOOR, "high", TS, "room_101")
            snapshot = get_all_states()
        assert FLOOR in snapshot

    async def test_snapshot_includes_danger_zones(self):
        with patch("services.danger_tracker._persist_event", new_callable=AsyncMock):
            await process_danger_event(FLOOR, "medium", TS, "room_101")
            await process_danger_event(FLOOR, "medium", TS, "room_202")
            snapshot = get_all_states()
        zones = snapshot[FLOOR]["danger_zones"]
        assert "room_101" in zones
        assert "room_202" in zones

    async def test_snapshot_includes_source_room_backward_compat(self):
        """source_room in snapshot must be the first sorted zone."""
        with patch("services.danger_tracker._persist_event", new_callable=AsyncMock):
            await process_danger_event(FLOOR, "medium", TS, "room_202")
            await process_danger_event(FLOOR, "medium", TS, "room_101")
            snapshot = get_all_states()
        # source_room = sorted(danger_zones)[0] = "room_101" (alphabetical)
        assert snapshot[FLOOR]["source_room"] == "room_101"

    async def test_snapshot_empty_when_no_active_danger(self):
        # No events — empty dict
        assert get_all_states() == {}

    async def test_low_event_removes_floor_from_snapshot(self):
        with patch("services.danger_tracker._persist_event", new_callable=AsyncMock):
            await process_danger_event(FLOOR, "high",   TS, "room_101")
            assert FLOOR in get_all_states()
            await process_danger_event(FLOOR, "low",    TS)
            assert FLOOR not in get_all_states()


# ── source_room backward compat ───────────────────────────────────────────────

class TestSourceRoomBackwardCompat:

    async def test_source_room_derived_from_sorted_zones(self):
        """source_room must be deterministic (first alphabetically)."""
        with patch("services.danger_tracker._persist_event", new_callable=AsyncMock):
            await process_danger_event(FLOOR, "medium", TS, "zone_c")
            await process_danger_event(FLOOR, "medium", TS, "zone_a")
            await process_danger_event(FLOOR, "medium", TS, "zone_b")
            snapshot = get_all_states()
        assert snapshot[FLOOR]["source_room"] == "zone_a"

    async def test_source_room_none_when_no_zone_events(self):
        """Floor-level events with no room_id → source_room is None."""
        with patch("services.danger_tracker._persist_event", new_callable=AsyncMock):
            await process_danger_event(FLOOR, "medium", TS)   # no room_id
            snapshot = get_all_states()
        assert snapshot[FLOOR]["source_room"] is None


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:

    async def test_evacuation_message_safe_without_zones(self):
        """
        _trigger_evacuation must not crash when danger_zones is empty
        (floor-level event, no room_id ever given).
        """
        from services.danger_tracker import _trigger_evacuation
        with patch("services.fire_service.handle_fire_input",
                   new_callable=AsyncMock) as mock_fire:
            await _trigger_evacuation(FLOOR, "high", set())   # empty zones
            mock_fire.assert_awaited_once()
            payload = mock_fire.call_args[0][0]
            assert payload["danger_zones"] == []
            assert payload["source_room"]  is None

    async def test_notify_safe_without_zones(self):
        """_notify_staff must not crash when danger_zones is empty."""
        with patch("services.alert_service.create_auto_alert",
                   new_callable=AsyncMock, return_value=None):
            from services.danger_tracker import _notify_staff
            # Should not raise
            await _notify_staff(FLOOR, set())

    async def test_multiple_floors_tracked_independently(self):
        """Two floors must have completely independent states."""
        with patch("services.danger_tracker._persist_event",  new_callable=AsyncMock), \
             patch("services.danger_tracker._notify_staff",   new_callable=AsyncMock) as mock_n:
            await process_danger_event("floor_A", "medium", TS, "room_101")
            await process_danger_event("floor_B", "medium", TS, "room_202")

            # Fast forward only floor_A
            state_a = _danger_states["floor_A"]
            state_a.started_at = time.monotonic() - (settings.DANGER_SUSTAIN_SECONDS + 1)
            state_a.last_seen  = time.monotonic()

            await process_danger_event("floor_A", "medium", TS, "room_101")

            # floor_A triggered, floor_B must NOT have triggered
            assert mock_n.await_count == 1
            notified_floor = mock_n.call_args[0][0]
            assert notified_floor == "floor_A"
            assert not _danger_states["floor_B"].notified

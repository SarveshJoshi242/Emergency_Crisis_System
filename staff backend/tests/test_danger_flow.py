# ============================================================
#  tests/test_danger_flow.py
#
#  Unit tests for services/danger_tracker.py.
#  Directly calls process_danger_event() — no HTTP layer.
#  DB is mocked via _persist_event patch.
#  Time is controlled by mutating state.started_at directly.
#
#  Tests covered (per spec):
#    2.  Noise filtering      — < 5s = no action
#    3.  Medium alert         — ≥ 5s = _notify_staff called
#    4.  High evacuation      — ≥ 5s = _trigger_evacuation called
#    5.  Multiple zones       — zones accumulate; all appear in notification
#    6.  Zone cleanup         — stale zones are pruned
#    7.  Max zone limit       — capped at MAX_ZONES, most-recent kept
#    +   Level change         — resets timer, preserves zones
#    +   Low event            — resets floor state
#    +   No double fire       — notified / evacuated flags prevent re-trigger
# ============================================================

import time
import pytest
from unittest.mock import AsyncMock, patch

from services.danger_tracker import (
    process_danger_event,
    _danger_states,
    ZONE_STALE_SECONDS,
    MAX_ZONES,
)
from config import settings

FLOOR     = "unit_test_floor"
TS        = "2026-04-11T14:00:00Z"
THRESHOLD = settings.DANGER_SUSTAIN_SECONDS   # 5 seconds


def _fast_forward(floor_id: str, seconds: float) -> None:
    """Simulate `seconds` of elapsed time by rewinding state.started_at."""
    state = _danger_states[floor_id]
    now   = time.monotonic()
    state.started_at = now - seconds
    state.last_seen  = now - 0.05   # just updated (not stale)


# ── TEST 2: Noise filtering ───────────────────────────────────────────────────

class TestNoiseFiltering:

    async def test_single_event_does_not_notify(self):
        with patch("services.danger_tracker._persist_event",  new_callable=AsyncMock), \
             patch("services.danger_tracker._notify_staff",   new_callable=AsyncMock) as mock_n, \
             patch("services.danger_tracker._trigger_evacuation", new_callable=AsyncMock) as mock_e:
            await process_danger_event(FLOOR, "medium", TS, "room_101")
            mock_n.assert_not_awaited()
            mock_e.assert_not_awaited()

    async def test_below_threshold_no_notification(self):
        """4.9 seconds of sustained medium → no action."""
        with patch("services.danger_tracker._persist_event",  new_callable=AsyncMock), \
             patch("services.danger_tracker._notify_staff",   new_callable=AsyncMock) as mock_n:
            await process_danger_event(FLOOR, "medium", TS, "room_101")
            _fast_forward(FLOOR, THRESHOLD - 0.1)   # 4.9s — just below
            await process_danger_event(FLOOR, "medium", TS, "room_101")
            mock_n.assert_not_awaited()

    async def test_below_threshold_state_exists_but_no_action(self):
        with patch("services.danger_tracker._persist_event", new_callable=AsyncMock):
            await process_danger_event(FLOOR, "high", TS)
            assert FLOOR in _danger_states
            assert not _danger_states[FLOOR].evacuated


# ── TEST 3: Medium alert after 5s ─────────────────────────────────────────────

class TestMediumAlert:

    async def test_medium_notifies_after_threshold(self):
        with patch("services.danger_tracker._persist_event",  new_callable=AsyncMock), \
             patch("services.danger_tracker._notify_staff",   new_callable=AsyncMock) as mock_n:
            await process_danger_event(FLOOR, "medium", TS, "room_101")
            _fast_forward(FLOOR, THRESHOLD + 1.0)    # 6 seconds
            await process_danger_event(FLOOR, "medium", TS, "room_101")
            mock_n.assert_awaited_once()

    async def test_medium_notify_receives_correct_floor(self):
        with patch("services.danger_tracker._persist_event",  new_callable=AsyncMock), \
             patch("services.danger_tracker._notify_staff",   new_callable=AsyncMock) as mock_n:
            await process_danger_event(FLOOR, "medium", TS, "room_101")
            _fast_forward(FLOOR, THRESHOLD + 1.0)
            await process_danger_event(FLOOR, "medium", TS, "room_101")
            floor_arg = mock_n.call_args[0][0]
            assert floor_arg == FLOOR

    async def test_medium_not_double_notified(self):
        """notified flag prevents re-triggering on subsequent events."""
        with patch("services.danger_tracker._persist_event",  new_callable=AsyncMock), \
             patch("services.danger_tracker._notify_staff",   new_callable=AsyncMock) as mock_n:
            await process_danger_event(FLOOR, "medium", TS)
            _fast_forward(FLOOR, THRESHOLD + 1.0)
            await process_danger_event(FLOOR, "medium", TS)   # triggers ✓
            await process_danger_event(FLOOR, "medium", TS)   # already notified
            await process_danger_event(FLOOR, "medium", TS)   # already notified
            assert mock_n.await_count == 1


# ── TEST 4: High / Critical evacuation ───────────────────────────────────────

class TestEvacuation:

    async def test_high_triggers_evacuation(self):
        with patch("services.danger_tracker._persist_event",       new_callable=AsyncMock), \
             patch("services.danger_tracker._trigger_evacuation",   new_callable=AsyncMock) as mock_e:
            await process_danger_event(FLOOR, "high", TS, "room_101")
            _fast_forward(FLOOR, THRESHOLD + 1.0)
            await process_danger_event(FLOOR, "high", TS, "room_101")
            mock_e.assert_awaited_once()

    async def test_critical_triggers_evacuation(self):
        with patch("services.danger_tracker._persist_event",       new_callable=AsyncMock), \
             patch("services.danger_tracker._trigger_evacuation",   new_callable=AsyncMock) as mock_e:
            await process_danger_event(FLOOR, "critical", TS)
            _fast_forward(FLOOR, THRESHOLD + 1.0)
            await process_danger_event(FLOOR, "critical", TS)
            mock_e.assert_awaited_once()

    async def test_evacuation_receives_correct_level(self):
        with patch("services.danger_tracker._persist_event",       new_callable=AsyncMock), \
             patch("services.danger_tracker._trigger_evacuation",   new_callable=AsyncMock) as mock_e:
            await process_danger_event(FLOOR, "high", TS, "room_101")
            _fast_forward(FLOOR, THRESHOLD + 1.0)
            await process_danger_event(FLOOR, "high", TS, "room_101")
            level_arg = mock_e.call_args[0][1]
            assert level_arg == "high"

    async def test_evacuation_not_double_triggered(self):
        with patch("services.danger_tracker._persist_event",       new_callable=AsyncMock), \
             patch("services.danger_tracker._trigger_evacuation",   new_callable=AsyncMock) as mock_e:
            await process_danger_event(FLOOR, "high", TS)
            _fast_forward(FLOOR, THRESHOLD + 1.0)
            await process_danger_event(FLOOR, "high", TS)
            await process_danger_event(FLOOR, "high", TS)
            assert mock_e.await_count == 1


# ── TEST 5: Multiple zones ────────────────────────────────────────────────────

class TestMultipleZones:

    async def test_zones_accumulate_in_state(self):
        with patch("services.danger_tracker._persist_event", new_callable=AsyncMock):
            await process_danger_event(FLOOR, "medium", TS, "room_101")
            await process_danger_event(FLOOR, "medium", TS, "room_202")
            await process_danger_event(FLOOR, "medium", TS, "room_303")
            state = _danger_states[FLOOR]
            assert {"room_101", "room_202", "room_303"}.issubset(state.danger_zones)

    async def test_both_zones_passed_to_notify_staff(self):
        """Spec: after ≥ 5s, all active zones appear in notification."""
        with patch("services.danger_tracker._persist_event",  new_callable=AsyncMock), \
             patch("services.danger_tracker._notify_staff",   new_callable=AsyncMock) as mock_n:
            await process_danger_event(FLOOR, "medium", TS, "room_101")
            await process_danger_event(FLOOR, "medium", TS, "room_202")
            _fast_forward(FLOOR, THRESHOLD + 1.0)
            await process_danger_event(FLOOR, "medium", TS, "room_303")
            mock_n.assert_awaited_once()
            zones_arg: set = mock_n.call_args[0][1]
            assert "room_101" in zones_arg
            assert "room_202" in zones_arg
            assert "room_303" in zones_arg

    async def test_both_zones_passed_to_evacuation(self):
        with patch("services.danger_tracker._persist_event",       new_callable=AsyncMock), \
             patch("services.danger_tracker._trigger_evacuation",   new_callable=AsyncMock) as mock_e:
            await process_danger_event(FLOOR, "high", TS, "room_101")
            await process_danger_event(FLOOR, "high", TS, "room_202")
            _fast_forward(FLOOR, THRESHOLD + 1.0)
            await process_danger_event(FLOOR, "high", TS, "room_101")
            mock_e.assert_awaited_once()
            zones_arg: set = mock_e.call_args[0][2]
            assert "room_101" in zones_arg
            assert "room_202" in zones_arg

    async def test_no_room_event_does_not_clear_zones(self):
        """Room-less events should NOT wipe accumulated zones."""
        with patch("services.danger_tracker._persist_event", new_callable=AsyncMock):
            await process_danger_event(FLOOR, "medium", TS, "room_101")
            await process_danger_event(FLOOR, "medium", TS)   # no room_id
            state = _danger_states[FLOOR]
            assert "room_101" in state.danger_zones


# ── TEST 6: Zone staleness cleanup ───────────────────────────────────────────

class TestZoneStaleness:

    async def test_stale_zone_removed_on_next_event(self):
        """A zone inactive for > ZONE_STALE_SECONDS is pruned."""
        with patch("services.danger_tracker._persist_event", new_callable=AsyncMock):
            await process_danger_event(FLOOR, "medium", TS, "room_101")
            # Manually make room_101 stale
            state = _danger_states[FLOOR]
            state.zone_last_seen["room_101"] = time.monotonic() - (ZONE_STALE_SECONDS + 5)
            # New event with a fresh room triggers cleanup
            await process_danger_event(FLOOR, "medium", TS, "room_202")
            state = _danger_states[FLOOR]
            assert "room_101" not in state.danger_zones, "Stale zone was not pruned"
            assert "room_202" in state.danger_zones

    async def test_fresh_zone_not_pruned(self):
        with patch("services.danger_tracker._persist_event", new_callable=AsyncMock):
            await process_danger_event(FLOOR, "medium", TS, "room_101")
            await process_danger_event(FLOOR, "medium", TS, "room_202")   # fresh
            state = _danger_states[FLOOR]
            assert "room_101" in state.danger_zones   # still active


# ── TEST 7: Max zone limit ────────────────────────────────────────────────────

class TestMaxZoneLimit:

    async def test_zone_count_capped_at_max(self):
        """Adding MAX_ZONES + 3 rooms must not exceed MAX_ZONES in state."""
        with patch("services.danger_tracker._persist_event", new_callable=AsyncMock):
            for i in range(MAX_ZONES + 3):
                await process_danger_event(FLOOR, "medium", TS, f"room_{i:03d}")
            state = _danger_states[FLOOR]
            assert len(state.danger_zones) <= MAX_ZONES

    async def test_zone_cap_keeps_most_recent(self):
        """After capping, the most recently active zones must be retained.
        We insert deliberate sub-millisecond gaps so zone_last_seen ordering
        is strictly monotone and the cap keeps the truly latest rooms."""
        import asyncio
        with patch("services.danger_tracker._persist_event", new_callable=AsyncMock):
            for i in range(MAX_ZONES + 2):
                await process_danger_event(FLOOR, "medium", TS, f"room_{i:03d}")
                await asyncio.sleep(0.001)   # ensure strictly increasing timestamps
            state = _danger_states[FLOOR]
            # The last TWO rooms added must stay (most recent after the cap)
            second_last = f"room_{(MAX_ZONES):03d}"
            last        = f"room_{(MAX_ZONES + 1):03d}"
            assert last in state.danger_zones, (
                f"{last} (most recent) should be retained; got {state.danger_zones}"
            )
            assert second_last in state.danger_zones, (
                f"{second_last} should be retained; got {state.danger_zones}"
            )


# ── Level change behaviour ────────────────────────────────────────────────────

class TestLevelChange:

    async def test_level_change_resets_timer(self):
        """Escalation from medium → high must reset the 5s timer."""
        with patch("services.danger_tracker._persist_event",       new_callable=AsyncMock), \
             patch("services.danger_tracker._trigger_evacuation",   new_callable=AsyncMock) as mock_e:
            await process_danger_event(FLOOR, "medium", TS)
            _fast_forward(FLOOR, THRESHOLD + 1.0)   # would have triggered medium
            # Escalate — timer resets
            await process_danger_event(FLOOR, "high", TS)
            # Not enough time yet for new high level
            assert not _danger_states[FLOOR].evacuated
            mock_e.assert_not_awaited()

    async def test_level_change_preserves_existing_zones(self):
        """Zones from the previous level must survive a level change."""
        with patch("services.danger_tracker._persist_event", new_callable=AsyncMock):
            await process_danger_event(FLOOR, "medium", TS, "room_101")
            await process_danger_event(FLOOR, "medium", TS, "room_202")
            # Escalate to high with a new room
            await process_danger_event(FLOOR, "high",   TS, "room_303")
            state = _danger_states[FLOOR]
            assert state.level == "high"
            assert "room_101" in state.danger_zones
            assert "room_202" in state.danger_zones
            assert "room_303" in state.danger_zones

    async def test_low_level_resets_state_completely(self):
        with patch("services.danger_tracker._persist_event", new_callable=AsyncMock):
            await process_danger_event(FLOOR, "high", TS, "room_101")
            assert FLOOR in _danger_states
            await process_danger_event(FLOOR, "low",  TS)
            assert FLOOR not in _danger_states


# ── Stale state reset ─────────────────────────────────────────────────────────

class TestStaleStateReset:

    async def test_stale_gap_resets_timer(self):
        """If no event for > DANGER_STALE_SECONDS, timer resets on next event."""
        from config import settings as cfg
        with patch("services.danger_tracker._persist_event",  new_callable=AsyncMock), \
             patch("services.danger_tracker._notify_staff",   new_callable=AsyncMock) as mock_n:
            await process_danger_event(FLOOR, "medium", TS, "room_101")
            # Simulate a stale gap — both started_at and last_seen are old
            state = _danger_states[FLOOR]
            old_time = time.monotonic() - (cfg.DANGER_STALE_SECONDS + 10)
            state.started_at = old_time
            state.last_seen  = old_time   # ← stale!
            # Next event sees stale → resets timer → no notification yet
            await process_danger_event(FLOOR, "medium", TS, "room_202")
            mock_n.assert_not_awaited()

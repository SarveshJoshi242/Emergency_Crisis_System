# ============================================================
#  Emergency Backend · services/danger_tracker.py  (v3 — multi-zone)
#  Purpose: Floor-level danger validation with multi-zone tracking
#
#  KEY DESIGN DECISIONS (v3):
#  ──────────────────────────
#  • State Key     : floor_id only — one DangerState per floor.
#  • danger_zones  : Set[str] inside the state — many rooms can be
#    tracked simultaneously per floor.
#  • zone_last_seen: Dict[str, float] — per-zone staleness tracking.
#  • ZONE_STALE_SECONDS: zones inactive for this long are pruned.
#  • MAX_ZONES: cap prevents unbounded growth under high event volume.
#  • source_room (backward compat): derived as first sorted zone.
#  • scope: always "floor" — rooms are context, not separate states.
# ============================================================

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from datetime import datetime, timezone

from config import settings
from database import get_collection

logger = logging.getLogger(__name__)

EVACUATION_LEVELS  = {"high", "critical"}
ZONE_STALE_SECONDS = 30   # seconds of silence before a zone is dropped
MAX_ZONES          = 5    # maximum simultaneous danger zones per floor


# ── State dataclass ───────────────────────────────────────────────────────────

@dataclass
class DangerState:
    """Per-floor danger state with multi-zone context tracking."""
    level: str
    started_at: float
    last_seen: float
    danger_zones: Set[str]             = field(default_factory=set)
    zone_last_seen: Dict[str, float]   = field(default_factory=dict)
    notified: bool                     = False
    evacuated: bool                    = False


# Global in-memory registry — one state per floor
_danger_states: Dict[str, DangerState] = {}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _reset_floor(floor_id: str) -> None:
    _danger_states.pop(floor_id, None)
    logger.debug(f"Danger state cleared | floor={floor_id}")


def _make_state(level: str, now: float, room_id: Optional[str]) -> DangerState:
    """Create a fresh DangerState with zero or one initial zone."""
    zones: Set[str] = set()
    zone_times: Dict[str, float] = {}
    if room_id:
        zones.add(room_id)
        zone_times[room_id] = now
    return DangerState(
        level=level,
        started_at=now,
        last_seen=now,
        danger_zones=zones,
        zone_last_seen=zone_times,
    )


def _update_zones(state: DangerState, room_id: Optional[str], now: float) -> None:
    """Add room, prune stale zones, enforce MAX_ZONES cap."""
    if room_id:
        state.danger_zones.add(room_id)
        state.zone_last_seen[room_id] = now

    # ── Prune stale zones ─────────────────────────────────────────────────────
    stale_cutoff = now - ZONE_STALE_SECONDS
    stale = [z for z, t in state.zone_last_seen.items() if t < stale_cutoff]
    for z in stale:
        state.danger_zones.discard(z)
        state.zone_last_seen.pop(z, None)
        logger.debug(f"Stale zone pruned: {z} | floor={state.level}")

    # ── Enforce cap: keep most recently seen zones ────────────────────────────
    if len(state.danger_zones) > MAX_ZONES:
        sorted_by_recency = sorted(
            state.zone_last_seen.items(), key=lambda x: x[1], reverse=True
        )
        keep = {z for z, _ in sorted_by_recency[:MAX_ZONES]}
        removed = state.danger_zones - keep
        for z in removed:
            state.danger_zones.discard(z)
            state.zone_last_seen.pop(z, None)
        logger.debug(f"Zone cap ({MAX_ZONES}) enforced — dropped: {removed}")


def _source_room(danger_zones: Set[str]) -> Optional[str]:
    """Backward-compat: derive a single source_room from the zone set."""
    return sorted(danger_zones)[0] if danger_zones else None


# ── Public entry point ────────────────────────────────────────────────────────

async def process_danger_event(
    floor_id: str,
    danger_level: str,
    timestamp: str,
    room_id: Optional[str] = None,
) -> None:
    """
    State machine for a single AI detection event.

    Behaviour summary
    ─────────────────
    LOW          → reset floor state completely
    No state     → start timer; add room to zones
    Stale (>30s) → reset timer; add room to zones
    Level change → reset timer; preserve old zones + add new room
    Same level   → keep timer; add room; prune stale zones; check duration

    duration < 5s                   → ignore (noise)
    duration ≥ 5s + medium          → notify staff once
    duration ≥ 5s + high/critical   → trigger evacuation once
    """
    now = time.monotonic()
    await _persist_event(floor_id, room_id, danger_level, timestamp)

    logger.info(
        f"AI detection | floor={floor_id} room={room_id or 'N/A'} "
        f"level={danger_level}"
    )

    # ── LOW → reset ───────────────────────────────────────────────────────────
    if danger_level == "low":
        if floor_id in _danger_states:
            logger.info(f"Level LOW — clearing state | floor={floor_id}")
            _reset_floor(floor_id)
        return

    existing = _danger_states.get(floor_id)

    # ── No state → start fresh ────────────────────────────────────────────────
    if existing is None:
        _danger_states[floor_id] = _make_state(danger_level, now, room_id)
        logger.info(
            f"Timer started | floor={floor_id} level={danger_level} "
            f"zones={[room_id] if room_id else []}"
        )
        return

    # ── Stale → reset ─────────────────────────────────────────────────────────
    if now - existing.last_seen > settings.DANGER_STALE_SECONDS:
        logger.info(
            f"State stale ({now - existing.last_seen:.0f}s gap) — "
            f"resetting | floor={floor_id}"
        )
        _danger_states[floor_id] = _make_state(danger_level, now, room_id)
        return

    # ── Level changed → reset timer, preserve zones ───────────────────────────
    if existing.level != danger_level:
        # Carry all existing zone context forward into the new level
        new_zones = set(existing.danger_zones)
        new_zone_times = dict(existing.zone_last_seen)
        if room_id:
            new_zones.add(room_id)
            new_zone_times[room_id] = now
        new_state = DangerState(
            level=danger_level,
            started_at=now,
            last_seen=now,
            danger_zones=new_zones,
            zone_last_seen=new_zone_times,
        )
        _danger_states[floor_id] = new_state
        logger.info(
            f"Level change | floor={floor_id}: {existing.level} → {danger_level} "
            f"zones={sorted(new_zones)}"
        )
        return

    # ── Same level: update zones + check duration ─────────────────────────────
    existing.last_seen = now
    _update_zones(existing, room_id, now)

    duration = now - existing.started_at
    logger.debug(
        f"Sustained | floor={floor_id} level={danger_level} "
        f"duration={duration:.1f}s / {settings.DANGER_SUSTAIN_SECONDS}s "
        f"zones={sorted(existing.danger_zones)}"
    )

    if duration < settings.DANGER_SUSTAIN_SECONDS:
        return  # Noise — not yet confirmed

    # ── Confirmed sustained danger — fire once ────────────────────────────────
    if danger_level == "medium" and not existing.notified:
        existing.notified = True
        logger.info(
            f"MEDIUM CONFIRMED [{duration:.1f}s] | floor={floor_id} "
            f"zones={sorted(existing.danger_zones)} → notifying staff"
        )
        await _notify_staff(floor_id, set(existing.danger_zones))

    elif danger_level in EVACUATION_LEVELS and not existing.evacuated:
        existing.evacuated = True
        logger.warning(
            f"{danger_level.upper()} CONFIRMED [{duration:.1f}s] | floor={floor_id} "
            f"zones={sorted(existing.danger_zones)} → triggering evacuation"
        )
        await _trigger_evacuation(floor_id, danger_level, set(existing.danger_zones))


# ── Action handlers ───────────────────────────────────────────────────────────

async def _persist_event(
    floor_id: str,
    room_id: Optional[str],
    danger_level: str,
    timestamp: str,
) -> None:
    """Write every AI event to DB for audit trail. Never blocks the caller."""
    try:
        col = get_collection("ai_danger_events")
        await col.insert_one({
            "floor_id":     floor_id,
            "room_id":      room_id,
            "danger_level": danger_level,
            "scope":        "floor",
            "timestamp":    timestamp,
            "received_at":  datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.error(f"Failed to persist AI danger event: {e}")


async def _notify_staff(
    floor_id: str,
    danger_zones: Set[str],
) -> None:
    """Sustained MEDIUM: notify staff. Includes all active zones in message."""
    from services.alert_service import create_auto_alert
    from services.websocket_manager import manager

    zones_list  = sorted(danger_zones)
    source_room = _source_room(danger_zones)  # backward compat
    zone_str    = ", ".join(zones_list) if zones_list else None

    if zone_str:
        room_context = f" in rooms: {zone_str}"
        avoidance    = f" Direct guests away from: {zone_str}."
    else:
        room_context = ""
        avoidance    = ""

    message = (
        f"⚠️ Sustained medium-level danger on Floor {floor_id}{room_context}. "
        f"Monitor the area and prepare staff for escalation.{avoidance}"
    )

    # Per-minute dedup key (one staff notification per floor per minute)
    minute_bucket = int(time.time() // 60)
    fire_event_id = f"ai_medium_{floor_id}_{minute_bucket}"

    try:
        alert = await create_auto_alert(
            floor_id=floor_id,
            fire_event_id=fire_event_id,
            risk_level="MEDIUM",
            message=message,
            source_room=source_room,
            danger_zones=zones_list,
            scope="floor",
        )
        if alert:
            ws_payload = {
                **alert,
                "type":         "ai_medium_alert",
                "floor_id":     floor_id,
                "danger_zones": zones_list,
                "source_room":  source_room,
                "severity":     "medium",
                "message":      message,
            }
            await manager.broadcast("ai_medium_alert", ws_payload)
            logger.info(
                f"Staff notified | floor={floor_id} zones={zones_list} "
                f"alert_id={alert['id']}"
            )
    except Exception as e:
        logger.error(f"Failed to send medium danger notification: {e}")


async def _trigger_evacuation(
    floor_id: str,
    danger_level: str,
    danger_zones: Set[str],
) -> None:
    """Sustained HIGH/CRITICAL: trigger full evacuation with all zone context."""
    from services.fire_service import handle_fire_input

    zones_list  = sorted(danger_zones)
    source_room = _source_room(danger_zones)  # backward compat

    if zones_list:
        zone_str = ", ".join(zones_list)
        message  = (
            f"🚨 {danger_level.upper()} danger confirmed on Floor {floor_id} "
            f"in rooms: {zone_str}. "
            f"Guests must avoid these areas: {zone_str}. "
            f"Immediate evacuation required. Use alternate routes."
        )
    else:
        message = (
            f"🚨 {danger_level.upper()} danger confirmed on Floor {floor_id}. "
            f"Immediate evacuation required. Use all available exits."
        )

    synthetic_payload = {
        "floor_id":         floor_id,
        "risk_level":       danger_level.upper(),
        "risk_score":       0.95 if danger_level == "critical" else 0.85,
        "action":           "EVACUATE",
        "density_label":    "HIGH",
        "density_value":    0.9,
        "people_count":     0,
        "fire_conf":        0.9,
        "movement_score":   0.7,
        "source_room":      source_room,     # backward compat: first zone
        "danger_zones":     zones_list,      # full multi-zone context
        "scope":            "floor",
        "override_message": message,
    }

    try:
        await handle_fire_input(synthetic_payload)
        logger.warning(
            f"Evacuation triggered | floor={floor_id} "
            f"zones={zones_list} level={danger_level}"
        )
    except Exception as e:
        logger.error(f"Failed to trigger evacuation: {e}")


# ── Debug helper ──────────────────────────────────────────────────────────────

def get_all_states() -> dict:
    """Return snapshot of all active floor states (dev/debug endpoint)."""
    result = {}
    for floor_id, state in _danger_states.items():
        result[floor_id] = {
            "level":        state.level,
            "duration_s":   round(time.monotonic() - state.started_at, 1),
            "danger_zones": sorted(state.danger_zones),
            "source_room":  _source_room(state.danger_zones),   # backward compat
            "notified":     state.notified,
            "evacuated":    state.evacuated,
        }
    return result

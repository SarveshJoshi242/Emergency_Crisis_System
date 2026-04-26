# ============================================================
#  Emergency Backend · services/task_service.py
#  Purpose: Rule-based task generation triggered by an alert
# ============================================================

from datetime import datetime, timezone
from typing import Optional, List
from database import get_collection
from services.staff_service import get_any_staff_id
from services.gemini_service import format_tasks


# ── Task rules ───────────────────────────────────────────────────────────────
# Returns a list of task-name strings given fire event data.

def _determine_tasks(
    risk_level: str,
    fire_conf: float,
    density_label: str,
    movement_score: float,
) -> List[str]:
    tasks = set()  # type: ignore

    if risk_level == "CRITICAL":
        tasks.update([
            "Evacuate Floor",
            "Check All Rooms",
            "Assist Injured",
            "Guide Guests to Exits",
            "Use Extinguisher",
            "Secure Exits",
            "Calm Crowd",
        ])
    elif fire_conf > 0.7 and density_label == "HIGH":
        tasks.update(["Evacuate Floor", "Check All Rooms", "Assist Injured"])
    elif fire_conf > 0.5 and density_label in ("MEDIUM", "HIGH"):
        tasks.update(["Guide Guests to Exits", "Use Extinguisher"])

    if movement_score > 0.6:
        tasks.update(["Secure Exits", "Calm Crowd"])

    # Fallback: always have at least one task for any alert
    if not tasks:
        tasks.add("Investigate and Monitor Area")

    return list(tasks)


# ── Service function ──────────────────────────────────────────────────────────

async def generate_tasks(
    alert_id: str,
    floor_id: str,
    floor_name: str,
    risk_level: str,
    fire_conf: float,
    density_label: str,
    movement_score: float,
    people_count: int = 0,
    source_room: str = None,   # optional room that triggered the alert
) -> List[dict]:
    """Generate and persist tasks for an alert. Returns saved task docs."""
    col = get_collection("tasks")
    raw_names = _determine_tasks(risk_level, fire_conf, density_label, movement_score)
    staff_id = await get_any_staff_id()

    # ── Gemini: enrich raw task names with actionable sentences ─────────────
    task_sentences = await format_tasks(
        raw_tasks=raw_names,
        floor_name=floor_name,
        risk_level=risk_level,
        density_label=density_label,
        people_count=people_count,
        fire_conf=fire_conf,
        source_room=source_room,
    )

    saved: List[dict] = []
    now = datetime.now(timezone.utc).isoformat()

    for raw_name, sentence in zip(raw_names, task_sentences):
        doc = {
            "task":        sentence,        # Gemini-formatted sentence
            "task_type":   raw_name,        # original rule label (for filtering)
            "alert_id":    alert_id,
            "floor_id":    floor_id,
            "source_room": source_room,     # room context (may be None)
            "assigned_to": staff_id,
            "status":      "pending",
            "created_at":  now,
        }
        result = await col.insert_one(doc)
        doc["id"] = str(result.inserted_id)
        doc.pop("_id", None)
        saved.append(doc)

    return saved


async def list_tasks(floor_id: Optional[str] = None) -> List[dict]:
    col = get_collection("tasks")
    query = {"floor_id": floor_id} if floor_id else {}
    docs: List[dict] = []
    async for doc in col.find(query).sort("created_at", -1):
        doc["id"] = str(doc.pop("_id"))
        docs.append(doc)
    return docs


async def complete_task(task_id: str) -> bool:
    from bson import ObjectId
    col = get_collection("tasks")
    result = await col.update_one(
        {"_id": ObjectId(task_id)},
        {"$set": {"status": "done"}},
    )
    return result.modified_count == 1

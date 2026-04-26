# ============================================================
#  Emergency Backend · services/staff_service.py
# ============================================================

from datetime import datetime, timezone
from typing import Optional, List
from database import get_collection
from bson import ObjectId


async def create_staff(name: str, role: str = "staff") -> dict:
    col = get_collection("staff")
    doc = {
        "name": name,
        "role": role,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await col.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    doc.pop("_id", None)
    return doc


async def list_staff() -> List[dict]:
    col = get_collection("staff")
    docs = []
    async for doc in col.find():
        doc["id"] = str(doc.pop("_id"))
        docs.append(doc)
    return docs


async def get_any_staff_id() -> Optional[str]:
    """Return the first staff member's id — used for auto task assignment."""
    col = get_collection("staff")
    doc = await col.find_one()
    if doc:
        return str(doc["_id"])
    return None

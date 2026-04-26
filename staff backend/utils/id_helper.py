# ============================================================
#  Emergency Backend · utils/id_helper.py
#  Purpose: ObjectId ↔ str conversion helpers
# ============================================================

from bson import ObjectId


def oid(v: str) -> ObjectId:
    """Convert a hex string to a MongoDB ObjectId."""
    return ObjectId(v)


def doc_id(doc: dict) -> dict:
    """Convert _id ObjectId to 'id' string in a MongoDB document."""
    if doc and "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    return doc

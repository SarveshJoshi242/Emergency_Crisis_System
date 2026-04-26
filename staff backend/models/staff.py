# ============================================================
#  Emergency Backend · models/staff.py
# ============================================================

from pydantic import BaseModel


class StaffCreate(BaseModel):
    name: str
    role: str = "staff"   # No auth for MVP — role is informational only


class StaffResponse(BaseModel):
    id: str
    name: str
    role: str
    created_at: str

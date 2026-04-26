# ============================================================
#  Emergency Backend · models/task.py
# ============================================================

from pydantic import BaseModel
from typing import Optional


class TaskResponse(BaseModel):
    id: str
    task: str
    alert_id: str
    floor_id: str
    assigned_to: Optional[str] = None   # staff_id
    status: str                          # pending | done
    created_at: str

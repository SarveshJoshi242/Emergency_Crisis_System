# ============================================================
#  Emergency Backend · routers/tasks.py
# ============================================================

from fastapi import APIRouter, HTTPException
from typing import Optional
from services.task_service import list_tasks, complete_task

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.get("", summary="List all tasks (optionally filter by floor_id)")
async def get_tasks(floor_id: Optional[str] = None):
    return await list_tasks(floor_id=floor_id)


@router.post("/{task_id}/complete", summary="Mark a task as done")
async def mark_complete(task_id: str):
    ok = await complete_task(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found or already done")
    return {"task_id": task_id, "status": "done"}

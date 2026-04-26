#!/usr/bin/env python
"""
Staff Backend — development server startup script.

Usage:
    python run.py
"""

import os
import sys
from pathlib import Path

# ── Project root (staff backend/) ────────────────────────────────────────────
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# ── Workspace root (hospitality backend/) — contains the shared auth/ package ─
# MUST be set as PYTHONPATH env var (not just sys.path) so that uvicorn's
# --reload subprocess workers inherit it.  sys.path mutations only live in
# the parent process; subprocesses start fresh from the environment.
workspace_root = project_root.parent   # .../hospitality backend/
existing_pythonpath = os.environ.get("PYTHONPATH", "")
os.environ["PYTHONPATH"] = (
    str(workspace_root) + os.pathsep + existing_pythonpath
    if existing_pythonpath
    else str(workspace_root)
)
# Also insert for the current process (belt-and-suspenders)
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

import uvicorn
from config import settings

if __name__ == "__main__":
    print(f"\n{'='*70}")
    print(f"🚨 Starting Smart Emergency Management Platform")
    print(f"    Version: 2.0.0")
    print(f"    Port: {settings.PORT}")
    print(f"    MongoDB: {settings.DB_NAME}")
    print(f"    Swagger: http://localhost:{settings.PORT}/docs")
    print(f"{'='*70}\n")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=True,
        log_level="info",
    )

#!/usr/bin/env python
"""
Development server startup script.

Usage:
    python run.py
"""

import os
import sys
from pathlib import Path

# ── Load .env file BEFORE any other imports ────────────────────────────────
from dotenv import load_dotenv
workspace_root = Path(__file__).parent.parent
load_dotenv(workspace_root / ".env")

# ── Project root (guest_backend/) ────────────────────────────────────────────
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
from app.core.config import settings

# ── Force UTF-8 stdout so emoji don't crash on Windows cp1252 consoles ────────
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

if __name__ == "__main__":
    print(f"\n{'='*70}")
    print(f"[START] Starting {settings.APP_NAME}")
    print(f"    Version : {settings.APP_VERSION}")
    print(f"    Debug   : {settings.DEBUG}")
    print(f"    Port    : 8000")
    print(f"{'='*70}\n")

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info" if not settings.DEBUG else "debug",
    )




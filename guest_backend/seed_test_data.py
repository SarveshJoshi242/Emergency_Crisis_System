# -*- coding: utf-8 -*-
"""
seed_test_data.py
=================
Resets and re-seeds the 'guests' and 'staff_accounts' collections
with data that matches the actual emergency_db schema.

Run from guest_backend/ directory:
    python seed_test_data.py

What it seeds:
  - 3 guests  (room_id matches actual node IDs in guest_sessions + floors)
  - 1 staff account  (login via staff backend POST /auth/staff/login)
"""

import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime, timezone

# Force UTF-8 on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Resolve workspace root for auth.hashing import
workspace_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(workspace_root))

from motor.motor_asyncio import AsyncIOMotorClient
import certifi
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DB_NAME     = os.getenv("MONGODB_DB_NAME", "emergency_db")
JWT_SECRET  = os.getenv("JWT_SECRET", "")

if JWT_SECRET:
    os.environ["JWT_SECRET"] = JWT_SECRET

from auth.hashing import hash_password  # noqa: E402


# ── Guest documents ────────────────────────────────────────────────────────────
# room_id MUST match node IDs in guest_sessions.room_id and the floors graph.
# These values are taken directly from the actual DB (seen in Compass).
TEST_GUESTS = [
    {
        "room_id":    "master_bedroom",         # from guest_sessions data
        "floor_id":   "Third Floor",            # matches guest_sessions.floor_id
        "phone_last4": "1234",
        "booking_id": "BK-MB-001",
        "name":       "Guest - Master Bedroom",
        "status":     "checked_in",
        "created_at": datetime.now(tz=timezone.utc),
    },
    {
        "room_id":    "royal_suite_rm_301",     # from guest_sessions data
        "floor_id":   "Third Floor",
        "phone_last4": "5678",
        "booking_id": "BK-RS-301",
        "name":       "Guest - Royal Suite 301",
        "status":     "checked_in",
        "created_at": datetime.now(tz=timezone.utc),
    },
    {
        "room_id":    "royal_suite_rm_301",     # second guest, same room different phone
        "floor_id":   "Third Floor",
        "phone_last4": "9999",
        "booking_id": "BK-RS-302",
        "name":       "Guest - Royal Suite 301 B",
        "status":     "checked_in",
        "created_at": datetime.now(tz=timezone.utc),
    },
]

# ── Staff account ──────────────────────────────────────────────────────────────
TEST_STAFF = {
    "name":          "Admin User",
    "email":         "admin@hotel.com",
    "password_hash": hash_password("Admin@1234"),
    "role":          "staff",
    "permissions":   ["evacuate", "analytics", "manage_staff"],
    "is_active":     True,
    "created_at":    datetime.now(tz=timezone.utc),
}


async def seed():
    client = AsyncIOMotorClient(MONGODB_URL, tlsCAFile=certifi.where())
    db = client[DB_NAME]

    print(f"\n[SEED] Connecting to '{DB_NAME}'...\n")

    # ── Clear stale guests (old schema had room_number instead of room_id) ─────
    old_schema = await db["guests"].find_one({"room_number": {"$exists": True}})
    if old_schema:
        result = await db["guests"].delete_many({"room_number": {"$exists": True}})
        print(f"  [CLEAN] Removed {result.deleted_count} old guest doc(s) with 'room_number' field (wrong schema)")

    # ── Insert guests ──────────────────────────────────────────────────────────
    print("  [GUESTS]")
    for g in TEST_GUESTS:
        existing = await db["guests"].find_one({
            "room_id": g["room_id"],
            "phone_last4": g["phone_last4"],
        })
        if existing:
            print(f"    [SKIP] room_id={g['room_id']} phone_last4={g['phone_last4']} already exists")
        else:
            result = await db["guests"].insert_one(g)
            print(f"    [OK] Inserted room_id={g['room_id']} phone={g['phone_last4']} booking={g['booking_id']}")

    print()

    # ── Staff account ──────────────────────────────────────────────────────────
    print("  [STAFF]")
    existing_staff = await db["staff_accounts"].find_one({"email": TEST_STAFF["email"]})
    if existing_staff:
        print(f"    [SKIP] {TEST_STAFF['email']} already exists (id={existing_staff['_id']})")
    else:
        result = await db["staff_accounts"].insert_one(TEST_STAFF)
        print(f"    [OK] Staff inserted  id={result.inserted_id}")
        print(f"         email={TEST_STAFF['email']}  password=Admin@1234")

    print()
    print("=" * 60)
    print("[DONE] Use these credentials to test:")
    print()
    print("  GUEST CHECK-IN  ->  POST http://localhost:8000/auth/guest/checkin")
    print('  Option A:  { "room_id": "master_bedroom",      "phone_last4": "1234" }')
    print('  Option B:  { "room_id": "royal_suite_rm_301",  "phone_last4": "5678" }')
    print('  Option C:  { "booking_id": "BK-MB-001" }')
    print()
    print("  STAFF LOGIN     ->  POST http://localhost:8001/auth/staff/login")
    print('  Body: { "email": "admin@hotel.com", "password": "Admin@1234" }')
    print("=" * 60)
    print()

    client.close()


if __name__ == "__main__":
    asyncio.run(seed())

"""
Example API usage scenarios for the guest-side emergency backend.

This file demonstrates how to interact with all endpoint using Python.
Run with: python examples_usage.py
"""

import asyncio
import httpx
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8000"
STAFF_BACKEND_URL = "http://localhost:8001"


async def example_complete_evacuation_flow():
    """
    Demonstrates a complete evacuation flow from session creation to safe zone.
    """
    print("\n" + "="*70)
    print("COMPLETE EVACUATION FLOW EXAMPLE")
    print("="*70)
    
    async with httpx.AsyncClient() as client:
        
        # ========== STEP 1: START SESSION ==========
        print("\n[1] Starting guest session...")
        response = await client.post(
            f"{BASE_URL}/guest/session/start",
            json={"room_id": "101"}
        )
        if response.status_code != 200:
            print(f"Error: {response.status_code}")
            return
        
        session_data = response.json()
        session_id = session_data["session_id"]
        floor_id = session_data["floor_id"]
        print(f"✓ Session created: {session_id}")
        print(f"  Floor: {floor_id}, Room: {session_data['room_id']}")
        
        
        # ========== STEP 2: GET FLOOR PLAN ==========
        print("\n[2] Retrieving floor plan...")
        response = await client.get(f"{BASE_URL}/guest/floor/{floor_id}")
        if response.status_code != 200:
            print(f"Error: {response.status_code}")
            return
        
        floor_data = response.json()
        print(f"✓ Floor plan loaded")
        print(f"  Nodes: {len(floor_data['nodes'])}")
        print(f"  Edges: {len(floor_data['edges'])}")
        
        
        # ========== STEP 3: CHECK EMERGENCY STATUS ==========
        print("\n[3] Checking emergency status...")
        response = await client.get(f"{BASE_URL}/guest/emergency-status")
        if response.status_code == 200:
            emergency = response.json()
            print(f"✓ Emergency active: {emergency['active']}")
            print(f"  Type: {emergency.get('emergency_type')}")
            print(f"  Blocked nodes: {emergency.get('blocked_nodes', [])}")
            print(f"  Safe exits: {emergency.get('safe_exits', [])}")
        
        
        # ========== STEP 4: UPDATE LOCATION (MANUAL) ==========
        print("\n[4] Guest manually updating location...")
        response = await client.post(
            f"{BASE_URL}/guest/update-location",
            json={
                "session_id": session_id,
                "node_id": "room_101"
            }
        )
        print(f"✓ Location updated: room_101")
        
        
        # ========== STEP 5: GENERATE EVACUATION ROUTE ==========
        print("\n[5] Generating evacuation route...")
        response = await client.post(
            f"{BASE_URL}/guest/evacuation-route",
            json={"session_id": session_id}
        )
        if response.status_code != 200:
            print(f"Error: {response.status_code}")
            return
        
        route_data = response.json()
        path = route_data["path"]
        distance = route_data["distance"]
        print(f"✓ Route generated")
        print(f"  Path: {' → '.join(path)}")
        print(f"  Distance: {distance}")
        
        
        # ========== STEP 6: GET NAVIGATION STEPS ==========
        print("\n[6] Converting to navigation steps...")
        response = await client.post(
            f"{BASE_URL}/guest/navigation-steps",
            json={
                "session_id": session_id,
                "path": path
            }
        )
        if response.status_code == 200:
            nav_data = response.json()
            print(f"✓ Navigation steps:")
            for i, step in enumerate(nav_data["steps"], 1):
                print(f"  {i}. {step}")
        
        
        # ========== STEP 7: SIMULATE STEP PROGRESSION ==========
        print("\n[7] Simulating step progression...")
        
        # Step 1: Completed
        response = await client.post(
            f"{BASE_URL}/guest/step-update",
            json={
                "session_id": session_id,
                "action": "completed",
                "details": "Exited room successfully"
            }
        )
        if response.status_code == 200:
            result = response.json()
            print(f"✓ Step update: {result['next_action']}")
        
        # Step 2: Guest unsure, requesting reroute
        response = await client.post(
            f"{BASE_URL}/guest/step-update",
            json={
                "session_id": session_id,
                "action": "reroute",
                "details": "Corridor blocked by debris"
            }
        )
        if response.status_code == 200:
            result = response.json()
            print(f"✓ Reroute requested: {result['next_action']}")
        
        
        # ========== STEP 8: REQUEST HELP ==========
        print("\n[8] Guest requesting help...")
        response = await client.post(
            f"{BASE_URL}/guest/request-help",
            json={
                "session_id": session_id,
                "issue": "Cannot locate corridor A, need assistance"
            }
        )
        if response.status_code == 200:
            result = response.json()
            print(f"✓ Help request sent: {result['message']}")
            print(f"  Status: {result['status']}")
        
        
        # ========== STEP 9: GET NOTIFICATIONS ==========
        print("\n[9] Checking for notifications from staff...")
        response = await client.get(
            f"{BASE_URL}/guest/notifications",
            params={"floor_id": floor_id}
        )
        if response.status_code == 200:
            notif_data = response.json()
            print(f"✓ Notifications ({notif_data['count']}):")
            for notif in notif_data["notifications"]:
                print(f"  - {notif}")
        
        
        # ========== STEP 10: SAFE ZONE REACHED ==========
        print("\n[10] Guest confirms reaching safe zone...")
        response = await client.post(
            f"{BASE_URL}/guest/reached-safe-zone",
            json={"session_id": session_id}
        )
        if response.status_code == 200:
            result = response.json()
            print(f"✓ {result['message']}")
            print(f"  Status: {result['status']}")


async def example_rerouting():
    """
    Example showing route recalculation when conditions change.
    """
    print("\n" + "="*70)
    print("REROUTING EXAMPLE")
    print("="*70)
    
    async with httpx.AsyncClient() as client:
        
        # Create session
        print("\n[1] Creating session...")
        response = await client.post(
            f"{BASE_URL}/guest/session/start",
            json={"room_id": "201"}
        )
        session_id = response.json()["session_id"]
        floor_id = response.json()["floor_id"]
        print(f"✓ Session: {session_id}")
        
        # Initial route
        print("\n[2] Generating initial route...")
        response = await client.post(
            f"{BASE_URL}/guest/evacuation-route",
            json={"session_id": session_id}
        )
        initial_path = response.json()["path"]
        print(f"✓ Initial path: {' → '.join(initial_path)}")
        
        # Simulate emergency state changing (blocked nodes)
        print("\n[3] Emergency state updates (stairs blocked)...")
        print("   [In real scenario, staff backend would update this]")
        
        # Request reroute
        print("\n[4] Requesting new route...")
        response = await client.post(
            f"{BASE_URL}/guest/reroute",
            json={"session_id": session_id}
        )
        new_path = response.json()["path"]
        print(f"✓ New path: {' → '.join(new_path)}")
        
        if new_path != initial_path:
            print("  → Route successfully recalculated!")


async def example_multiple_sessions():
    """
    Example showing multiple guests on same floor.
    """
    print("\n" + "="*70)
    print("MULTIPLE GUESTS EXAMPLE")
    print("="*70)
    
    async with httpx.AsyncClient() as client:
        
        rooms = ["101", "102", "103"]
        sessions = []
        
        print(f"\n[1] Creating {len(rooms)} sessions...")
        for room in rooms:
            response = await client.post(
                f"{BASE_URL}/guest/session/start",
                json={"room_id": room}
            )
            if response.status_code == 200:
                data = response.json()
                sessions.append(data)
                print(f"  ✓ Room {room}: {data['session_id']}")
        
        print(f"\n[2] Generating routes for all guests...")
        for session in sessions:
            response = await client.post(
                f"{BASE_URL}/guest/evacuation-route",
                json={"session_id": session["session_id"]}
            )
            if response.status_code == 200:
                path = response.json()["path"]
                print(f"  ✓ {session['room_id']}: {' → '.join(path[:3])}...")


async def main():
    """Run all examples."""
    try:
        # Check if server is running
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"{BASE_URL}/health", timeout=2)
                print(f"✓ Backend is running at {BASE_URL}")
            except Exception as e:
                print(f"✗ Cannot connect to backend at {BASE_URL}")
                print(f"  Make sure the server is running: python -m uvicorn app.main:app --reload")
                return
        
        # Run examples
        await example_complete_evacuation_flow()
        await example_rerouting()
        await example_multiple_sessions()
        
        print("\n" + "="*70)
        print("✅ All examples completed!")
        print("="*70)
        print("\n💡 Next steps:")
        print("  1. Check MongoDB collections in Atlas console")
        print("  2. Test API docs at http://localhost:8000/docs")
        print("  3. Try with different room_ids and floor configurations")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("\n🚀 Smart Emergency Management System - Guest Backend")
    print("  Example Usage Scenarios\n")
    asyncio.run(main())

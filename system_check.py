import asyncio
import json
import requests
import websockets

async def check_websocket(uri):
    try:
        async with websockets.connect(uri, ping_timeout=5) as websocket:
            return True
    except Exception:
        return False

def main():
    print("====================")
    print("SYSTEM STATUS")
    print("=============")

    # 1. Guest Backend
    guest_ok = False
    try:
        res = requests.get("http://localhost:8000/health", timeout=3)
        if res.status_code == 200 and res.json().get("service") == "guest":
            guest_ok = True
    except:
        pass
    print(f"Guest Backend: {'OK' if guest_ok else 'FAIL'}")

    # 2. Staff Backend
    staff_ok = False
    try:
        res = requests.get("http://localhost:8001/health", timeout=3)
        if res.status_code == 200 and res.json().get("service") == "staff":
            staff_ok = True
    except:
        pass
    print(f"Staff Backend: {'OK' if staff_ok else 'FAIL'}")

    # 3. Alert API
    api_ok = False
    try:
        payload = {
            "type": "fire",
            "room_id": "system_check",
            "floor": "0",
            "confidence": 0.99,
            "source": "manual"
        }
        res = requests.post("http://localhost:8001/alerts", json=payload, timeout=3)
        if res.status_code in (200, 201):
            api_ok = True
    except:
        pass
    print(f"Alert API:     {'OK' if api_ok else 'FAIL'}")

    # 4. WebSocket
    ws_ok = asyncio.run(check_websocket("ws://localhost:8001/ws/live"))
    print(f"WebSocket:     {'OK' if ws_ok else 'FAIL'}")
    
    print("============")

if __name__ == "__main__":
    main()

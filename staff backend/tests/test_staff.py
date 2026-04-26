# ============================================================
#  tests/test_staff.py
#
#  Tests 8 & 9 (spec):
#    8. Manual room trigger via POST /staff/emergency/trigger-room
#    9. Backward compatibility — existing staff endpoints unchanged
# ============================================================

import pytest
from unittest.mock import AsyncMock, patch


# ── TEST 8: Manual room trigger ───────────────────────────────────────────────

class TestTriggerRoomEndpoint:

    async def test_medium_severity_returns_notified(self, client):
        """Medium trigger → creates alert, broadcasts, returns 'notified'."""
        c, _ = client
        with patch("services.websocket_manager.manager.broadcast", new_callable=AsyncMock):
            r = await c.post("/staff/emergency/trigger-room", json={
                "floor_id": "floor_1",
                "room_id":  "room_101",
                "severity": "medium",
            })
        assert r.status_code == 200
        body = r.json()
        assert body["status"]      == "notified"
        assert body["source_room"] == "room_101"
        assert body["severity"]    == "medium"
        assert "alert_id" in body
        assert "message"  in body

    async def test_medium_broadcasts_ws_event(self, client):
        """WebSocket must be called at least once for staff notification."""
        c, _ = client
        with patch("services.websocket_manager.manager.broadcast",
                   new_callable=AsyncMock) as mock_ws:
            await c.post("/staff/emergency/trigger-room", json={
                "floor_id": "floor_1",
                "room_id":  "room_101",
                "severity": "medium",
            })
        mock_ws.assert_awaited()

    async def test_high_severity_returns_evacuation_triggered(self, client):
        """High trigger → runs full evacuation pipeline → 'evacuation_triggered'."""
        c, _ = client
        with patch("services.websocket_manager.manager.broadcast", new_callable=AsyncMock), \
             patch("services.gemini_service.format_alert_message",
                   new_callable=AsyncMock, return_value="🚨 Evacuate floor_1"), \
             patch("services.task_service.generate_tasks",
                   new_callable=AsyncMock, return_value=[]):
            r = await c.post("/staff/emergency/trigger-room", json={
                "floor_id": "floor_1",
                "room_id":  "room_101",
                "severity": "high",
            })
        assert r.status_code == 200
        body = r.json()
        assert body["status"]      == "evacuation_triggered"
        assert body["source_room"] == "room_101"
        assert body["severity"]    == "high"

    async def test_critical_severity_triggers_evacuation(self, client):
        c, _ = client
        with patch("services.websocket_manager.manager.broadcast", new_callable=AsyncMock), \
             patch("services.gemini_service.format_alert_message",
                   new_callable=AsyncMock, return_value="🚨 Critical"), \
             patch("services.task_service.generate_tasks",
                   new_callable=AsyncMock, return_value=[]):
            r = await c.post("/staff/emergency/trigger-room", json={
                "floor_id": "floor_1",
                "room_id":  "room_505",
                "severity": "critical",
            })
        assert r.status_code == 200
        assert r.json()["status"] == "evacuation_triggered"

    async def test_custom_message_accepted(self, client):
        c, _ = client
        custom = "Smoke observed near Room 101. Evacuate immediately."
        with patch("services.websocket_manager.manager.broadcast", new_callable=AsyncMock):
            r = await c.post("/staff/emergency/trigger-room", json={
                "floor_id": "floor_1",
                "room_id":  "room_101",
                "severity": "medium",
                "message":  custom,
            })
        assert r.status_code == 200
        assert r.json()["message"] == custom

    async def test_room_included_in_alert_scope_is_floor(self, client):
        """Internal scope must always be 'floor' (room is context, not scope)."""
        c, mock_col = client
        with patch("services.websocket_manager.manager.broadcast", new_callable=AsyncMock):
            await c.post("/staff/emergency/trigger-room", json={
                "floor_id": "floor_1",
                "room_id":  "room_101",
                "severity": "medium",
            })
        call_kwargs = mock_col.insert_one.call_args[0][0]
        assert call_kwargs.get("scope") == "floor"

    async def test_missing_floor_id_rejected(self, client):
        c, _ = client
        r = await c.post("/staff/emergency/trigger-room", json={
            "room_id":  "room_101",
            "severity": "medium",
        })
        assert r.status_code == 422

    async def test_invalid_severity_rejected(self, client):
        c, _ = client
        r = await c.post("/staff/emergency/trigger-room", json={
            "floor_id": "floor_1",
            "room_id":  "room_101",
            "severity": "catastrophic",   # not in Literal
        })
        assert r.status_code == 422


# ── TEST 9: Backward compatibility — existing endpoints ───────────────────────

class TestBackwardCompatibility:

    async def test_get_staff_returns_list(self, client):
        """GET /staff must return a list (always worked)."""
        c, _ = client
        r = await c.get("/staff")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    async def test_post_staff_registers_member(self, client):
        c, mock_col = client
        r = await c.post("/staff", json={"name": "Alice", "role": "security"})
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "Alice"
        assert body["role"] == "security"
        assert "id" in body

    async def test_health_endpoint_unchanged(self, client):
        c, _ = client
        r = await c.get("/")
        assert r.status_code == 200
        body = r.json()
        assert body["status"]  == "ok"
        assert body["version"] == "2.0.0"

    async def test_fire_input_backward_compat(self, client):
        """
        POST /fire/input (existing InfernoGuard endpoint) must still work
        WITHOUT danger_zones or source_room — those are optional extensions.
        """
        c, _ = client
        with patch("services.gemini_service.format_alert_message",
                   new_callable=AsyncMock, return_value="High risk alert"), \
             patch("services.task_service.generate_tasks",
                   new_callable=AsyncMock, return_value=[]), \
             patch("services.websocket_manager.manager.broadcast",
                   new_callable=AsyncMock):
            r = await c.post("/fire/input", json={
                "floor_id":      "floor_1",
                "risk_level":    "HIGH",
                "risk_score":    0.9,
                "action":        "EVACUATE",
                "density_label": "HIGH",
                "density_value": 0.9,
                "people_count":  5,
                "fire_conf":     0.9,
                "movement_score": 0.7,
            })
        assert r.status_code == 200
        body = r.json()
        assert "risk_level"    in body
        assert "alert_created" in body
        assert body["risk_level"] == "HIGH"

    async def test_alert_status_returns_list(self, client):
        """GET /alert/status must return a JSON list — existing contract."""
        c, _ = client
        r = await c.get("/alert/status")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    async def test_debug_danger_states_returns_dict(self, client):
        """GET /debug/danger-states (new endpoint) returns a dict."""
        c, _ = client
        r = await c.get("/debug/danger-states")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

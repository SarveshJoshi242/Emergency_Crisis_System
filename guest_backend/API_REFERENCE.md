# API Reference - Guest Backend

## Base URL

```
http://localhost:8000/guest
```

API Documentation: http://localhost:8000/docs

---

## Endpoints

### 1. START GUEST SESSION

**Endpoint:** `POST /session/start`

**Description:** Create a new guest evacuation session

**Request:**
```json
{
  "room_id": "101"
}
```

**Response:** `200 OK`
```json
{
  "session_id": "sess_abc123def456",
  "floor_id": "floor_1",
  "room_id": "101",
  "current_node": "room_101",
  "status": "active",
  "created_at": "2024-01-01T00:00:00Z"
}
```

**Error Responses:**
- `400 Bad Request`: Invalid room_id
- `500 Internal Server Error`: Staff backend unavailable

**Integration Flow:**
1. Call staff backend to get `floor_id` from `room_id`
2. Create MongoDB document in `guest_sessions`
3. Return session info

---

### 2. GET FLOOR PLAN

**Endpoint:** `GET /floor/{floor_id}`

**Parameters:**
- `floor_id` (path): Floor identifier

**Description:** Get complete floor plan with nodes and edges

**Response:** `200 OK`
```json
{
  "floor_id": "floor_1",
  "nodes": [
    {
      "id": "room_101",
      "label": "Conference Room A",
      "type": "room",
      "position": {"x": 10, "y": 20}
    },
    {
      "id": "corridor_a",
      "label": "Main Corridor",
      "type": "corridor",
      "position": null
    }
  ],
  "edges": [
    {
      "from": "room_101",
      "to": "corridor_a",
      "weight": 5.0
    }
  ]
}
```

**Caching Behavior:**
- First call: Fetches from staff backend and caches locally
- Subsequent calls: Returns from local MongoDB cache
- Cache validity: Until emergency state changes

**Error Responses:**
- `404 Not Found`: Floor not found in staff backend
- `500 Internal Server Error`: Database error

---

### 3. UPDATE LOCATION

**Endpoint:** `POST /update-location`

**Description:** Guest manually updates their current position

**Request:**
```json
{
  "session_id": "sess_abc123def456",
  "node_id": "corridor_a"
}
```

**Response:** `200 OK`
```json
{
  "message": "location updated",
  "node_id": "corridor_a"
}
```

**Error Responses:**
- `404 Not Found`: Session or node not found
- `400 Bad Request`: Invalid node_id for this floor
- `500 Internal Server Error`: Database error

**Use Case:**
- Guest manually selects their position from available options
- Called before generating evacuation route
- Can be called at any time to update location

---

### 4. GET EMERGENCY STATUS

**Endpoint:** `GET /emergency-status`

**Description:** Get current emergency state across all floors

**Response:** `200 OK`
```json
{
  "active": true,
  "emergency_type": "fire",
  "affected_floors": ["floor_1", "floor_2"],
  "blocked_nodes": ["room_105", "stairs_east", "corridor_b"],
  "safe_exits": ["exit_south", "exit_north"],
  "updated_at": "2024-01-01T00:05:00Z"
}
```

**Default Response (No Emergency):**
```json
{
  "active": false,
  "emergency_type": null,
  "affected_floors": [],
  "blocked_nodes": [],
  "safe_exits": [],
  "updated_at": "2024-01-01T00:00:00Z"
}
```

**Sync Behavior:**
1. Attempts to get latest from staff backend
2. Updates local MongoDB cache
3. Returns current state (with local fallback)

**Error Responses:**
- No direct errors; returns default state on failure

---

### 5. GENERATE EVACUATION ROUTE (CORE)

**Endpoint:** `POST /evacuation-route`

**Description:** Compute optimal evacuation route to safe zone

**Request:**
```json
{
  "session_id": "sess_abc123def456"
}
```

**Response:** `200 OK`
```json
{
  "path": ["room_101", "corridor_a", "stairs_1", "exit_south"],
  "distance": 28.5
}
```

**Algorithm:**
- Uses Dijkstra's algorithm with edge weights
- Avoids blocked nodes from emergency state
- Routes to closest safe exit
- Fallback: BFS if Dijkstra unavailable

**Response Algorithm Selection:**
```
if PATHFINDING_ALGORITHM == "dijkstra":
  use weighted shortest path
else:
  use BFS (unweighted)
```

**Error Responses:**
- `404 Not Found`: Session not found
- `500 Internal Server Error`: Route generation failed

**Blocked Nodes:**
Automatically respected from emergency state:
- Blocked corridors
- Unsafe stairs
- Damaged areas

---

### 6. GET NAVIGATION STEPS

**Endpoint:** `POST /navigation-steps`

**Description:** Convert node path to human-readable instructions

**Request:**
```json
{
  "session_id": "sess_abc123def456",
  "path": ["room_101", "corridor_a", "stairs_1", "exit_south"]
}
```

**Response:** `200 OK`
```json
{
  "steps": [
    "Exit your room",
    "Move to Main Corridor",
    "Go to Stairs 1",
    "Exit through South Exit to safety"
  ]
}
```

**Step Generation Logic:**
1. First step: "Exit from {start_label}"
2. Middle steps: "Move to {location}" or "Take stairs"
3. Final step: "Exit through {exit}" or "Reach {safe_zone}"

**Error Responses:**
- `404 Not Found`: Session not found
- `400 Bad Request`: Empty path
- `500 Internal Server Error`: Step generation failed

---

### 7. STEP UPDATE

**Endpoint:** `POST /step-update`

**Description:** Guest response to each navigation step

**Request:**
```json
{
  "session_id": "sess_abc123def456",
  "action": "completed",
  "details": "Exited room successfully"
}
```

**Action Types:**

#### Completed
```json
{
  "action": "completed",
  "details": "Optional description"
}
```
Response: `next_action: next-step`

#### Reroute
```json
{
  "action": "reroute",
  "details": "Corridor blocked, need alternative"
}
```
Response: `next_action: generate-route`

#### Help
```json
{
  "action": "help",
  "details": "Severely injured, need immediate assistance"
}
```
Response: `next_action: contact-staff`

**Response:** `200 OK`
```json
{
  "message": "Action completed recorded",
  "next_action": "next-step"
}
```

**Logging:**
- All actions logged to `guest_logs` collection
- Associated with current node
- Timestamped for audit trail

**Error Responses:**
- `404 Not Found`: Session not found
- `500 Internal Server Error`: Logging failed

---

### 8. REROUTE

**Endpoint:** `POST /reroute`

**Description:** Recalculate evacuation route from current position

**Request:**
```json
{
  "session_id": "sess_abc123def456"
}
```

**Response:** `200 OK`
```json
{
  "path": ["corridor_a", "stairs_2", "exit_north"],
  "distance": 18.5
}
```

**When to Call:**
- Guest reports obstacle blocking current route
- Emergency state changes (new blocked nodes)
- Guest needs alternative path

**Difference from evacuating-route:**
- Uses current_node instead of initial room
- Re-evaluates emergency state
- May return different exit if previous blocked

**Error Responses:**
- `404 Not Found`: Session not found
- `500 Internal Server Error`: Route generation failed

---

### 9. REQUEST HELP

**Endpoint:** `POST /request-help`

**Description:** Guest requests immediate assistance

**Request:**
```json
{
  "session_id": "sess_abc123def456",
  "issue": "trapped"
}
```

**Issue Types:**
- `"trapped"` - Guest physically trapped
- `"injured"` - Guest or others injured
- `"lost"` - Guest disoriented/lost
- `"confused"` - Unsure of directions
- Custom text: Any description

**Response:** `200 OK`
```json
{
  "message": "help request sent",
  "session_id": "sess_abc123def456",
  "status": "pending"
}
```

**Workflow:**
1. Log locally to `guest_logs`
2. Forward to staff backend: `POST /staff/emergency/guest-help-request`
3. Staff backend creates alert
4. Return acknowledgment to guest

**Error Responses:**
- `404 Not Found`: Session not found
- `500 Internal Server Error`: Request failed (still logged locally)

---

### 10. SAFE ZONE CONFIRMATION

**Endpoint:** `POST /reached-safe-zone`

**Description:** Guest confirms arrival at safe location

**Request:**
```json
{
  "session_id": "sess_abc123def456"
}
```

**Response:** `200 OK`
```json
{
  "message": "safe zone confirmed",
  "session_id": "sess_abc123def456",
  "status": "safe"
}
```

**Changes Made:**
1. Session status updated to "safe" in `guest_sessions`
2. Safety confirmation sent to staff backend: `POST /staff/emergency/guest-safe-confirmation`
3. Staff backend updates headcount/accountability
4. Logged for audit trail

**Error Responses:**
- `404 Not Found`: Session not found
- `500 Internal Server Error`: Update failed

---

### 11. GET NOTIFICATIONS

**Endpoint:** `GET /notifications`

**Parameters:**
- `floor_id` (query): Floor identifier

**Description:** Get alerts/notifications from staff backend

**Response:** `200 OK`
```json
{
  "floor_id": "floor_1",
  "notifications": [
    {
      "id": "notif_123",
      "message": "Do not use East Stairwell",
      "priority": "critical",
      "timestamp": "2024-01-01T00:05:00Z"
    },
    {
      "id": "notif_124",
      "message": "All South exits now safe",
      "priority": "info",
      "timestamp": "2024-01-01T00:06:00Z"
    }
  ],
  "count": 2
}
```

**Priority Levels:**
- `critical` - Immediate danger
- `warning` - Important safety info
- `info` - General information

**Error Responses:**
- No direct errors; returns empty list on failure

---

## Helper Endpoints

### GET Available Nodes

**Endpoint:** `GET /available-nodes/{floor_id}`

**Description:** Get selectable nodes for manual location picking

**Response:** `200 OK`
```json
{
  "nodes": [
    {
      "id": "room_101",
      "label": "Conference Room",
      "type": "room",
      "position": null
    },
    {
      "id": "room_102",
      "label": "Meeting Room",
      "type": "room",
      "position": null
    }
  ]
}
```

---

### GET Session Details

**Endpoint:** `GET /session/{session_id}`

**Description:** Get detailed session information

**Response:** `200 OK`
```json
{
  "session_id": "sess_abc123",
  "room_id": "101",
  "floor_id": "floor_1",
  "current_node": "corridor_a",
  "status": "evacuating",
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:05:00Z"
}
```

---

## Error Codes

```
200 OK                  Successful request
201 Created            Resource created
400 Bad Request        Invalid input
404 Not Found          Resource not found
500 Internal Server Error  Server error
503 Service Unavailable    Database/service down
```

---

## Request/Response Headers

**Request:**
```
Content-Type: application/json
Authorization: Optional (implement as needed)
```

**Response:**
```
Content-Type: application/json
X-Request-ID: Unique request identifier (recommended)
```

---

## Rate Limiting (Recommended for Production)

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 99
X-RateLimit-Reset: 1234567890
```

---

## Timeout Values

- Session creation: 10 seconds
- Path generation: 5 seconds
- Database operations: 2 seconds
- Staff backend calls: 10 seconds

---

## Data Types

**Session Status:**
- `active` - Session in progress
- `evacuating` - Actively advancing toward exit
- `safe` - Guest reached safe zone
- `abandoned` - Session timed out/abandoned

**Node Types:**
- `room` - Guest room/office
- `corridor` - Hallway/walkway
- `stairs` - Stairwell
- `exit` - Emergency exit
- `safe_zone` - Designated safe assembly area

---

## Example: Complete Evacuation Sequence

```bash
# 1. Start session
POST /session/start
→ session_id, floor_id

# 2. Get floor plan
GET /floor/{floor_id}
→ nodes, edges

# 3. Update location
POST /update-location
→ confirmation

# 4. Check emergency
GET /emergency-status
→ active, blocked_nodes, safe_exits

# 5. Generate route
POST /evacuation-route
→ path, distance

# 6. Get instructions
POST /navigation-steps
→ steps array

# 7. Report step completion (repeat for each step)
POST /step-update
→ next_action

# 8. If needed, reroute
POST /reroute
→ new path

# 9. When safe
POST /reached-safe-zone
→ confirmation
```

---

**For SDK implementations and client libraries, see examples_usage.py**

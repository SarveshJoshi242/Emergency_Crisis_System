# Smart Emergency Management System - Guest Backend

Production-ready backend for guiding guests during emergency evacuations using graph-based navigation and real-time decision handling.

## 🏗️ Project Structure

```
.
├── app/
│   ├── core/                 # Core configuration and database
│   │   ├── config.py        # Settings management
│   │   └── database.py      # MongoDB connection
│   ├── models/
│   │   └── schemas.py       # Pydantic models and validation
│   ├── services/            # Business logic layer
│   │   ├── guest_session.py     # Session management
│   │   ├── floor_graph.py       # Floor plan caching
│   │   ├── navigation.py        # Route computation
│   │   ├── emergency.py         # Emergency state
│   │   ├── interaction.py       # Guest logging
│   │   └── integration.py       # Staff backend API integration
│   ├── routes/
│   │   └── guest.py         # All API endpoints
│   ├── utils/
│   │   └── pathfinding.py   # Dijkstra + BFS algorithms
│   └── main.py              # FastAPI app initialization
├── requirements.txt         # Dependencies
├── .env.example            # Configuration template
└── README.md               # This file
```

## 🔧 Tech Stack

- **Framework**: FastAPI (async Python)
- **Database**: MongoDB Atlas (cloud)
- **Database Driver**: Motor (async MongoDB driver)
- **Pathfinding**: Custom Dijkstra + BFS implementation
- **API Communication**: httpx (async HTTP client)

## 📋 Features

✅ Guest session management  
✅ Floor graph caching from staff backend  
✅ Real-time emergency state synchronization  
✅ Intelligent evacuation route generation (Dijkstra algorithm)  
✅ Step-by-step navigation instructions  
✅ Dynamic rerouting based on changing conditions  
✅ Help request forwarding to staff  
✅ Safe zone confirmation and headcount  
✅ Guest action logging and tracking  
✅ Notification delivery  

## 🚀 Quick Start

### 1. Create Virtual Environment

```bash
python -m venv venv
 source venv/bin/activate  # macOS/Linux
# or
venv\Scripts\activate      # Windows
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

Create `.env` file from template:

```bash
cp .env.example .env
```

Edit `.env` with your MongoDB Atlas credentials:

```
MONGODB_URL=mongodb+srv://user:password@cluster.mongodb.net/?retryWrites=true&w=majority
MONGODB_DB_NAME=emergency_system_guest
STAFF_BACKEND_URL=http://localhost:8001
```

### 4. Run Server

```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Server will be available at: `http://localhost:8000`

API documentation: `http://localhost:8000/docs`

## 📡 API Endpoints

### Session Management
- `POST /guest/session/start` - Create new guest session
- `GET /guest/session/{session_id}` - Get session details
- `GET /guest/available-nodes/{floor_id}` - Available nodes for selection

### Location & Navigation
- `GET /guest/floor/{floor_id}` - Get floor plan with nodes and edges
- `POST /guest/update-location` - Update current position
- `POST /guest/evacuation-route` - Generate evacuation route
- `POST /guest/navigation-steps` - Get step-by-step instructions
- `POST /guest/reroute` - Recalculate route from current position

### Emergency Response
- `GET /guest/emergency-status` - Get emergency state
- `POST /guest/step-update` - Report step completion/reroute/help
- `POST /guest/request-help` - Send help request to staff
- `POST /guest/reached-safe-zone` - Confirm arrival at safe zone

### Information
- `GET /guest/notifications` - Get alerts from staff
- `GET /health` - Health check

## 🔄 Integration with Staff Backend

The guest backend communicates with the staff backend via REST APIs:

### Inbound Data
- **Floor Plans**: Retrieved and cached from `/staff/building/floor/{floor_id}/graph`
- **Emergency State**: Synced from `/staff/emergency/current-state`
- **Notifications**: Fetched from `/staff/emergency/notifications`
- **Room Mappings**: Retrieved from `/staff/building/room/{room_id}`

### Outbound Data
- **Help Requests**: Sent to `/staff/emergency/guest-help-request`
- **Safe Confirmations**: Sent to `/staff/emergency/guest-safe-confirmation`

## 💾 Database Schema

### Collections

**guest_sessions**
```json
{
  "_id": ObjectId,
  "session_id": "sess_abc123",
  "room_id": "101",
  "floor_id": "floor_1",
  "current_node": "room_101",
  "status": "active",
  "created_at": 2024-01-01T00:00:00Z,
  "updated_at": 2024-01-01T00:05:00Z
}
```

**floor_graphs**
```json
{
  "_id": ObjectId,
  "floor_id": "floor_1",
  "nodes": [
    { "id": "room_101", "label": "Conference Room", "type": "room" },
    { "id": "exit_south", "label": "South Exit", "type": "exit" }
  ],
  "edges": [
    { "from": "room_101", "to": "corridor_a", "weight": 5 }
  ]
}
```

**emergency_state**
```json
{
  "_id": ObjectId,
  "is_active": true,
  "emergency_type": "fire",
  "affected_floors": ["floor_1", "floor_2"],
  "blocked_nodes": ["room_105", "stairs_east"],
  "safe_exits": ["exit_south", "exit_north"],
  "updated_at": 2024-01-01T00:10:00Z
}
```

**guest_logs**
```json
{
  "_id": ObjectId,
  "session_id": "sess_abc123",
  "step": 3,
  "action": "completed",
  "node_id": "corridor_a",
  "timestamp": 2024-01-01T00:05:30Z
}
```

## 🧮 Pathfinding Algorithm

The system uses **Dijkstra's algorithm** (with BFS fallback) for computing evacuation routes:

- **Weighted shortest path**: Considers edge weights (distances)
- **Obstacle avoidance**: Automatically avoids blocked nodes
- **Multiple exits**: Chooses closest safe exit
- **Real-time adaptation**: Recomputes routes as emergency state changes

Example route: `[room_101] → [corridor_a] → [stairs_1] → [exit_south]`

## 🔐 Development & Production

### Development
```bash
DEBUG=True python -m uvicorn app.main:app --reload
```

### Production
```bash
DEBUG=False uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

Use a production ASGI server like Gunicorn:
```bash
pip install gunicorn
gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app
```

## 📝 Example Usage Flow

```
1. Guest starts session
   POST /guest/session/start
   → returns session_id, floor_id

2. Get floor plan
   GET /guest/floor/{floor_id}
   → returns nodes and edges

3. Guest selects location
   POST /guest/update-location
   → updates current_node

4. Emergency triggered (staff backend)
   Emergency state updated in MongoDB

5. Guest requests route
   POST /guest/evacuation-route
   → returns [room_101, corridor_a, stairs_1, exit_south]

6. Get navigation steps
   POST /guest/navigation-steps
   → returns ["Exit room", "Go to corridor", "Take stairs", "Use exit"]

7. After each step, report status
   POST /guest/step-update
   → action: completed | reroute | help

8. If reroute needed
   POST /guest/reroute
   → returns updated route

9. Reach safe zone
   POST /guest/reached-safe-zone
   → updates status, notifies staff
```

## 🧪 Testing

Create test files in `tests/` directory:

```bash
pytest tests/
```

Example test pattern:
```python
@pytest.mark.asyncio
async def test_session_creation():
    session = await session_service.create_session("101", "floor_1")
    assert session.session_id is not None
```

## 🤝 Contributing

1. Follow modular architecture
2. Add docstrings to all functions
3. Use type hints
4. Test async code properly
5. Keep services focused on single responsibility

## 📚 Documentation

- API documentation: `http://localhost:8000/docs` (Swagger UI)
- Alternative docs: `http://localhost:8000/redoc` (ReDoc)

## 🚨 Error Handling

The backend includes comprehensive error handling:

- **404 Not Found**: Session or resource not found
- **400 Bad Request**: Invalid input
- **500 Internal Server Error**: Server-side failures
- **Graceful degradation**: Returns sensible defaults when staff backend unavailable

## 🔧 Configuration

Key settings in `.env`:

| Variable | Default | Purpose |
|----------|---------|---------|
| `MONGODB_URL` | - | MongoDB Atlas connection string |
| `STAFF_BACKEND_URL` | `http://localhost:8001` | Staff backend address |
| `PATHFINDING_ALGORITHM` | `dijkstra` | Route algorithm (dijkstra or bfs) |
| `DEBUG` | `False` | Debug mode |

## 📊 Performance Considerations

- **Caching**: Floor graphs cached locally to reduce API calls
- **Async I/O**: All database and API calls are non-blocking
- **Edge weights**: Enables optimal path selection based on distance/risk
- **Connection pooling**: Motor handles MongoDB connection pooling

## 🛑 Shutdown

The application gracefully handles shutdown:
- Closes MongoDB connections
- Completes in-flight requests
- Logs all shutdown events

## 📞 Support

For issues or questions:
1. Check MongoDB connection
2. Verify staff backend is accessible
3. Check application logs

## 📄 License

[Your License Here]

---

**Built for reliable, real-time emergency guidance** 🚨

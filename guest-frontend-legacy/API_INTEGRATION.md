# API Integration Mapping

## Staff Backend Integration

### Alert Management
| Backend Endpoint | Method | Frontend Hook | Component | Status |
|------------------|--------|---------------|-----------|--------|
| `/alert/status` | GET | `useStaffAlerts()` | StaffDashboard | ✅ Polling 3s |
| `/alert/resolve` | POST | `useStaffAlerts().resolveAlert` | StaffDashboard | ✅ Click button |
| `/alert/manual` | POST | `useEmergencyActions().createManualAlert` | (Ready to use) | ✅ Available |

### Task Management
| Backend Endpoint | Method | Frontend Hook | Component | Status |
|------------------|--------|---------------|-----------|--------|
| `/tasks` | GET | `useStaffTasks()` | StaffDashboard | ✅ Polling 4s |
| `/tasks/{id}/complete` | POST | `useStaffTasks().completeTask` | StaffDashboard | ✅ Click button |

### Staff Directory
| Backend Endpoint | Method | Frontend Hook | Component | Status |
|------------------|--------|---------------|-----------|--------|
| `/staff` | GET | `useStaffList()` | StaffDashboard | ✅ One-time load |
| `/staff` | POST | `useStaffList().registerStaff` | (Ready to use) | ✅ Available |

### Emergency Trigger
| Backend Endpoint | Method | Frontend Hook | Component | Status |
|------------------|--------|---------------|-----------|--------|
| `/staff/emergency/trigger-room` | POST | `useEmergencyActions().triggerRoomEmergency` | (Ready to use) | ✅ Available |

### Floor Graph Operations
| Backend Endpoint | Method | Frontend Hook | Component | Status |
|------------------|--------|---------------|-----------|--------|
| `/floor/{id}/graph` | GET | `useFloorGraph().graph` | FloorGraphEditor | ✅ Initial load |
| `/floor/{id}/graph` | PUT | `useFloorGraph().updateGraph` | FloorGraphEditor | ✅ Save button |
| `/floor/{id}/graph/node` | PATCH | `useFloorGraph().addNode` | FloorGraphEditor | ✅ Add mode |
| `/floor/{id}/graph/node` | DELETE | `useFloorGraph().deleteNode` | FloorGraphEditor | ✅ Delete button |
| `/floor/{id}/graph/edge` | PATCH | `useFloorGraph().addEdge` | FloorGraphEditor | ✅ Connect mode |
| `/floor/{id}/graph/edge` | DELETE | `useFloorGraph().deleteEdge` | FloorGraphEditor | ✅ Auto-handled |

---

## Guest Backend Integration

### Session Management
| Backend Endpoint | Method | Frontend Hook | Component | Status |
|------------------|--------|---------------|-----------|--------|
| `/guest/session/start` | POST | `useGuestSession().startSession` | GuestEntry | ✅ Room selection |

### Floor Plans
| Backend Endpoint | Method | Frontend Hook | Component | Status |
|------------------|--------|---------------|-----------|--------|
| `/guest/floor/{id}` | GET | `useFloorPlan()` | (Ready to use) | ✅ Available |
| `/guest/available-nodes/{id}` | GET | `useAvailableNodes()` | GuestEntry | ✅ Room list |

### Emergency Management
| Backend Endpoint | Method | Frontend Hook | Component | Status |
|------------------|--------|---------------|-----------|--------|
| `/guest/emergency-status` | GET | `useEmergencyStatus()` | EvacuationPage | ✅ Polling 3.5s |

### Evacuation Routing
| Backend Endpoint | Method | Frontend Hook | Component | Status |
|------------------|--------|---------------|-----------|--------|
| `/guest/evacuation-route` | POST | `useEvacuationRoute()` | EvacuationPage | ✅ Polling 2.5s |
| `/guest/reroute` | POST | `useEvacuationRoute().reroute` | EvacuationPage | ✅ Reroute button |

### Navigation
| Backend Endpoint | Method | Frontend Hook | Component | Status |
|------------------|--------|---------------|-----------|--------|
| `/guest/navigation-steps` | POST | `useNavigationSteps()` | (Ready to use) | ✅ Available |
| `/guest/step-update` | POST | (Custom) | (Ready to use) | ✅ Available |

### Guest Actions
| Backend Endpoint | Method | Frontend Hook | Component | Status |
|------------------|--------|---------------|-----------|--------|
| `/guest/update-location` | POST | `useGuestSession().updateLocation` | (Ready to use) | ✅ Available |
| `/guest/request-help` | POST | `useGuestActions().requestHelp` | EvacuationPage | ✅ Help button |
| `/guest/reached-safe-zone` | POST | `useGuestActions().reachedSafety` | EvacuationPage | ✅ Safe button |
| `/guest/notifications` | GET | (Not yet implemented) | (Ready to use) | ⏳ Available |

---

## Data Flow Examples

### Example 1: Staff Alert Resolution
```
User clicks "Resolve" on alert in StaffDashboard
        ↓
resolveAlert(alert_id)
        ↓
POST /alert/resolve { alert_id: "..." }
        ↓
Backend returns { status: "RESOLVED" }
        ↓
Frontend: removeAlert from state
        ↓
Re-render: alert disappears from list
```

### Example 2: Guest Evacuation Route Update
```
Guest enters room and starts evacuation
        ↓
POST /guest/session/start { room_id: "..." }
        ↓
Backend: Creates session, returns session_id
        ↓
Auto-poll: POST /guest/evacuation-route { session_id: "..." } (every 2.5s)
        ↓
Backend: Calculates route avoiding blocked nodes (Dijkstra)
        ↓
Display: "You are 45m from safety"
        ↓
If blocked_nodes change in next poll:
  → Auto-update route display
  → Show "Route updated" message
  → EvacuationPage re-renders with new path
```

### Example 3: Floor Graph Edit
```
Staff opens FloorGraphEditor for floor_1
        ↓
GET /floor/floor_1/graph
        ↓
Render: Canvas with nodes and edges
        ↓
Staff adds 3 nodes, deletes 1, adds 2 edges (all local state)
        ↓
Staff clicks "Save"
        ↓
PUT /floor/floor_1/graph {
  nodes: [...all 4 nodes with new positions...],
  edges: [...all updated edges...]
}
        ↓
Backend: Validates graph, saves to database
        ↓
Frontend: Show "Graph saved successfully"
```

---

## Error Handling

All hooks include error states:

```typescript
const { data, loading, error, refetch } = useStaffAlerts();

if (error) {
  // Display: "Failed to fetch alerts: [error message]"
  // User can retry with refetch()
}
```

Common error scenarios handled:
- Network timeout (3s for alerts, 4s for tasks)
- Invalid session (guest session expired)
- Backend server error (500)
- Invalid request (400)
- Not found (404)

---

## Testing Checklist

### Staff Dashboard
- [ ] Alerts display with correct severity color
- [ ] Clicking "Resolve" removes alert
- [ ] Tasks show pending/done status
- [ ] Clicking "Complete" marks task done
- [ ] Staff list displays all members
- [ ] Alerts refresh every 3 seconds (check network tab)
- [ ] Tasks refresh every 4 seconds

### Floor Graph Editor
- [ ] Canvas renders loaded graph
- [ ] Can drag nodes to new positions
- [ ] "Add" mode creates new nodes at click
- [ ] "Connect" mode links two nodes
- [ ] Delete button removes selected node
- [ ] "Save" button sends PUT request
- [ ] Zoom in/out adjusts canvas view

### Guest Entry
- [ ] Floor dropdown populates
- [ ] Selecting floor loads rooms
- [ ] Clicking room selects it
- [ ] "Begin Navigation" starts session
- [ ] Redirects to evacuation page

### Evacuation
- [ ] Progress bar updates as steps advance
- [ ] Distance to safety displays
- [ ] Blocked areas shown
- [ ] "Reroute" recalculates path
- [ ] "Help" button sends help request
- [ ] Emergency status updates every 3.5s
- [ ] Route polling every 2.5s

---

## Performance Metrics

**Target Response Times:**
- Alert fetch: <500ms (polled 3s)
- Task fetch: <500ms (polled 4s)
- Emergency status: <300ms (polled 3.5s)
- Route calculation: <1s (polled 2.5s)

**Network Usage (Estimated):**
- Staff: ~5 requests/minute (alerts + tasks)
- Guest: ~24 requests/minute (emergency + route polling)

**Memory:**
- Session: ~2-5 MB per active user
- No unnecessary re-renders (React.memo on components)

---

## Backwards Compatibility

All existing pages remain functional:
- `/dashboard` → Still works (legacy support)
- `/evacuation` → Enhanced with backend
- `/safe` → Reachable from evacuation flow

New pages don't break existing flows:
- Can access any page directly via URL
- All hooks handle missing data gracefully
- Fallback UI shown during loads

---

## Future Enhancements (Not Implemented)

These features exist in the backend but aren't integrated yet:
- `/webhook/ai-danger-detection` - AI danger detection
- `/fire/input` - Fire system integration
- `/guest/notifications` - Staff announcements
- WebSocket real-time feeds (using polling instead)
- Multi-language support
- Accessibility enhancements

---

## Known Limitations

1. **No real-time WebSocket updates** - Using polling instead (sufficient for requirements)
2. **Floor list hardcoded** - Should fetch from `/floor` listing endpoint (future)
3. **Single staff session** - No staff login/auth (design choice per MVP)
4. **Evacuation steps** - Using path node IDs instead of generated steps (backend supports step generation)
5. **Heatmap visualization** - Not integrated (backend supports it)

All limitations are graceful and don't affect core functionality.

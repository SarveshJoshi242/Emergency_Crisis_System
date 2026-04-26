# Frontend Refactor - Architecture Documentation

## Overview
Complete refactor of the guest frontend to cleanly integrate with existing backend APIs (staff backend + guest backend) with NO backend modifications.

---

## 🗑️ Deletions
- **LandingPage.tsx** - Removed the emergency assistance system splash screen
- Updated routes to remove `/` → LandingPage mapping

---

## 🏗️ New Architecture

### Entry Point: Mode Selector (/)
New landing page that lets users choose their role:
- **Staff Mode** → `/staff-dashboard` 
- **Guest Mode** → `/guest-entry`

```
ModeSelector (/)
├── Staff Path
│   ├── StaffDashboard (/staff-dashboard)
│   │   └── FloorGraphEditor (/floor-editor/:floorId)
│   └── Polling: Alerts (3s), Tasks (4s), Emergency Status (3.5s)
│
└── Guest Path
    ├── GuestEntry (/guest-entry)
    │   └── Evacuation (/evacuation)
    │       └── SafeZone (/safe)
    └── Polling: Emergency Status (3.5s), Route Updates (2.5s)
```

---

## 📁 New API Layer

### API Configuration (`src/api/config.ts`)
- Centralized API endpoints for both backends
- Polling interval constants (3-5 seconds)
- Environment-aware URL configuration

### Staff API Client (`src/api/staffClient.ts`)
**Endpoints:**
- **Alerts**: GET /alert/status, POST /alert/manual, POST /alert/resolve
- **Tasks**: GET /tasks, POST /tasks/{id}/complete
- **Staff**: POST /staff, GET /staff, POST /staff/emergency/trigger-room
- **Floor Graphs**: GET, PUT, PATCH, DELETE on /floor/{id}/graph/*

**Features:**
- Full type safety with TypeScript interfaces
- Error handling with descriptive messages
- Support for all CRUD operations on floor graphs

### Guest API Client (`src/api/guestClient.ts`)
**Endpoints:**
- **Session**: POST /guest/session/start
- **Floor Plans**: GET /guest/floor/{id}
- **Location**: POST /guest/update-location
- **Emergency**: GET /guest/emergency-status
- **Routing**: POST /guest/evacuation-route, /guest/reroute
- **Navigation**: POST /guest/navigation-steps, /guest/step-update
- **Actions**: POST /guest/request-help, /guest/reached-safe-zone

**Features:**
- Full type safety with backend schemas
- Support for multi-floor buildings
- Dijkstra pathfinding integration (backend-handled)

---

## 🎣 State Management Hooks

### Staff Hooks (`src/hooks/useStaffBackend.ts`)
1. **useStaffAlerts()** - Polls alerts every 3 seconds
   - auto-resolves, displays severity
   
2. **useStaffTasks(floorId?)** - Polls tasks every 4 seconds
   - Filter by floor, mark complete
   
3. **useStaffList()** - One-time staff fetch
   
4. **useFloorGraph(floorId)** - Full graph management
   - CRUD operations on nodes/edges
   - Bulk graph updates
   - Local caching during edits
   
5. **useEmergencyActions()** - Trigger emergencies manually

### Guest Hooks (`src/hooks/useGuestBackend.ts`)
1. **useGuestSession()** - Session lifecycle
   
2. **useFloorPlan(floorId)** - Floor graph caching
   
3. **useEmergencyStatus()** - Polls every 3.5 seconds
   
4. **useEvacuationRoute(sessionId)** - Polls every 2.5 seconds during evacuation
   - Auto-updates when path changes
   
5. **useNavigationSteps(path)** - Convert path nodes to instructions
   
6. **useGuestActions()** - Help requests, safety confirmation, rerouting

---

## 🎨 Components

### Staff Frontend

#### StaffDashboard (`src/app/pages/StaffDashboard.tsx`)
**Real-time alert monitoring:**
- Active alerts with severity indicators (CRITICAL/HIGH/MEDIUM)
- Color-coded by risk level
- Display danger zones, source rooms, and escalation time

**Task management panel:**
- Grouped by parent alert
- Shows task type, status, assignments
- Complete button for pending tasks

**Staff list:**
- Registered staff members with roles
- Quick reference for coordination

**Features:**
- 3-second polling for fresh data
- One-click alert resolution
- Task completion tracking

#### FloorGraphEditor (`src/app/pages/FloorGraphEditor.tsx`)
**Interactive canvas-based editor:**
- Node types: room (blue), corridor (amber), exit (green), danger (red)
- Drag to reposition nodes
- Multiple editing modes: select, add, connect
- Real-time edge/node visualization

**Operations:**
- Add nodes at cursor position
- Delete selected nodes
- Connect nodes with edges
- Zoom in/out for large floors
- Bulk save (sends entire graph to backend)

**Validation:**
- Node existence checks
- Edge validation before save

### Guest Frontend

#### ModeSelector (`src/app/pages/ModeSelector.tsx`)
Entry point with role selection.

#### GuestEntry (`src/app/pages/GuestEntry.tsx`)
**Room/location selection:**
- Multi-floor support
- Dynamic room loading from backend /guest/available-nodes
- Converts backend nodes to familiar UI format

**Features:**
- Floor dropdown
- Location list (rooms/corridors)
- Session initialization
- Error display

#### EvacuationPage (`src/app/pages/EvacuationPage.tsx`)
**Three-phase evacuation:**
1. **Room Selection** - Guest picks starting location
2. **Active Evacuation** - Step-by-step navigation
3. **Safe Zone** - Confirmation screen

**Features:**
- Real-time progress tracking
- Distance to safety display
- Blocked area warnings
- Reroute button for path changes
- Help request button (trapped/injured/lost)
- Continuous emergency status polling

---

## 🔄 Data Flow Diagrams

### Staff Alert Workflow
```
Backend Fire/Alert Event
         ↓
StaffDashboard polls /alert/status (every 3s)
         ↓
Display active alerts with risk level
         ↓
Staff clicks "Resolve" → POST /alert/resolve
         ↓
Alert removed from list
```

### Guest Evacuation Workflow
```
Guest selects room
         ↓
POST /guest/session/start {room_id}
         ↓
GET /guest/emergency-status (polling every 3.5s)
         ↓
POST /guest/evacuation-route {session_id}
         ↓
Display path with distance
         ↓
Guest moves → POST /guest/update-location
         ↓
Poll /guest/evacuation-route (every 2.5s)
         ↓
If blocked zones change → auto-reroute
```

### Floor Graph Edit Workflow
```
Staff opens /floor-editor/floor_1
         ↓
GET /floor/floor_1/graph
         ↓
Display nodes/edges on canvas
         ↓
Staff edits locally (add/delete/move)
         ↓
Staff clicks "Save"
         ↓
PUT /floor/floor_1/graph {nodes[], edges[]}
         ↓
Confirmation
```

---

## ⚡ Polling Strategy

| Feature | Interval | Purpose |
|---------|----------|---------|
| Staff Alerts | 3s | Real-time emergency tracking |
| Staff Tasks | 4s | Fresh task assignments |
| Emergency Status (Guest) | 3.5s | Detect danger zone changes |
| Evacuation Route (Guest) | 2.5s | Detect blocked paths |

**Why polling instead of WebSockets:**
- Simpler implementation (no server-side WebSocket infrastructure needed)
- Respects existing API design
- Sufficient for 2.5-4s response time requirements
- Easier fallback/error handling

---

## 🔐 Type Safety

All API operations are fully typed:

```typescript
// Staff
Alert, Task, Staff, Floor, FloorGraph, GraphNode, GraphEdge
staffClient.resolveAlert(alertId: string): Promise<Alert>
staffClient.updateFloorGraph(floorId: string, graph: FloorGraph): Promise<FloorGraph>

// Guest
GuestSession, FloorPlan, EmergencyStatus, EvacuationRoute, NavigationStep, FloorNode
guestClient.startSession(roomId: string): Promise<GuestSession>
guestClient.getEvacuationRoute(sessionId: string): Promise<EvacuationRoute>
```

---

## 🚫 NOT MODIFIED
- ✅ Zero backend API changes
- ✅ Zero backend schema changes
- ✅ Zero backend endpoint modifications
- ✅ All existing business logic preserved

---

## 📦 Context Integration

### EvacuationContext (`src/app/context/EvacuationContext.tsx`)
**Updated to support backend data:**
- New: `setSession()` - Store backend GuestSession
- New: `setAvailableRooms()` - Populate rooms from backend nodes
- New: `setEvacuationSteps()` - Update steps from backend route
- Preserved: UI state (emergencyActive, voiceGuidance, etc.)
- Removed: Hardcoded room list (now fetched from backend)

---

## 🎯 Features Implemented

### Staff Features
✅ Real-time alert monitoring with polling
✅ Task assignment visualization (pending vs done)
✅ Interactive floor graph editor with drag-drop
✅ Manual emergency trigger capability
✅ Alert resolution workflow
✅ Staff member directory
✅ Color-coded severity indicators
✅ Multi-floor support

### Guest Features
✅ Room/location selection from backend
✅ Session-based evacuation tracking
✅ Real-time route updates
✅ Danger zone avoidance
✅ Blocked path detection
✅ Reroute capability
✅ Help request system
✅ Step-by-step progress tracking
✅ Distance-to-safety display

---

## 🔧 Configuration

Set backend URLs via environment variables:
```
REACT_APP_STAFF_BACKEND_URL=http://localhost:8001
REACT_APP_GUEST_BACKEND_URL=http://localhost:8000
```

Default to localhost if not set (development mode).

---

## 📝 File Summary

**New Files Created:**
- `src/api/config.ts` - API configuration
- `src/api/staffClient.ts` - Staff API client
- `src/api/guestClient.ts` - Guest API client
- `src/hooks/useStaffBackend.ts` - Staff state hooks
- `src/hooks/useGuestBackend.ts` - Guest state hooks
- `src/app/pages/ModeSelector.tsx` - Role selection
- `src/app/pages/StaffDashboard.tsx` - Staff main page
- `src/app/pages/FloorGraphEditor.tsx` - Floor editor
- `src/app/pages/GuestEntry.tsx` - Guest room selection

**Modified Files:**
- `src/app/routes.tsx` - Updated routing
- `src/app/context/EvacuationContext.tsx` - Backend integration
- Deleted: `src/app/pages/LandingPage.tsx`

**Preserved:**
- All existing UI components (buttons, cards, banners, etc.)
- Existing page flows (EvacuationPage, SafeZonePage)
- Existing styling and theme

---

## ✅ Quality Assurance

- ✅ All data types match backend schemas
- ✅ Polling intervals configured appropriately
- ✅ Error handling with user feedback
- ✅ Loading states during async operations
- ✅ State persisted across navigation
- ✅ Fallback behavior when APIs unavailable
- ✅ TypeScript strict mode compliance

---

## 🚀 Deployment

1. Install dependencies: `npm install`
2. Set environment variables for backend URLs
3. Run development: `npm run dev`
4. Build for production: `npm run build`

Visit `localhost:3000` to access the mode selector.

---

## 📚 Integration Guide

### For Staff Users
1. Navigate to Mode Selector
2. Click "Staff Mode"
3. View active alerts and tasks with 3-4 second refresh
4. Click "Floor Graph Editor" to edit floor layouts
5. Save changes to backend

### For Guest Users
1. Navigate to Mode Selector
2. Click "Guest Mode"
3. Select your floor and current location
4. Follow step-by-step evacuation guidance
5. System automatically reroutes if danger zones change

---

## Notes
- Guest backend fetches room→floor mapping from staff backend as documented
- Floor graphs are complete objects (not individual node updates)
- Task assignment is optional (assigned_to field)
- All polling honors backend rate limits
- Graceful degradation if components fail to load

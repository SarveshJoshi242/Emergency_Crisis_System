// Backend API base URLs
export const GUEST_BACKEND_URL = import.meta.env.VITE_GUEST_BACKEND_URL || 'http://localhost:8000';

// ─── Guest API Endpoints ──────────────────────────────────────────────────────
// These match the actual guest backend routes exactly.
// PUBLIC endpoints (no JWT needed):
//   /guest/check-in   — create session
//   /guest/rooms      — list all rooms
//   /guest/path       — get evacuation path (polling)
//   /guest/emergency-status — current state
// ─────────────────────────────────────────────────────────────────────────────

export const GUEST_API = {
  // ── Public ─────────────────────────────────────────────────────────────────

  // POST { room_id } → { session_id, room_id, floor_id, status }
  CHECK_IN: `${GUEST_BACKEND_URL}/guest/check-in`,

  // GET → [{ room_id, floor_id, label, floor_name }]
  ROOMS_LIST: `${GUEST_BACKEND_URL}/guest/rooms`,

  // GET ?session_id=X → { steps: [{instruction, node}], is_active }
  PATH_GET: `${GUEST_BACKEND_URL}/guest/path`,

  // GET → { active, status, emergency_type, ... }
  EMERGENCY_STATUS: `${GUEST_BACKEND_URL}/guest/emergency-status`,

  // ── Session ────────────────────────────────────────────────────────────────

  // GET /guest/session/{session_id}
  SESSION_GET: (sessionId: string) => `${GUEST_BACKEND_URL}/guest/session/${sessionId}`,

  // ── Evacuation ────────────────────────────────────────────────────────────

  // POST { session_id } → new path (EvacuationRouteResponse)
  REROUTE: `${GUEST_BACKEND_URL}/guest/reroute`,

  // POST { session_id } → { message }
  REACHED_SAFE_ZONE: `${GUEST_BACKEND_URL}/guest/reached-safe-zone`,

  // GET /guest/available-nodes/{floorId}  (still available for advanced use)
  AVAILABLE_NODES: (floorId: string) => `${GUEST_BACKEND_URL}/guest/available-nodes/${floorId}`,
};

// ─── Polling intervals (ms) ───────────────────────────────────────────────────
export const POLLING = {
  EMERGENCY_STATUS: 3000,  // dashboard polls every 3s
  PATH:             3000,  // evacuation polls path every 3s
};

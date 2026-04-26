/**
 * Guest API client.
 *
 * All methods are no-auth — the backend's new public endpoints don't need JWT.
 * session_id is stored in localStorage by checkIn() and read back by callers.
 *
 * Error philosophy:
 *   - All methods throw on non-2xx so callers can catch and show UI error state.
 *   - No silent swallowing of errors.
 */
import { GUEST_API } from './config';

// ─── Shared types ────────────────────────────────────────────────────────────

export interface GuestSession {
  session_id: string;
  room_id: string;
  floor_id: string;
  status: string;
  current_node?: string;
  created_at?: string;
}

export interface PathStep {
  instruction: string;
  node: string;
}

export interface PathResponse {
  steps: PathStep[];
  is_active: boolean;
}

export interface EmergencyStatusResponse {
  active: boolean;
  /** 'active' | 'inactive' — normalized by this client */
  status: 'active' | 'inactive';
  emergency_type?: string | null;
  affected_floors: string[];
  blocked_nodes: string[];
  safe_exits: string[];
  updated_at?: string;
}

export interface FloorNode {
  id: string;
  label: string;
  type: string;
}

export interface RoomEntry {
  room_id: string;
  floor_id: string;
  label: string;
  floor_name: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

async function _fetch<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
    ...options,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? body.message ?? detail;
    } catch { /* ignore parse errors */ }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

// ─── Guest API Client ─────────────────────────────────────────────────────────

export const guestClient = {
  /**
   * Public check-in: resolve room → floor, create session, persist session_id.
   * No JWT required.
   */
  async checkIn(roomId: string): Promise<GuestSession> {
    const session = await _fetch<GuestSession>(GUEST_API.CHECK_IN, {
      method: 'POST',
      body: JSON.stringify({ room_id: roomId }),
    });
    // Persist for AppLoader to pick up on page refresh
    localStorage.setItem('session_id', session.session_id);
    return session;
  },

  /**
   * Retrieve an existing session by ID.
   * Used by AppLoader to restore state on page refresh.
   */
  async getSession(sessionId: string): Promise<GuestSession> {
    return _fetch<GuestSession>(GUEST_API.SESSION_GET(sessionId));
  },

  /**
   * Get current emergency status.
   * Normalizes response to always have `status: 'active' | 'inactive'`.
   */
  async getEmergencyStatus(): Promise<EmergencyStatusResponse> {
    const data = await _fetch<Record<string, unknown>>(GUEST_API.EMERGENCY_STATUS);

    // Backend returns { active: bool, status: 'active'|'inactive', ... }
    // Normalize to guarantee the `status` field even if older backend returns only `active`.
    const isActive = Boolean(data.active ?? data.is_active ?? false);
    return {
      active:          isActive,
      status:          isActive ? 'active' : 'inactive',
      emergency_type:  (data.emergency_type as string | null) ?? null,
      affected_floors: (data.affected_floors as string[]) ?? [],
      blocked_nodes:   (data.blocked_nodes as string[])   ?? [],
      safe_exits:      (data.safe_exits as string[])      ?? [],
      updated_at:      data.updated_at as string | undefined,
    };
  },

  /**
   * Get evacuation path for a session.
   * Polls GET /guest/path?session_id=...
   */
  async getPath(sessionId: string): Promise<PathResponse> {
    const url = `${GUEST_API.PATH_GET}?session_id=${encodeURIComponent(sessionId)}`;
    const data = await _fetch<PathResponse>(url);
    // Cache steps to localStorage for offline fallback (EvacuationPage uses this)
    if (data.steps && data.steps.length > 0) {
      try {
        localStorage.setItem('offline_path', JSON.stringify(data.steps));
      } catch { /* quota exceeded — ignore */ }
    }
    return data;
  },

  /**
   * Request reroute for a session.
   * POST /guest/reroute — backend recalculates path around new obstacles.
   */
  async reroute(sessionId: string): Promise<PathResponse> {
    // The existing reroute endpoint returns an EvacuationRouteResponse { path, distance }
    // We convert it to PathResponse format the UI expects.
    interface RerouteResponse { path?: string[]; steps?: PathStep[]; distance?: number; }
    const data = await _fetch<RerouteResponse>(GUEST_API.REROUTE, {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId }),
    });

    // If backend already returns steps, use them directly
    if (data.steps) {
      return { steps: data.steps, is_active: true };
    }

    // Otherwise, convert path array → minimal steps
    const path = data.path ?? [];
    const steps: PathStep[] = path.map((node, i) => ({
      node,
      instruction: i === 0
        ? `Leave ${node}`
        : i === path.length - 1
          ? `EXIT through ${node} — you are safe!`
          : `Move to ${node}`,
    }));
    return { steps, is_active: true };
  },

  /**
   * Confirm guest reached safe zone.
   * POST /guest/reached-safe-zone
   */
  async confirmSafeZone(sessionId: string): Promise<void> {
    await _fetch(GUEST_API.REACHED_SAFE_ZONE, {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId }),
    });
    // Clear cached path now that guest is safe
    localStorage.removeItem('offline_path');
  },

  /**
   * Public rooms list — used by GuestEntry to build the room picker.
   * No JWT required.
   * Returns all rooms from all floor graphs.
   */
  async getRooms(): Promise<RoomEntry[]> {
    return _fetch<RoomEntry[]>(GUEST_API.ROOMS_LIST);
  },

  /**
   * Get available nodes for a specific floor.
   * Still available for advanced use (e.g. location update UI).
   * Returns FloorNode[] filtered from the floor graph.
   */
  async getAvailableNodes(floorId: string): Promise<FloorNode[]> {
    interface AvailableNodesResponse { nodes: FloorNode[] }
    const data = await _fetch<AvailableNodesResponse>(GUEST_API.AVAILABLE_NODES(floorId));
    return data.nodes ?? [];
  },

  /**
   * Request immediate staff help — broadcasts via WebSocket to staff dashboard.
   * Calls the staff backend directly since the endpoint lives on port 8001.
   * No auth required (the /guest-api/help-requests endpoint is public).
   */
  async requestHelp(params: {
    sessionId: string;
    currentNode: string;
    issue: string;
    floorId?: string | null;
  }): Promise<void> {
    const STAFF_BACKEND = import.meta.env.VITE_STAFF_BACKEND_URL ?? 'http://localhost:8001';
    await _fetch<unknown>(`${STAFF_BACKEND}/guest-api/help-requests`, {
      method: 'POST',
      body: JSON.stringify({
        session_id:   params.sessionId,
        current_node: params.currentNode,
        issue:        params.issue,
        floor_id:     params.floorId ?? null,
      }),
    });
  },

  /**
   * Fetch active notifications (alerts and broadcast messages)
   */
  async getNotifications(floorId?: string): Promise<{ alerts: any[], messages: any[] }> {
    const STAFF_BACKEND = import.meta.env.VITE_STAFF_BACKEND_URL ?? 'http://localhost:8001';
    const url = floorId 
      ? `${STAFF_BACKEND}/guest-api/notifications?floor_id=${encodeURIComponent(floorId)}`
      : `${STAFF_BACKEND}/guest-api/notifications`;
    return _fetch(url);
  }
};


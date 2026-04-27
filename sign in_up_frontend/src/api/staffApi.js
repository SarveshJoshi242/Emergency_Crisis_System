// ============================================================
//  src/api/staffApi.js
//  All HTTP calls to the Staff Backend (port 8001)
// ============================================================

const BASE = import.meta.env.VITE_STAFF_API_URL || 'http://localhost:8001';

function getToken() {
  return localStorage.getItem('staff_access_token');
}

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request(method, path, body = null, extraHeaders = {}) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...extraHeaders },
  };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(`${BASE}${path}`, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Auth ─────────────────────────────────────────────────────
export const staffLogin = (email, password) =>
  request('POST', '/auth/staff/login', { email, password });

export const staffRegister = (name, email, password) =>
  request('POST', '/auth/staff/register', { name, email, password });

export const staffRefresh = (refresh_token) =>
  request('POST', '/auth/refresh', { refresh_token });

export const staffLogout = (refresh_token) =>
  request('POST', '/auth/logout', { refresh_token });

export const getMe = () => request('GET', '/auth/me');

// ── Alerts ───────────────────────────────────────────────────
export const getAlerts = () => request('GET', '/alert/status');
export const resolveAlert = (id) => request('POST', '/alert/resolve', { alert_id: id });
export const resolveAllAlerts = () => request('POST', '/alert/resolve-all');
export const triggerDemo = () => request('POST', '/alert/demo');
export const startEmergency = (roomId, floorId, severity = 'high') =>
  request('POST', '/staff/emergency/trigger-room', { floor_id: floorId, room_id: roomId, severity, message: `Manual emergency triggered for room ${roomId}` });

// ── AI Fire Alerts ───────────────────────────────────────────
export const getPendingAIAlerts = () => request('GET', '/alerts/ai-pending');
export const confirmAIAlert = (id) => request('POST', `/alerts/ai/${id}/confirm`);
export const dismissAIAlert = (id) => request('POST', `/alerts/ai/${id}/dismiss`);

// ── Tasks ────────────────────────────────────────────────────
export const getTasks = () => request('GET', '/tasks');
export const completeTask = (id) => request('POST', `/tasks/${id}/complete`);

// ── Floors ───────────────────────────────────────────────────
export const listFloors = () => request('GET', '/staff/floors');

export const createFloor = (formData) =>
  fetch(`${BASE}/staff/floors`, {
    method: 'POST',
    headers: authHeaders(),
    body: formData,
  }).then(async (res) => {
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  });

export const deleteFloor = (floorId) =>
  request('DELETE', `/staff/floors/${floorId}`);

export const getFloorGraph = (floorId) =>
  request('GET', `/staff/floors/${floorId}/graph`);

// ── Guest Bridge ─────────────────────────────────────────────
export const getHelpRequests = (floorId = null, status = null) => {
  const params = new URLSearchParams();
  if (floorId) params.set('floor_id', floorId);
  if (status) params.set('status', status);
  return request('GET', `/guest-api/help-requests?${params}`);
};

export const resolveHelpRequest = (id, resolvedBy = 'staff') =>
  request('PATCH', `/guest-api/help-requests/${id}/resolve?resolved_by=${encodeURIComponent(resolvedBy)}`);

export const broadcastMessage = (message, priority = 'info', floorId = null) =>
  request('POST', '/guest-api/messages/broadcast', { message, priority, floor_id: floorId });

export const getGuestSessions = (floorId = null) => {
  const params = new URLSearchParams();
  if (floorId) params.set('floor_id', floorId);
  return request('GET', `/guest-api/sessions?${params}`);
};

// ── Staff Members ─────────────────────────────────────────────
export const getStaff = () => request('GET', '/staff/');

// ── WebSocket ─────────────────────────────────────────────────
export function createStaffWebSocket(onMessage) {
  const token = getToken();
  const WS_BASE = import.meta.env.VITE_STAFF_WS_URL || 'ws://localhost:8001/ws/live';
  const ws = new WebSocket(`${WS_BASE}${token ? `?token=${token}` : ''}`);
  ws.onmessage = (evt) => {
    try { onMessage(JSON.parse(evt.data)); }
    catch { onMessage(evt.data); }
  };
  return ws;
}

// ── Webhook Triggers ──────────────────────────────────────────
export const callResponders = async () => {
  const response = await fetch("https://aamrut.app.n8n.cloud/webhook/emergency-call", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      location: "Hotel Sunshine",
      ambulance_number: "+918600866956",
      fire_number: "+917620888147"
    })
  });
  if (!response.ok) {
    throw new Error('Failed to trigger responder webhook');
  }
  return response.json().catch(() => ({}));
};

// ============================================================
//  src/api/guestApi.js
//  All HTTP calls to the Guest Backend (port 8000)
// ============================================================

const BASE = import.meta.env.VITE_GUEST_API_URL || 'http://localhost:8000';

function getToken() {
  return sessionStorage.getItem('guest_access_token');
}

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request(method, path, body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
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
export const guestCheckin = (room_id, phone = null, booking_id = null) =>
  request('POST', '/auth/guest/checkin', { room_id, phone, booking_id });

export const guestRefresh = (refresh_token) =>
  request('POST', '/auth/refresh', { refresh_token });

export const guestLogout = (refresh_token) =>
  request('POST', '/auth/logout', { refresh_token });

export const getGuestMe = () => request('GET', '/auth/me');

// ── Rooms (public) ───────────────────────────────────────────
export const listRooms = () => request('GET', '/guest/rooms');

// ── Check-in (public, creates session) ───────────────────────
export const checkIn = (room_id, phone_number = null) =>
  request('POST', '/guest/check-in', { room_id, phone_number });

// ── Evacuation path (public — polling) ───────────────────────
export const getEvacuationPath = (session_id) =>
  request('GET', `/guest/path?session_id=${encodeURIComponent(session_id)}`);

// ── Emergency status (public) ────────────────────────────────
export const getEmergencyStatus = () =>
  request('GET', '/guest/emergency-status');

// ── Session (authenticated) ───────────────────────────────────
export const startSession = (room_id) =>
  request('POST', '/guest/session/start', { room_id });

export const updateLocation = (session_id, node_id) =>
  request('POST', '/guest/update-location', { session_id, node_id });

// ── Help request ─────────────────────────────────────────────
export const requestHelp = (session_id, current_node, issue) =>
  request('POST', '/guest/request-help', { session_id, current_node, issue });

// ── Safe confirmation ────────────────────────────────────────
export const confirmSafe = (session_id, final_location) =>
  request('POST', '/guest/reached-safe-zone', { session_id, final_location });

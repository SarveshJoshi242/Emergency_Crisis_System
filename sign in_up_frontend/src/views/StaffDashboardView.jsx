import { useState, useEffect, useRef, useCallback } from 'react'
import {
  getAlerts, resolveAlert, getTasks, listFloors, createFloor,
  deleteFloor, getFloorGraph, getHelpRequests, resolveHelpRequest,
  broadcastMessage, getGuestSessions, staffLogout, getMe,
  createStaffWebSocket,
} from '../api/staffApi'
import FloorMapPanel from './staff/FloorMapPanel'

const TABS = ['Alerts', 'Floor Map', 'Help Requests', 'Broadcast', 'Guests']

export default function StaffDashboardView({ session, onLogout }) {
  const [tab, setTab]             = useState('Alerts')
  const [alerts, setAlerts]       = useState([])
  const [tasks, setTasks]         = useState([])
  const [floors, setFloors]       = useState([])
  const [helpReqs, setHelpReqs]   = useState([])
  const [sessions, setSessions]   = useState([])
  const [liveEvents, setLiveEvents] = useState([])
  const [me, setMe]               = useState(null)
  const [loading, setLoading]     = useState(false)
  const wsRef                     = useRef(null)
  const refreshToken              = localStorage.getItem('staff_refresh_token')

  // ── Initial data load ─────────────────────────────────────
  useEffect(() => {
    loadAll()
    getMe().then(setMe).catch(() => {})
    // WebSocket
    const ws = createStaffWebSocket(handleWsEvent)
    wsRef.current = ws
    return () => { try { ws.close() } catch {} }
  }, [])

  const loadAll = useCallback(async () => {
    setLoading(true)
    try {
      const [a, t, f, h, s] = await Promise.allSettled([
        getAlerts(), getTasks(), listFloors(), getHelpRequests(), getGuestSessions(),
      ])
      if (a.status === 'fulfilled') setAlerts(a.value || [])
      if (t.status === 'fulfilled') setTasks(t.value || [])
      if (f.status === 'fulfilled') setFloors(f.value || [])
      if (h.status === 'fulfilled') setHelpReqs(h.value || [])
      if (s.status === 'fulfilled') setSessions(s.value || [])
    } finally { setLoading(false) }
  }, [])

  // ── Auto-refresh every 15s ────────────────────────────────
  useEffect(() => {
    const id = setInterval(loadAll, 15000)
    return () => clearInterval(id)
  }, [loadAll])

  function handleWsEvent(evt) {
    setLiveEvents(prev => [
      { ...evt, _ts: new Date().toLocaleTimeString() },
      ...prev.slice(0, 49),
    ])
    // Refresh relevant data on WS event
    if (evt.type === 'alert' || evt.type === 'alert_created') {
      getAlerts().then(setAlerts).catch(() => {})
    }
    if (evt.type === 'help_request') {
      getHelpRequests().then(setHelpReqs).catch(() => {})
    }
    if (evt.type === 'safe_confirmation') {
      getGuestSessions().then(setSessions).catch(() => {})
    }
  }

  async function handleLogout() {
    try { if (refreshToken) await staffLogout(refreshToken) } catch {}
    onLogout()
  }

  // ── Danger level from alerts ──────────────────────────────
  const activeAlerts = alerts.filter(a => a.status === 'active' || a.status === 'open')
  const isEmergency  = activeAlerts.length > 0

  return (
    <div className="min-h-screen flex flex-col animate-fadeIn">
      {/* Alert Banner */}
      {isEmergency && (
        <div className="alert-bar-danger">
          🚨 EMERGENCY ACTIVE — {activeAlerts.length} alert{activeAlerts.length !== 1 ? 's' : ''} — Coordinate immediate response!
        </div>
      )}

      {/* Top Nav */}
      <header className="glass border-b border-slate-800 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-xl">🚨</span>
          <div>
            <h1 className="font-bold text-white text-sm">Emergency Management</h1>
            <p className="text-slate-500 text-xs">Staff Dashboard</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* WS indicator */}
          <div className="flex items-center gap-1.5 text-xs text-slate-400">
            <span className={`w-2 h-2 rounded-full ${wsRef.current?.readyState === 1 ? 'bg-emerald-400 animate-pulse' : 'bg-slate-600'}`} />
            Live
          </div>

          <div className="text-right hidden sm:block">
            <p className="text-sm font-medium text-white">{me?.name || session?.name || 'Staff'}</p>
            <p className="text-xs text-slate-400">{me?.email || session?.email || ''}</p>
          </div>
          <button id="btn-logout" onClick={handleLogout} className="btn-ghost text-xs px-3 py-1.5">
            Sign out
          </button>
        </div>
      </header>

      {/* Stats bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 px-6 py-4 border-b border-slate-800/50">
        <StatCard icon="🚨" label="Active Alerts"  value={activeAlerts.length}         color="red" />
        <StatCard icon="🆘" label="Help Requests"  value={helpReqs.filter(h => h.status === 'pending').length} color="yellow" />
        <StatCard icon="🏨" label="Active Guests"  value={sessions.filter(s => s.status === 'active').length}  color="blue" />
        <StatCard icon="🗺️"  label="Floors"         value={floors.length}               color="green" />
      </div>

      {/* Tab Nav */}
      <div className="flex gap-1 px-6 py-3 border-b border-slate-800/50 overflow-x-auto">
        {TABS.map(t => (
          <button
            key={t}
            id={`tab-${t.toLowerCase().replace(/\s+/g, '-')}`}
            onClick={() => setTab(t)}
            className={tab === t ? 'nav-tab-active' : 'nav-tab-inactive'}
          >
            {t}
          </button>
        ))}
        <button
          onClick={loadAll}
          className="nav-tab-inactive ml-auto"
          title="Refresh"
        >
          {loading ? '⟳' : '↻'} Refresh
        </button>
      </div>

      {/* Tab Content */}
      <main className="flex-1 p-6 overflow-auto">
        {tab === 'Alerts'       && <AlertsTab alerts={alerts} onResolve={id => resolveAlert(id).then(loadAll).catch(()=>{})} tasks={tasks} liveEvents={liveEvents} />}
        {tab === 'Floor Map'    && <FloorMapPanel floors={floors} onRefresh={loadAll} />}
        {tab === 'Help Requests'&& <HelpReqTab helpReqs={helpReqs} onResolve={id => resolveHelpRequest(id).then(loadAll).catch(()=>{})} />}
        {tab === 'Broadcast'    && <BroadcastTab floors={floors} />}
        {tab === 'Guests'       && <GuestsTab sessions={sessions} />}
      </main>
    </div>
  )
}


// ── Stat Card ─────────────────────────────────────────────────
function StatCard({ icon, label, value, color }) {
  const colors = {
    red:    'bg-red-900/20 border-red-800/30 text-red-300',
    yellow: 'bg-yellow-900/20 border-yellow-800/30 text-yellow-300',
    blue:   'bg-blue-900/20 border-blue-800/30 text-blue-300',
    green:  'bg-emerald-900/20 border-emerald-800/30 text-emerald-300',
  }
  return (
    <div className={`card-sm flex items-center gap-3 ${colors[color]}`}>
      <span className="text-2xl">{icon}</span>
      <div>
        <p className="text-2xl font-bold">{value}</p>
        <p className="text-xs opacity-70">{label}</p>
      </div>
    </div>
  )
}


// ── Alerts Tab ────────────────────────────────────────────────
function AlertsTab({ alerts, onResolve, tasks, liveEvents }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="lg:col-span-2 space-y-4">
        <h2 className="text-base font-semibold text-white">Active Alerts</h2>
        {alerts.length === 0 ? (
          <div className="card-sm text-slate-400 text-sm text-center py-8">
            ✅ No alerts — system nominal
          </div>
        ) : alerts.map(a => (
          <AlertCard key={a.id || a._id} alert={a} onResolve={() => onResolve(a.id || a._id)} />
        ))}

        <h2 className="text-base font-semibold text-white mt-6">Open Tasks</h2>
        {tasks.length === 0 ? (
          <div className="card-sm text-slate-400 text-sm text-center py-6">No tasks</div>
        ) : tasks.filter(t => t.status !== 'completed').map(t => (
          <div key={t.id || t._id} className="card-sm flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-white">{t.description || t.type}</p>
              <p className="text-xs text-slate-400 mt-0.5">Floor: {t.floor_id || '—'} · Room: {t.room_id || '—'}</p>
            </div>
            <span className={`badge ${t.priority === 'high' ? 'badge-red' : 'badge-yellow'}`}>
              {t.priority || 'normal'}
            </span>
          </div>
        ))}
      </div>

      {/* Live feed */}
      <div>
        <h2 className="text-base font-semibold text-white mb-3">Live Feed</h2>
        <div className="glass rounded-xl p-4 h-[500px] overflow-y-auto space-y-2">
          {liveEvents.length === 0 ? (
            <p className="text-slate-500 text-xs text-center mt-4">Waiting for WebSocket events…</p>
          ) : liveEvents.map((ev, i) => (
            <div key={i} className="text-xs border-b border-slate-800/50 pb-2">
              <span className="text-slate-500">{ev._ts}</span>
              <span className="ml-2 badge badge-gray">{ev.type || 'event'}</span>
              <pre className="text-slate-300 mt-1 whitespace-pre-wrap break-all text-[10px]">
                {JSON.stringify(ev, null, 2).slice(0, 200)}
              </pre>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}


function AlertCard({ alert, onResolve }) {
  const riskColors = {
    HIGH:     'border-red-700 bg-red-950/40',
    MEDIUM:   'border-yellow-700 bg-yellow-950/40',
    LOW:      'border-blue-700 bg-blue-950/40',
    CRITICAL: 'border-red-600 bg-red-950/60',
  }
  const risk = (alert.risk_level || alert.type || 'MEDIUM').toUpperCase()
  const colorClass = riskColors[risk] || 'border-slate-700 bg-slate-900/40'

  return (
    <div className={`rounded-xl border p-4 ${colorClass}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`badge ${risk === 'HIGH' || risk === 'CRITICAL' ? 'badge-red' : risk === 'MEDIUM' ? 'badge-yellow' : 'badge-blue'}`}>
              {risk}
            </span>
            <span className="text-white font-medium text-sm">{alert.message || alert.description || 'Emergency alert'}</span>
          </div>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400">
            {alert.floor_id && <span>Floor: {alert.floor_id}</span>}
            {alert.source_room && <span>Room: {alert.source_room}</span>}
            {alert.created_at && <span>{new Date(alert.created_at).toLocaleString()}</span>}
          </div>
        </div>
        {alert.status !== 'resolved' && (
          <button
            id={`btn-resolve-${alert.id || alert._id}`}
            onClick={onResolve}
            className="btn-success text-xs px-3 py-1.5 shrink-0"
          >
            Resolve
          </button>
        )}
        {alert.status === 'resolved' && <span className="badge badge-green">Resolved</span>}
      </div>
    </div>
  )
}


// ── Help Requests Tab ─────────────────────────────────────────
function HelpReqTab({ helpReqs, onResolve }) {
  const pending  = helpReqs.filter(h => h.status === 'pending')
  const resolved = helpReqs.filter(h => h.status === 'resolved')

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-base font-semibold text-white mb-3">
          Pending Requests <span className="badge badge-red ml-2">{pending.length}</span>
        </h2>
        {pending.length === 0 ? (
          <div className="card-sm text-slate-400 text-sm text-center py-6">No pending help requests</div>
        ) : (
          <div className="space-y-3">
            {pending.map(h => (
              <HelpCard key={h.id} req={h} onResolve={() => onResolve(h.id)} />
            ))}
          </div>
        )}
      </div>
      <div>
        <h2 className="text-base font-semibold text-white mb-3">Resolved</h2>
        {resolved.slice(0, 10).map(h => (
          <HelpCard key={h.id} req={h} resolved />
        ))}
      </div>
    </div>
  )
}

function HelpCard({ req, onResolve, resolved }) {
  return (
    <div className={`card-sm flex items-start justify-between gap-4 ${resolved ? 'opacity-50' : ''}`}>
      <div className="flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="badge badge-yellow">Help Request</span>
          <span className="text-sm text-white">{req.issue || 'Guest needs assistance'}</span>
        </div>
        <div className="mt-1 text-xs text-slate-400 flex flex-wrap gap-x-3">
          <span>Session: {req.session_id?.slice(0, 8)}…</span>
          {req.current_node && <span>Location: {req.current_node}</span>}
          {req.floor_id && <span>Floor: {req.floor_id}</span>}
          {req.created_at && <span>{new Date(req.created_at).toLocaleString()}</span>}
        </div>
      </div>
      {!resolved && (
        <button
          id={`btn-resolve-help-${req.id}`}
          onClick={onResolve}
          className="btn-success text-xs px-3 py-1.5 shrink-0"
        >
          Resolve
        </button>
      )}
    </div>
  )
}


// ── Broadcast Tab ─────────────────────────────────────────────
function BroadcastTab({ floors }) {
  const [message,  setMessage]  = useState('')
  const [priority, setPriority] = useState('info')
  const [floorId,  setFloorId]  = useState('')
  const [status,   setStatus]   = useState(null)   // 'ok' | 'err' | null
  const [loading,  setLoading]  = useState(false)

  async function handleBroadcast(e) {
    e.preventDefault()
    setLoading(true)
    setStatus(null)
    try {
      await broadcastMessage(message, priority, floorId || null)
      setStatus('ok')
      setMessage('')
    } catch {
      setStatus('err')
    } finally { setLoading(false) }
  }

  return (
    <div className="max-w-lg">
      <h2 className="text-base font-semibold text-white mb-4">Broadcast to Guests</h2>
      <div className="card">
        <form onSubmit={handleBroadcast} className="space-y-4">
          <div>
            <label className="label">Message</label>
            <textarea
              id="input-broadcast-msg"
              className="input resize-none"
              rows={3}
              placeholder="Emergency update: all guests proceed to stairwell B…"
              value={message}
              onChange={e => setMessage(e.target.value)}
              required
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">Priority</label>
              <select
                id="select-priority"
                className="input"
                value={priority}
                onChange={e => setPriority(e.target.value)}
              >
                <option value="info">Info</option>
                <option value="warning">Warning</option>
                <option value="critical">Critical</option>
              </select>
            </div>
            <div>
              <label className="label">Floor (optional)</label>
              <select
                id="select-floor-broadcast"
                className="input"
                value={floorId}
                onChange={e => setFloorId(e.target.value)}
              >
                <option value="">All Floors</option>
                {floors.map(f => (
                  <option key={f.id} value={f.floor_id || f.id}>{f.name}</option>
                ))}
              </select>
            </div>
          </div>

          {status === 'ok' && <p className="text-emerald-400 text-sm">✅ Message broadcast successfully</p>}
          {status === 'err' && <p className="text-red-400 text-sm">❌ Failed to broadcast</p>}

          <button
            id="btn-send-broadcast"
            type="submit"
            disabled={loading || !message.trim()}
            className="btn-primary w-full disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Sending…' : '📢 Send Broadcast'}
          </button>
        </form>
      </div>
    </div>
  )
}


// ── Guests Tab ────────────────────────────────────────────────
function GuestsTab({ sessions }) {
  const active   = sessions.filter(s => s.status === 'active')
  const safe     = sessions.filter(s => s.status === 'safe')
  const other    = sessions.filter(s => s.status !== 'active' && s.status !== 'safe')

  return (
    <div className="space-y-6">
      <h2 className="text-base font-semibold text-white">
        Guest Sessions <span className="badge badge-blue ml-2">{sessions.length} total</span>
      </h2>

      {/* Summary */}
      <div className="grid grid-cols-3 gap-3">
        <div className="card-sm text-center">
          <p className="text-2xl font-bold text-yellow-300">{active.length}</p>
          <p className="text-xs text-slate-400 mt-1">Active</p>
        </div>
        <div className="card-sm text-center">
          <p className="text-2xl font-bold text-emerald-300">{safe.length}</p>
          <p className="text-xs text-slate-400 mt-1">Safe</p>
        </div>
        <div className="card-sm text-center">
          <p className="text-2xl font-bold text-slate-300">{other.length}</p>
          <p className="text-xs text-slate-400 mt-1">Other</p>
        </div>
      </div>

      {/* Session list */}
      <div className="space-y-2">
        {sessions.slice(0, 50).map((s, i) => (
          <div key={s.session_id || i} className="card-sm flex items-center justify-between gap-3">
            <div>
              <p className="text-sm text-white font-mono">{s.session_id?.slice(0, 12)}…</p>
              <p className="text-xs text-slate-400">
                Room: {s.room_id || '—'} · Floor: {s.floor_id || '—'} · Node: {s.current_node || '—'}
              </p>
            </div>
            <span className={`badge ${s.status === 'safe' ? 'badge-green' : s.status === 'active' ? 'badge-yellow' : 'badge-gray'}`}>
              {s.status}
            </span>
          </div>
        ))}
        {sessions.length === 0 && (
          <div className="card-sm text-slate-400 text-sm text-center py-6">No guest sessions</div>
        )}
      </div>
    </div>
  )
}

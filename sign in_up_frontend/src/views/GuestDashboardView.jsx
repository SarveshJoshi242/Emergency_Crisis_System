import { useState, useEffect, useCallback } from 'react'
import { getEvacuationPath, getEmergencyStatus, requestHelp, confirmSafe } from '../api/guestApi'

const POLL_INTERVAL = 5000   // 5 seconds

export default function GuestDashboardView({ session, onExit }) {
  const { session_id, room_id, floor_id } = session

  const [steps,         setSteps]         = useState([])
  const [isActive,      setIsActive]      = useState(false)
  const [emergency,     setEmergency]     = useState(null)
  const [currentStep,   setCurrentStep]   = useState(0)
  const [safe,          setSafe]          = useState(false)
  const [safeConfirmedAnim, setSafeConfirmedAnim] = useState(false)
  const [helpSent,      setHelpSent]      = useState(false)
  const [helpLoading,   setHelpLoading]   = useState(false)
  const [confirmLoading,setConfirmLoading]= useState(false)
  const [lastUpdated,   setLastUpdated]   = useState(null)
  const [error,         setError]         = useState('')
  const [notifications, setNotifications] = useState([])

  // ── Polling ───────────────────────────────────────────────
  const poll = useCallback(async () => {
    try {
      const [pathData, emergData] = await Promise.all([
        getEvacuationPath(session_id),
        getEmergencyStatus(),
      ])
      setSteps(pathData.steps || [])
      setIsActive(!!pathData.is_active)
      setEmergency(emergData)
      setLastUpdated(new Date())
      setError('')
    } catch (e) {
      setError('Connection error — retrying…')
    }
  }, [session_id])

  useEffect(() => {
    poll()
    const id = setInterval(poll, POLL_INTERVAL)
    return () => clearInterval(id)
  }, [poll])

  // ── WebSocket for Real-time Notifications ─────────────────
  useEffect(() => {
    // We connect to the Staff backend WS to receive broadcast messages and help resolutions
    const WS_URL = import.meta.env.VITE_STAFF_WS_URL || 'ws://localhost:8001/ws/live'
    const ws = new WebSocket(WS_URL)
    
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        
        if (msg.event === 'help_resolved' && msg.data.session_id === session_id) {
          setNotifications(prev => [...prev, {
            id: Date.now(),
            type: 'success',
            text: '✅ Staff has resolved your help request. Assistance is on the way.'
          }])
          setHelpSent(false) // reset button so they can ask again if needed
        } else if (msg.event === 'broadcast_message') {
          setNotifications(prev => [...prev, {
            id: msg.data.id || Date.now(),
            type: msg.data.priority,
            text: `📢 ${msg.data.message}`
          }])
        } else if (msg.event === 'route_update') {
          setNotifications(prev => [...prev, {
            id: Date.now(),
            type: 'warning',
            text: `⚠️ ${msg.data.message || 'Route blocked. Please follow updated instructions.'}`
          }])
        }
      } catch (e) {
        console.error('WS parse error:', e)
      }
    }
    
    return () => ws.close()
  }, [session_id])

  const dismissNotification = (id) => {
    setNotifications(prev => prev.filter(n => n.id !== id))
  }

  async function handleHelp() {
    setHelpLoading(true)
    try {
      await requestHelp(session_id, steps[currentStep]?.node || room_id, 'Guest needs assistance')
      setHelpSent(true)
    } catch { /* non-fatal */ }
    finally { setHelpLoading(false) }
  }

  async function handleSafe() {
    setConfirmLoading(true)
    try {
      await confirmSafe(session_id, steps[steps.length - 1]?.node || 'exit')
      setSafeConfirmedAnim(true)
      setTimeout(() => {
        setSafe(true)
      }, 1500)
    } catch { /* non-fatal */ }
    finally { setConfirmLoading(false) }
  }

  // ── Safe state ────────────────────────────────────────────
  if (safe) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4 animate-fadeIn">
        <div className="card text-center max-w-sm w-full">
          <div className="text-6xl mb-4">✅</div>
          <h1 className="text-2xl font-bold text-emerald-400 mb-2">You Are Safe!</h1>
          <p className="text-slate-400 text-sm mb-6">You have confirmed reaching the safe zone. Staff have been notified.</p>
          <button onClick={onExit} className="btn-ghost w-full">Exit</button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex flex-col animate-fadeIn">
      {/* Emergency Banner */}
      <div className={isActive ? 'alert-bar-danger' : 'alert-bar-safe'}>
        {isActive
          ? `🚨 EMERGENCY — Follow instructions below immediately`
          : `✅ No active emergency — system monitoring`}
      </div>

      {/* Header */}
      <header className="glass border-b border-slate-800 px-4 md:px-6 py-3 flex items-center justify-between gap-2">
        <div className="min-w-0">
          <h1 className="font-bold text-white text-sm truncate">Guest Evacuation</h1>
          <p className="text-slate-500 text-xs truncate">Room {room_id} · Floor {floor_id || '—'}</p>
        </div>
        <div className="flex items-center gap-2 md:gap-3 shrink-0">
          {lastUpdated && (
            <span className="text-[10px] md:text-xs text-slate-500 hidden sm:inline">
              Updated {lastUpdated.toLocaleTimeString()}
            </span>
          )}
          <button id="btn-guest-exit" onClick={onExit} className="btn-ghost text-xs px-2 md:px-3 py-1.5">Exit</button>
        </div>
      </header>

      <main className="flex-1 p-4 md:p-6 max-w-2xl mx-auto w-full space-y-4 md:space-y-6 overflow-x-hidden">
        {/* Session info */}
        <div className="card-sm flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-400">
          <span>Session: <code className="text-slate-300">{session_id?.slice(0, 16)}…</code></span>
          <span>Room: <code className="text-slate-300">{room_id}</code></span>
          {floor_id && <span>Floor: <code className="text-slate-300">{floor_id}</code></span>}
        </div>

        {error && (
          <div className="card-sm text-yellow-400 text-sm">{error}</div>
        )}

        {/* Emergency details */}
        {emergency && isActive && (
          <div className="card border border-red-800/50 bg-red-950/30 space-y-2">
            <h2 className="text-sm font-semibold text-red-300">Emergency Details</h2>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-300">
              {emergency.emergency_type && <span>Type: <strong>{emergency.emergency_type}</strong></span>}
              {emergency.affected_floors?.length > 0 && (
                <span>Affected: <strong>{emergency.affected_floors.join(', ')}</strong></span>
              )}
              {emergency.blocked_nodes?.length > 0 && (
                <span>Blocked: <strong>{emergency.blocked_nodes.join(', ')}</strong></span>
              )}
            </div>
          </div>
        )}

        {/* Evacuation steps */}
        <div className="card space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-white">
              {isActive ? '🚨 Evacuation Route' : '📍 Your Location'}
            </h2>
            {steps.length > 0 && (
              <span className="badge badge-blue">{steps.length} step{steps.length !== 1 ? 's' : ''}</span>
            )}
          </div>

          {steps.length === 0 && !isActive && (
            <div className="text-center py-8 text-slate-400">
              <div className="text-4xl mb-3">🏨</div>
              <p className="text-sm">No emergency active. Stay calm and monitor this screen.</p>
              <p className="text-xs mt-1 text-slate-600">Auto-refreshes every 5 seconds</p>
            </div>
          )}

          {steps.length === 0 && isActive && (
            <div className="text-center py-8 text-yellow-300">
              <div className="text-4xl mb-3">⚠️</div>
              <p className="text-sm">Calculating evacuation route… Please wait.</p>
            </div>
          )}

          {steps.length > 0 && (
            <div className="space-y-2">
              {steps.map((step, i) => (
                <div
                  key={i}
                  id={`step-${i}`}
                  className={`flex items-start gap-3 p-3 rounded-xl transition-all ${
                    i === currentStep
                      ? 'bg-brand-900/40 border border-brand-700/40'
                      : i < currentStep
                      ? 'opacity-40'
                      : 'bg-slate-800/40'
                  }`}
                >
                  <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${
                    i < currentStep   ? 'bg-emerald-700 text-white'
                    : i === currentStep ? 'bg-brand-600 text-white animate-pulse-slow'
                    : 'bg-slate-700 text-slate-400'
                  }`}>
                    {i < currentStep ? '✓' : i + 1}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className={`text-sm ${i === currentStep ? 'text-white font-semibold' : 'text-slate-300'}`}>
                      {step.instruction}
                    </p>
                    {step.node && (
                      <p className="text-xs text-slate-500 mt-0.5 font-mono">{step.node}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Step navigation */}
          {steps.length > 0 && (
            <div className="flex gap-3 pt-2">
              <button
                id="btn-prev-step"
                onClick={() => setCurrentStep(s => Math.max(0, s - 1))}
                disabled={currentStep === 0}
                className="btn-ghost flex-1 disabled:opacity-30"
              >
                ← Previous
              </button>
              {currentStep < steps.length - 1 ? (
                <button
                  id="btn-next-step"
                  onClick={() => setCurrentStep(s => Math.min(steps.length - 1, s + 1))}
                  className="btn-primary flex-1"
                >
                  Next →
                </button>
              ) : (
                <button
                  id="btn-confirm-safe"
                  onClick={handleSafe}
                  disabled={confirmLoading || safeConfirmedAnim}
                  className={`flex-1 px-4 py-3 rounded-xl font-bold transition-all duration-300 disabled:opacity-50 ${
                    safeConfirmedAnim 
                      ? 'bg-emerald-500 text-white shadow-[0_0_20px_rgba(16,185,129,0.5)] border border-emerald-400' 
                      : 'btn-success'
                  }`}
                >
                  {safeConfirmedAnim ? '✅ Status Confirmed!' : confirmLoading ? 'Confirming…' : '✅ I am Safe'}
                </button>
              )}
            </div>
          )}
        </div>

        {/* Bottom Widgets */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Help request */}
          <div className="card-sm flex flex-col justify-between gap-4 h-full">
            <div>
              <p className="text-sm font-medium text-white">Need Assistance?</p>
              <p className="text-xs text-slate-400">Alert staff to your location</p>
            </div>
            <button
              id="btn-request-help"
              onClick={handleHelp}
              disabled={helpSent || helpLoading}
              className={`w-full ${helpSent ? 'btn-ghost opacity-70 cursor-not-allowed' : 'btn-danger'}`}
            >
              {helpSent ? '⏳ Waiting for staff response' : helpLoading ? 'Sending…' : '🆘 Help!'}
            </button>
          </div>

          {/* Broadcast Messages */}
          <div className="card-sm flex flex-col gap-3 h-full overflow-hidden">
            <div>
              <p className="text-sm font-medium text-white">Live Updates</p>
              <p className="text-xs text-slate-400">Messages from staff</p>
            </div>
            <div className="flex-1 overflow-y-auto space-y-2 pr-1 custom-scrollbar min-h-[60px] max-h-[120px]">
              {notifications.length === 0 ? (
                <p className="text-xs text-slate-500 italic flex h-full items-center justify-center">No new messages</p>
              ) : (
                notifications.map(n => (
                  <div key={n.id} className={`p-2 rounded-lg text-xs font-medium flex items-start gap-2 border ${
                    n.type === 'critical' || n.type === 'danger' || n.type === 'info' ? 'bg-red-950/30 text-red-200 border-red-900/50' :
                    n.type === 'warning' ? 'bg-yellow-950/30 text-yellow-200 border-yellow-900/50' :
                    n.type === 'success' ? 'bg-emerald-950/30 text-emerald-200 border-emerald-900/50' :
                    'bg-red-950/30 text-red-200 border-red-900/50'
                  }`}>
                    <span className="flex-1">{n.text}</span>
                    <button onClick={() => dismissNotification(n.id)} className="opacity-50 hover:opacity-100 shrink-0 font-bold">✕</button>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}

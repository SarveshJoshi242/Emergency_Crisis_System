import { useState, useEffect, useRef, useCallback } from 'react'
import {
  getAlerts, resolveAlert, resolveAllAlerts, listFloors,
  staffLogout, getMe, createStaffWebSocket, triggerDemo, startEmergency, getGuestSessions,
  broadcastMessage, getHelpRequests, resolveHelpRequest, getTasks, completeTask,
  getPendingAIAlerts, confirmAIAlert, dismissAIAlert, callResponders
} from '../api/staffApi'
import FloorMapPanel from './staff/FloorMapPanel'

export default function StaffDashboardView({ session, onLogout }) {
  const [alerts, setAlerts] = useState([])
  const [floors, setFloors] = useState([])
  const [tasks, setTasks] = useState([])
  const [helpRequests, setHelpRequests] = useState([])
  const [guestSessions, setGuestSessions] = useState([])
  const [pendingAIAlerts, setPendingAIAlerts] = useState([])
  const [me, setMe] = useState(null)
  
  const [broadcastText, setBroadcastText] = useState('')
  const [isBroadcasting, setIsBroadcasting] = useState(false)
  const [confirmingAlertId, setConfirmingAlertId] = useState(null)

  // Tabs: overview, tasks, help, floors, map, ai
  const [activeTab, setActiveTab] = useState('overview')

  const wsRef = useRef(null)
  
  const activeAlerts = alerts.filter(a => a.status === 'ACTIVE' || a.status === 'open')
  const pendingTasks = tasks.filter(t => t.status !== 'done' && t.status !== 'completed')
  const pendingHelp = helpRequests.filter(h => h.status === 'pending')
  
  const isEmergency = activeAlerts.length > 0
  
  useEffect(() => {
    loadAll()
    getMe().then(setMe).catch(() => {})
    setupWebSocket()
    return () => { if (wsRef.current) wsRef.current.close() }
  }, [])

  const setupWebSocket = () => {
    const ws = createStaffWebSocket(handleWsEvent)
    ws.onopen = () => console.log('WS Connected')
    ws.onclose = () => setTimeout(setupWebSocket, 3000)
    wsRef.current = ws
  }

  const loadAll = useCallback(async () => {
    try {
      const [a, f, g, t, h, ai] = await Promise.all([
        getAlerts(), 
        listFloors(),
        getGuestSessions().catch(() => []),
        getTasks().catch(() => []),
        getHelpRequests().catch(() => []),
        getPendingAIAlerts().catch(() => [])
      ])
      setAlerts(a || [])
      setFloors(f || [])
      setGuestSessions(g || [])
      setTasks(t || [])
      setHelpRequests(h || [])
      setPendingAIAlerts(ai || [])
    } catch (e) {
      console.error(e)
    }
  }, [])

  function handleWsEvent(msg) {
    if (msg.event === 'new_alert') {
      setAlerts(prev => prev.some(a => a.id === msg.data.id) ? prev : [msg.data, ...prev])
    } else if (msg.event === 'ai_fire_alert') {
      setPendingAIAlerts(prev => prev.some(a => a.id === msg.data.id) ? prev : [msg.data, ...prev])
    } else if (msg.event === 'resolve_alert') {
      setAlerts(prev => prev.map(a => a.id === msg.data.alert_id ? { ...a, status: 'RESOLVED' } : a))
    } else if (msg.event === 'bulk_update' && msg.data.action === 'resolve_all') {
      setAlerts(prev => prev.map(a => ({ ...a, status: 'RESOLVED' })))
      setTasks([])
    } else if (msg.event === 'task_assigned') {
      setTasks(msg.data.tasks || [])
    } else {
      loadAll() // reload for help requests, safe confirmations, etc.
    }
  }

  async function handleLogout() {
    try { await staffLogout(localStorage.getItem('staff_refresh_token')) } catch {}
    onLogout()
  }

  async function handleConfirm(alert) {
    setConfirmingAlertId(alert.id || alert._id)
    try {
      if (alert.state === 'pending' || alert.source === 'yolo') {
        await confirmAIAlert(alert.id || alert._id)
        setConfirmingAlertId('confirmed_' + (alert.id || alert._id))
        setTimeout(() => {
          setPendingAIAlerts(prev => prev.filter(a => a.id !== alert.id))
          loadAll()
          setActiveTab('tasks')
          setConfirmingAlertId(null)
        }, 1500)
      } else {
        await startEmergency(alert.room_id || alert.source_room, alert.floor || alert.floor_id, alert.type || "fire")
        loadAll()
        setActiveTab('tasks')
        setConfirmingAlertId(null)
      }
    } catch(e) {
      console.error("Failed to start emergency", e)
      window.alert("Failed to confirm emergency. Please try again.")
      setConfirmingAlertId(null)
    }
  }

  async function handleDismiss(alert) {
    try {
      if (alert.state === 'pending' || alert.source === 'yolo') {
        await dismissAIAlert(alert.id || alert._id)
        setPendingAIAlerts(prev => prev.filter(a => a.id !== alert.id))
      } else {
        await resolveAlert(alert.id || alert._id)
      }
    } catch (e) {
      console.error(e)
    }
  }

  async function handleResolveAll() {
    await resolveAllAlerts()
    setTasks([])
  }

  async function handleCompleteTask(taskId) {
    try {
      await completeTask(taskId)
      setTasks(prev => prev.map(t => (t.id === taskId || t._id === taskId) ? { ...t, status: 'done' } : t))
    } catch (e) {
      console.error(e)
    }
  }

  async function handleResolveHelp(id) {
    try {
      await resolveHelpRequest(id, me?.name || 'Staff')
      setHelpRequests(prev => prev.map(h => (h.id === id || h._id === id) ? { ...h, status: 'resolved' } : h))
    } catch (e) {
      console.error(e)
    }
  }

  const [isCallingResponders, setIsCallingResponders] = useState(false)

  async function handleCallResponders() {
    if (!window.confirm("Are you sure you want to call first responders (Ambulance & Fire)? This will trigger an automated emergency call.")) return;
    
    setIsCallingResponders(true)
    try {
      await callResponders()
      alert("Emergency responders have been called successfully.")
    } catch (err) {
      alert("Failed to call responders: " + err.message)
    } finally {
      setIsCallingResponders(false)
    }
  }

  async function handleBroadcast(e) {
    e.preventDefault()
    if (!broadcastText.trim()) return
    setIsBroadcasting(true)
    try {
      await broadcastMessage(broadcastText, 'info')
      setBroadcastText('')
      alert('Message broadcasted to all guests.')
    } catch (err) {
      alert('Broadcast failed: ' + err.message)
    } finally {
      setIsBroadcasting(false)
    }
  }

  const sortedAlerts = [...activeAlerts, ...pendingAIAlerts].sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
  const sortedAIAlerts = [...pendingAIAlerts].sort((a, b) => new Date(b.created_at) - new Date(a.created_at))

  return (
    <div className="min-h-screen bg-[#0B0F19] text-slate-300 font-sans selection:bg-red-500/30 flex flex-col">
      
      {/* HEADER */}
      <header className="px-4 md:px-6 py-4 flex flex-col md:flex-row md:items-center justify-between shrink-0 border-b border-[#1E293B] gap-4">
        <div>
          <h1 className="font-bold text-white tracking-wide text-xl">Smart Emergency Dashboard</h1>
          <p className="text-sm text-slate-400 mt-1">{me?.name || session?.name || 'TestUser'} - {me?.email || session?.email || 'user@xyz.com'}</p>
        </div>
        <div className="flex items-center gap-2 md:gap-4 flex-wrap">
          <button 
            onClick={handleCallResponders} 
            disabled={isCallingResponders}
            className="flex items-center gap-2 bg-red-600 hover:bg-red-500 text-white px-4 py-2 rounded-lg transition-colors text-sm font-bold shadow-[0_0_15px_rgba(220,38,38,0.3)] border border-red-500 disabled:opacity-50"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" /></svg>
            {isCallingResponders ? 'Calling...' : 'Call Responders'}
          </button>
          <button onClick={() => setActiveTab('map')} className="flex items-center gap-2 border border-slate-700 hover:bg-slate-800 text-slate-300 px-4 py-2 rounded-lg transition-colors text-sm font-medium">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" /></svg>
            Floor Maps
          </button>
          <button onClick={loadAll} className="p-2 border border-slate-700 hover:bg-slate-800 text-slate-300 rounded-lg transition-colors">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
          </button>
          <button onClick={handleLogout} className="flex items-center gap-2 border border-slate-700 hover:bg-slate-800 text-slate-300 px-4 py-2 rounded-lg transition-colors text-sm font-medium">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" /></svg>
            Sign Out
          </button>
        </div>
      </header>

      {/* EMERGENCY BANNER */}
      {isEmergency && (
        <div className="bg-[#4C101C] text-red-200 px-4 md:px-6 py-4 flex flex-col md:flex-row md:items-center justify-between border-b border-[#7F1D1D] shadow-[0_0_30px_rgba(220,38,38,0.1)] gap-4">
          <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-3">
            <div className="flex items-center gap-2">
              <div className="animate-pulse shrink-0">
                <svg className="w-5 h-5 text-red-400" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M10 2a8 8 0 100 16 8 8 0 000-16zM9 5a1 1 0 112 0v5a1 1 0 11-2 0V5zm1 10a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" /></svg>
              </div>
              <span className="font-bold tracking-widest text-sm">EMERGENCY ACTIVE — HIGH</span>
            </div>
            <span className="text-red-300/70 text-sm sm:ml-2">Affected locations: System-wide Alert</span>
          </div>
          <button onClick={handleResolveAll} className="w-full md:w-auto bg-red-600 hover:bg-red-500 text-white px-6 py-2 rounded font-bold transition-colors shadow-lg shadow-red-900/50 flex items-center justify-center gap-2 shrink-0">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" /></svg>
            Resolve All
          </button>
        </div>
      )}

      <main className="p-4 md:p-8 flex-1 flex flex-col gap-6 md:gap-8 max-w-7xl mx-auto w-full overflow-x-hidden">
        
        {/* STAT CARDS */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6">
          
          {/* System Status */}
          <div className={`p-5 rounded-xl border flex items-center gap-4 ${isEmergency ? 'bg-[#2A0E15] border-[#4C1D26]' : 'bg-[#0F1C18] border-[#133125]'}`}>
            <div className={`w-12 h-12 rounded-lg flex items-center justify-center shrink-0 ${isEmergency ? 'bg-[#5B1123] text-red-400' : 'bg-[#153D2E] text-emerald-400'}`}>
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" /></svg>
            </div>
            <div>
              <p className="text-[10px] font-bold tracking-widest text-slate-500 uppercase">System Status</p>
              <h2 className={`text-2xl font-bold mt-1 leading-none ${isEmergency ? 'text-white' : 'text-white'}`}>
                {isEmergency ? 'EMERGENCY' : 'ALL CLEAR'}
              </h2>
              <p className={`text-xs mt-1 font-medium ${isEmergency ? 'text-red-400' : 'text-emerald-500'}`}>{isEmergency ? 'HIGH' : 'No active threats'}</p>
            </div>
          </div>

          {/* Active Alerts */}
          <div className="bg-[#111A24] border border-[#1E293B] p-5 rounded-xl flex items-center gap-4">
            <div className={`w-12 h-12 rounded-lg flex items-center justify-center shrink-0 ${activeAlerts.length > 0 ? 'bg-orange-500/20 text-orange-400' : 'bg-emerald-500/20 text-emerald-400'}`}>
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
            </div>
            <div>
              <p className="text-[10px] font-bold tracking-widest text-slate-500 uppercase">Active Alerts</p>
              <h2 className="text-2xl font-bold mt-1 text-white leading-none">{activeAlerts.length}</h2>
              <p className="text-xs text-slate-400 mt-1">{activeAlerts.length === 0 ? 'No alerts' : 'Requires attention'}</p>
            </div>
          </div>

          {/* Active Guests */}
          <div className="bg-[#111A24] border border-[#1E293B] p-5 rounded-xl flex items-center gap-4">
            <div className="w-12 h-12 rounded-lg bg-blue-500/20 text-blue-400 flex items-center justify-center shrink-0">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" /></svg>
            </div>
            <div>
              <p className="text-[10px] font-bold tracking-widest text-slate-500 uppercase">Active Guests</p>
              <h2 className="text-2xl font-bold mt-1 text-white leading-none">{guestSessions.length}</h2>
              <p className="text-xs text-slate-400 mt-1">On-property sessions</p>
            </div>
          </div>

          {/* Floors Mapped */}
          <div className="bg-[#111A24] border border-[#1E293B] p-5 rounded-xl flex items-center gap-4">
            <div className="w-12 h-12 rounded-lg bg-indigo-500/20 text-indigo-400 flex items-center justify-center shrink-0">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" /></svg>
            </div>
            <div>
              <p className="text-[10px] font-bold tracking-widest text-slate-500 uppercase">Floors Mapped</p>
              <h2 className="text-2xl font-bold mt-1 text-white leading-none">{floors.length}</h2>
              <p className="text-xs text-slate-400 mt-1">Configured floors</p>
            </div>
          </div>

        </div>

        {/* TABS */}
        <div className="flex items-center gap-4 md:gap-6 border-b border-[#1E293B] pb-4 overflow-x-auto whitespace-nowrap custom-scrollbar">
          <button onClick={() => setActiveTab('overview')} className={`px-4 py-1.5 rounded-full text-sm font-semibold transition-colors ${activeTab === 'overview' ? 'bg-[#FF003C] text-white shadow-[#FF003C]/30 shadow-lg' : 'text-slate-400 hover:text-slate-300'}`}>Overview</button>
          <button onClick={() => setActiveTab('tasks')} className={`text-sm font-semibold transition-colors ${activeTab === 'tasks' ? 'text-white' : 'text-slate-400 hover:text-slate-300'}`}>Tasks ({tasks.length})</button>
          <button onClick={() => setActiveTab('help')} className={`text-sm font-semibold transition-colors ${activeTab === 'help' ? 'text-white' : 'text-slate-400 hover:text-slate-300'}`}>Help Requests ({pendingHelp.length})</button>
          <button onClick={() => setActiveTab('floors')} className={`text-sm font-semibold transition-colors ${activeTab === 'floors' ? 'text-white' : 'text-slate-400 hover:text-slate-300'}`}>Floors</button>
          <button onClick={() => setActiveTab('ai')} className={`text-sm font-bold ml-4 px-4 py-1.5 rounded-full flex items-center gap-2 transition-all shadow-lg ${activeTab === 'ai' ? 'bg-[#FF003C] text-white shadow-[#FF003C]/30' : 'bg-red-500/10 text-red-500 hover:bg-red-500/20'}`}>
            🔥 AI Alerts
          </button>
        </div>

        {/* TAB CONTENT */}
        <div className="flex-1 rounded-xl flex flex-col">
          
          {/* OVERVIEW TAB */}
          {activeTab === 'overview' && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              
              {/* Active Alerts Panel */}
              <div className="bg-[#0F1523] border border-[#1E293B] rounded-xl p-6 min-h-[250px] lg:h-[500px] overflow-y-auto">
                <h3 className="font-bold text-white flex items-center gap-2 mb-4">
                  <span className="text-yellow-500">⚠️</span> Active Alerts
                </h3>
                {sortedAlerts.length === 0 ? (
                  <div className="flex items-center justify-center h-48 text-slate-500 text-sm">
                    No active alerts — system nominal
                  </div>
                ) : (
                  <div className="space-y-4">
                    {sortedAlerts.map(a => (
                      <div key={a.id} className="bg-[#181014] border border-[#4C1D26] rounded-lg p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <p className="text-white font-bold text-sm truncate">⚠️ {a.message || `Fire detected in Room ${a.room_id || a.source_room}`}</p>
                          <p className="text-xs text-slate-400 mt-1">Floor: {a.floor_id} | Risk: {a.risk_level || 'HIGH'}</p>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          {a.state === 'pending' ? (
                            <button 
                              onClick={() => handleConfirm(a)} 
                              disabled={confirmingAlertId === (a.id || a._id) || confirmingAlertId === 'confirmed_' + (a.id || a._id)}
                              className={`px-3 py-1.5 rounded text-xs font-bold transition-all ${
                                confirmingAlertId === 'confirmed_' + (a.id || a._id)
                                ? 'bg-emerald-500 text-white shadow-[0_0_15px_rgba(16,185,129,0.5)] border border-emerald-400'
                                : confirmingAlertId === (a.id || a._id) 
                                ? 'bg-emerald-800 text-emerald-400 cursor-not-allowed border border-emerald-700/50' 
                                : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg'
                              }`}
                            >
                              {confirmingAlertId === 'confirmed_' + (a.id || a._id) ? '✅ Confirmed!' : confirmingAlertId === (a.id || a._id) ? '⏳ Starting...' : '✅ Confirm'}
                            </button>
                          ) : null}
                          {confirmingAlertId !== 'confirmed_' + (a.id || a._id) && (
                            <button onClick={() => handleDismiss(a)} className="bg-slate-800 text-slate-300 hover:text-white px-3 py-1.5 rounded text-xs font-bold border border-slate-700">Dismiss</button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Right Column: Broadcast & Guests */}
              <div className="flex flex-col gap-6 lg:h-[500px]">
                
                {/* Broadcast Message */}
                <div className="bg-[#0F1523] border border-[#1E293B] rounded-xl p-6">
                  <h3 className="font-bold text-white flex items-center gap-2 mb-4">
                    <span className="text-blue-400">✈️</span> Broadcast Message to Guests
                  </h3>
                  <form onSubmit={handleBroadcast}>
                    <textarea 
                      value={broadcastText}
                      onChange={e => setBroadcastText(e.target.value)}
                      placeholder="Type a message to broadcast to all guests..."
                      className="w-full bg-[#111A24] border border-[#1E293B] rounded-lg p-3 text-sm text-white focus:outline-none focus:border-blue-500 mb-4 h-24"
                    />
                    <button type="submit" disabled={isBroadcasting || !broadcastText.trim()} className="w-full bg-blue-700 hover:bg-blue-600 disabled:opacity-50 text-white font-bold py-2 rounded-lg flex items-center justify-center gap-2 transition-colors">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"/></svg>
                      {isBroadcasting ? 'Sending...' : 'Send to All Guests'}
                    </button>
                  </form>
                </div>

                {/* Active Guest Sessions */}
                <div className="bg-[#0F1523] border border-[#1E293B] rounded-xl p-6 flex-1 overflow-hidden flex flex-col max-h-[350px] lg:max-h-none">
                  <h3 className="font-bold text-white flex items-center gap-2 mb-4 shrink-0">
                    <span className="text-slate-400">👥</span> Active Guest Sessions
                  </h3>
                  <div className="overflow-y-auto space-y-2 pr-2">
                    {guestSessions.length === 0 ? (
                      <p className="text-slate-500 text-sm">No active guests.</p>
                    ) : (
                      guestSessions.map((session, i) => (
                        <div key={i} className="flex items-center justify-between py-1 border-b border-[#1E293B]/50 last:border-0 gap-2 overflow-hidden">
                          <span className="text-sm font-medium text-slate-300 truncate">room_{session.room_id || 'unknown'}</span>
                          <span className="bg-blue-900/30 text-blue-400 px-2 py-0.5 rounded text-xs shrink-0">active</span>
                        </div>
                      ))
                    )}
                  </div>
                </div>

              </div>
            </div>
          )}

          {/* AI ALERTS TAB */}
          {activeTab === 'ai' && (
            <div className="bg-[#0F1523] border border-[#1E293B] rounded-xl p-6 h-full flex flex-col">
              <div className="flex items-center justify-between border-b border-[#1E293B] pb-4 mb-6 shrink-0">
                <h3 className="font-bold text-white flex items-center gap-2">
                  <span className="text-yellow-500">🛡</span> AI Fire Alerts <span className="text-slate-500 font-normal text-xs ml-2">from YOLO Room Service</span>
                </h3>
                <button onClick={loadAll} className="text-slate-500 hover:text-white transition-colors">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                </button>
              </div>

              {sortedAIAlerts.length === 0 ? (
                <div className="flex-1 flex flex-col items-center justify-center text-center">
                  <div className="w-16 h-16 border-2 border-emerald-900 rounded-full flex items-center justify-center mb-4">
                    <svg className="w-8 h-8 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" /></svg>
                  </div>
                  <h4 className="text-white font-bold text-lg mb-2">No pending AI alerts</h4>
                  <p className="text-sm text-slate-500">All clear — AI monitoring is active</p>
                </div>
              ) : (
                <div className="flex-1 overflow-y-auto space-y-4 pr-2">
                  {sortedAIAlerts.map(a => (
                    <div key={a.id} className="bg-[#181014] border border-[#4C1D26] rounded-xl p-4 md:p-6 shadow-lg shadow-red-900/10 flex flex-col md:flex-row md:items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse shrink-0"></span>
                          <span className="text-[10px] md:text-xs font-bold text-red-400 tracking-wider truncate">{a.risk_level === 'MEDIUM' || a.risk === 'MEDIUM' ? 'MEDIUM RISK DETECTED' : 'HIGH RISK DETECTED'}</span>
                        </div>
                        <h4 className="text-lg md:text-2xl font-bold text-white mb-2 break-words">⚠️ {a.message || `Possible fire detected in Room ${a.room_id || a.source_room}`}</h4>
                        <p className="text-sm md:text-base text-slate-400 mb-4 md:mb-6 font-medium">Confidence: {a.risk_level === 'MEDIUM' || a.risk === 'MEDIUM' ? 'Medium' : a.risk_level || a.risk || 'Medium'}</p>
                        
                        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 sm:gap-4">
                          <button 
                            onClick={() => handleConfirm(a)} 
                            disabled={confirmingAlertId === (a.id || a._id) || confirmingAlertId === 'confirmed_' + (a.id || a._id)}
                            className={`px-4 md:px-8 py-3 rounded-lg font-bold text-sm md:text-base transition-all text-center ${
                              confirmingAlertId === 'confirmed_' + (a.id || a._id)
                              ? 'bg-emerald-500 text-white shadow-[0_0_15px_rgba(16,185,129,0.5)] border border-emerald-400'
                              : confirmingAlertId === (a.id || a._id) 
                              ? 'bg-emerald-800 text-emerald-400 cursor-not-allowed border border-emerald-700/50' 
                              : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg hover:shadow-emerald-600/20'
                            }`}
                          >
                            {confirmingAlertId === 'confirmed_' + (a.id || a._id) ? '✅ Confirmed!' : confirmingAlertId === (a.id || a._id) ? '⏳ Starting Evacuation...' : '✅ Confirm Emergency'}
                          </button>
                          {confirmingAlertId !== 'confirmed_' + (a.id || a._id) && (
                            <button onClick={() => handleDismiss(a)} className="bg-slate-800 hover:bg-slate-700 text-white px-4 md:px-8 py-3 rounded-lg font-bold text-sm md:text-base transition-all border border-slate-600 text-center">
                              ❌ Dismiss
                            </button>
                          )}
                        </div>
                      </div>
                      <div className="text-left md:text-right text-slate-500 text-xs md:text-sm font-mono shrink-0">
                        {new Date(a.created_at).toLocaleTimeString()}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* TASKS TAB */}
          {activeTab === 'tasks' && (
            <div className="bg-[#0F1523] border border-[#1E293B] rounded-xl p-6 h-full flex flex-col">
              <div className="flex flex-col md:flex-row md:items-center justify-between border-b border-[#1E293B] pb-4 mb-6 shrink-0 gap-4">
                <h3 className="font-bold text-white flex items-center gap-2">
                  <span className="text-blue-400">🧑‍🚒</span> Active Responder Tasks
                </h3>
              </div>
              
              {tasks.length === 0 ? (
                <div className="flex-1 flex flex-col items-center justify-center text-slate-600">
                  <p>No active emergency tasks</p>
                </div>
              ) : (
                <div className="overflow-y-auto space-y-4 max-h-[600px] pr-2 custom-scrollbar">
                  {tasks.map((task, idx) => {
                    const isDone = task.status === 'done' || task.status === 'completed';
                    return (
                      <div key={task.id || task._id || idx} className={`bg-[#111A24] p-4 md:p-5 rounded-xl border flex flex-col sm:flex-row sm:items-center gap-3 md:gap-5 transition-all ${isDone ? 'border-emerald-900/50 opacity-50' : 'border-[#1E293B]'}`}>
                        <div className={`w-10 h-10 rounded-full flex items-center justify-center font-bold text-lg shrink-0 ${isDone ? 'bg-emerald-900 text-emerald-400' : 'bg-blue-500/10 text-blue-400 border border-blue-500/20'}`}>
                          {isDone ? '✓' : idx + 1}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className={`text-lg font-medium break-words ${isDone ? 'text-slate-400 line-through' : 'text-white'}`}>
                            {task.task || task.task_type || JSON.stringify(task)}
                          </p>
                          <p className="text-sm text-slate-500 mt-1 truncate">Status: {task.status} | Floor: {task.floor_id}</p>
                        </div>
                        {!isDone && (
                          <button onClick={() => handleCompleteTask(task.id || task._id)} className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg font-bold text-sm transition-colors shrink-0 w-full sm:w-auto">
                            Resolve
                          </button>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )}

          {/* HELP REQUESTS TAB */}
          {activeTab === 'help' && (
            <div className="bg-[#0F1523] border border-[#1E293B] rounded-xl p-6 h-full flex flex-col">
              <div className="flex items-center justify-between border-b border-[#1E293B] pb-4 mb-6 shrink-0">
                <h3 className="font-bold text-white flex items-center gap-2">
                  <span className="text-purple-400">✋</span> Guest Help Requests
                </h3>
              </div>
              
              {helpRequests.length === 0 ? (
                <div className="flex-1 flex flex-col items-center justify-center text-slate-600">
                  <p>No active help requests</p>
                </div>
              ) : (
                <div className="overflow-y-auto space-y-4 max-h-[600px] pr-2 custom-scrollbar">
                  {helpRequests.map((req) => {
                    const isDone = req.status === 'resolved';
                    return (
                      <div key={req.id || req._id} className={`bg-[#111A24] p-4 md:p-5 rounded-xl border flex flex-col sm:flex-row sm:items-center gap-3 md:gap-5 transition-all ${isDone ? 'border-emerald-900/50 opacity-50' : 'border-[#1E293B]'}`}>
                        <div className={`w-10 h-10 rounded-full flex items-center justify-center font-bold text-lg shrink-0 ${isDone ? 'bg-emerald-900 text-emerald-400' : 'bg-purple-500/10 text-purple-400 border border-purple-500/20'}`}>
                          {isDone ? '✓' : '!'}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className={`text-lg font-medium break-words ${isDone ? 'text-slate-400 line-through' : 'text-red-200'}`}>
                            {req.issue}
                          </p>
                          <p className="text-sm text-slate-500 mt-1 truncate">Location: {req.current_node || req.room_id} | Floor: {req.floor_id}</p>
                          <p className="text-xs text-slate-600 mt-1 truncate">Requested at: {new Date(req.created_at).toLocaleTimeString()}</p>
                        </div>
                        {!isDone && (
                          <button onClick={() => handleResolveHelp(req.id || req._id)} className="bg-purple-600 hover:bg-purple-500 text-white px-4 py-2 rounded-lg font-bold text-sm transition-colors shrink-0 w-full sm:w-auto">
                            Resolve
                          </button>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )}

          {/* FLOORS / MAP TAB */}
          {(activeTab === 'floors' || activeTab === 'map') && (
            <div className="bg-[#0F1523] border border-[#1E293B] rounded-xl p-6 h-full overflow-y-auto">
              <FloorMapPanel floors={floors} onRefresh={loadAll} />
            </div>
          )}

        </div>
      </main>

    </div>
  )
}

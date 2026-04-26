import { useState } from 'react'
import LandingView from './views/LandingView'
import StaffLoginView from './views/StaffLoginView'
import StaffDashboardView from './views/StaffDashboardView'
import GuestCheckinView from './views/GuestCheckinView'
import GuestDashboardView from './views/GuestDashboardView'

// ── App-level router ──────────────────────────────────────────
// Views: landing | staff-login | staff-dashboard | guest-checkin | guest-dashboard
export default function App() {
  const [view, setView] = useState('landing')
  const [staffSession, setStaffSession] = useState(null)   // { name, email, tokens }
  const [guestSession, setGuestSession] = useState(null)   // { session_id, room_id, floor_id }

  function goTo(v) { setView(v) }

  // ── Staff auth callbacks ──────────────────────────────────
  function onStaffLogin(data) {
    localStorage.setItem('staff_access_token', data.access_token)
    localStorage.setItem('staff_refresh_token', data.refresh_token)
    setStaffSession(data)
    setView('staff-dashboard')
  }

  function onStaffLogout() {
    localStorage.removeItem('staff_access_token')
    localStorage.removeItem('staff_refresh_token')
    setStaffSession(null)
    setView('landing')
  }

  // ── Guest auth callbacks ──────────────────────────────────
  function onGuestCheckin(data) {
    // data = { session_id, room_id, floor_id, access_token?, refresh_token? }
    if (data.access_token) {
      sessionStorage.setItem('guest_access_token', data.access_token)
      sessionStorage.setItem('guest_refresh_token', data.refresh_token)
    }
    setGuestSession(data)
    setView('guest-dashboard')
  }

  function onGuestExit() {
    sessionStorage.removeItem('guest_access_token')
    sessionStorage.removeItem('guest_refresh_token')
    setGuestSession(null)
    setView('landing')
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950">
      {view === 'landing' && (
        <LandingView onStaff={() => goTo('staff-login')} onGuest={() => goTo('guest-checkin')} />
      )}
      {view === 'staff-login' && (
        <StaffLoginView onLogin={onStaffLogin} onBack={() => goTo('landing')} />
      )}
      {view === 'staff-dashboard' && (
        <StaffDashboardView session={staffSession} onLogout={onStaffLogout} />
      )}
      {view === 'guest-checkin' && (
        <GuestCheckinView onCheckin={onGuestCheckin} onBack={() => goTo('landing')} />
      )}
      {view === 'guest-dashboard' && (
        <GuestDashboardView session={guestSession} onExit={onGuestExit} />
      )}
    </div>
  )
}

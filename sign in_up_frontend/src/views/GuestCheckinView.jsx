import { useState, useEffect } from 'react'
import { listRooms, checkIn, guestCheckin } from '../api/guestApi'

export default function GuestCheckinView({ onCheckin, onBack }) {
  const [rooms,       setRooms]       = useState([])
  const [roomId,      setRoomId]      = useState('')
  const [phone,       setPhone]       = useState('')
  const [loading,     setLoading]     = useState(false)
  const [loadingRooms, setLoadingRooms] = useState(true)
  const [error,       setError]       = useState('')
  const [searchQuery, setSearch]      = useState('')

  useEffect(() => {
    listRooms()
      .then(r => setRooms(r || []))
      .catch(() => {})
      .finally(() => setLoadingRooms(false))
  }, [])

  const filtered = rooms.filter(r =>
    !searchQuery ||
    r.room_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (r.label || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
    (r.floor_name || '').toLowerCase().includes(searchQuery.toLowerCase())
  )

  async function handleCheckin(e) {
    e.preventDefault()
    if (!roomId) return
    setError('')
    setLoading(true)
    try {
      // 1. Public check-in → creates session
      const sessionData = await checkIn(roomId)

      // 2. JWT auth check-in (optional — gets tokens)
      let tokens = {}
      try {
        tokens = await guestCheckin(roomId, phone || null)
      } catch {
        // Non-fatal — session still works without JWT for public endpoints
      }

      onCheckin({
        session_id:    sessionData.session_id,
        room_id:       sessionData.room_id || roomId,
        floor_id:      sessionData.floor_id,
        access_token:  tokens.access_token,
        refresh_token: tokens.refresh_token,
      })
    } catch (err) {
      setError(err.message)
    } finally { setLoading(false) }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4 animate-fadeIn">
      <div className="w-full max-w-lg">
        <button onClick={onBack} className="flex items-center gap-1 text-slate-400 hover:text-white text-sm mb-6 transition-colors">
          ← Back
        </button>

        <div className="card">
          {/* Header */}
          <div className="flex items-center gap-3 mb-6">
            <div className="w-10 h-10 rounded-xl bg-blue-600/20 flex items-center justify-center">
              <span className="text-xl">🧳</span>
            </div>
            <div>
              <h1 className="text-lg font-bold text-white">Guest Check-in</h1>
              <p className="text-slate-400 text-xs">Select your room to get your evacuation plan</p>
            </div>
          </div>

          <form onSubmit={handleCheckin} className="space-y-4">
            {/* Room picker */}
            <div>
              <label className="label">Your Room</label>
              {loadingRooms ? (
                <div className="input text-slate-500">Loading rooms…</div>
              ) : rooms.length > 0 ? (
                <>
                  <input
                    id="input-room-search"
                    className="input mb-2"
                    placeholder="Search rooms…"
                    value={searchQuery}
                    onChange={e => setSearch(e.target.value)}
                  />
                  <div className="max-h-48 overflow-y-auto rounded-xl border border-slate-700 bg-slate-900 divide-y divide-slate-800">
                    {filtered.length === 0 && (
                      <p className="text-slate-500 text-sm text-center py-4">No rooms found</p>
                    )}
                    {filtered.map(r => (
                      <button
                        key={r.room_id}
                        type="button"
                        id={`btn-room-${r.room_id}`}
                        onClick={() => { setRoomId(r.room_id); setSearch('') }}
                        className={`w-full text-left px-4 py-2.5 flex items-center justify-between hover:bg-slate-800 transition-colors ${roomId === r.room_id ? 'bg-blue-900/30 border-l-2 border-blue-500' : ''}`}
                      >
                        <div>
                          <span className="text-sm text-white font-medium">{r.label || r.room_id}</span>
                          <span className="text-xs text-slate-400 ml-2">({r.room_id})</span>
                        </div>
                        <span className="text-xs text-slate-500">{r.floor_name}</span>
                      </button>
                    ))}
                  </div>
                </>
              ) : (
                /* Fallback: manual entry */
                <input
                  id="input-room-id"
                  className="input"
                  placeholder="e.g. room_101"
                  value={roomId}
                  onChange={e => setRoomId(e.target.value)}
                  required
                />
              )}
              {roomId && (
                <p className="text-xs text-blue-400 mt-1.5">Selected: <strong>{roomId}</strong></p>
              )}
            </div>

            {/* Phone (optional) */}
            <div>
              <label className="label">Phone Number <span className="text-slate-600">(optional)</span></label>
              <input
                id="input-phone"
                type="tel"
                className="input"
                placeholder="+91 9876543210"
                value={phone}
                onChange={e => setPhone(e.target.value)}
              />
            </div>

            {error && (
              <div className="bg-red-900/30 border border-red-800 rounded-xl px-4 py-3 text-red-300 text-sm">
                {error}
              </div>
            )}

            <button
              id="btn-submit-checkin"
              type="submit"
              disabled={loading || !roomId}
              className="btn-primary w-full py-3 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Checking in…' : '🚪 Check In'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}

import { useState } from 'react'
import { staffLogin, staffRegister } from '../api/staffApi'

export default function StaffLoginView({ onLogin, onBack }) {
  const [mode, setMode]       = useState('login')   // 'login' | 'register'
  const [email, setEmail]     = useState('')
  const [password, setPass]   = useState('')
  const [name, setName]       = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      let data
      if (mode === 'login') {
        data = await staffLogin(email, password)
        onLogin(data)
      } else {
        await staffRegister(name, email, password)
        // Auto-login after register
        data = await staffLogin(email, password)
        onLogin(data)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4 animate-fadeIn">
      <div className="w-full max-w-md">
        <button onClick={onBack} className="flex items-center gap-1 text-slate-400 hover:text-white text-sm mb-6 transition-colors">
          ← Back
        </button>

        <div className="card">
          {/* Header */}
          <div className="flex items-center gap-3 mb-6">
            <div className="w-10 h-10 rounded-xl bg-brand-600/20 flex items-center justify-center">
              <span className="text-xl">👮</span>
            </div>
            <div>
              <h1 className="text-lg font-bold text-white">Staff Portal</h1>
              <p className="text-slate-400 text-xs">Emergency Management System</p>
            </div>
          </div>

          {/* Tab toggle */}
          <div className="flex gap-1 bg-slate-900 rounded-xl p-1 mb-6">
            <button
              id="tab-login"
              className={`flex-1 py-2 rounded-lg text-sm font-medium transition-all ${mode === 'login' ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-white'}`}
              onClick={() => { setMode('login'); setError('') }}
            >Sign In</button>
            <button
              id="tab-register"
              className={`flex-1 py-2 rounded-lg text-sm font-medium transition-all ${mode === 'register' ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-white'}`}
              onClick={() => { setMode('register'); setError('') }}
            >Register</button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {mode === 'register' && (
              <div>
                <label className="label">Full Name</label>
                <input id="input-name" className="input" placeholder="Jane Smith" value={name} onChange={e => setName(e.target.value)} required />
              </div>
            )}
            <div>
              <label className="label">Email</label>
              <input id="input-email" type="email" className="input" placeholder="staff@hotel.com" value={email} onChange={e => setEmail(e.target.value)} required />
            </div>
            <div>
              <label className="label">Password</label>
              <input id="input-password" type="password" className="input" placeholder="••••••••" value={password} onChange={e => setPass(e.target.value)} required />
            </div>

            {error && (
              <div className="bg-red-900/30 border border-red-800 rounded-xl px-4 py-3 text-red-300 text-sm">
                {error}
              </div>
            )}

            <button
              id="btn-submit-staff"
              type="submit"
              disabled={loading}
              className="btn-primary w-full py-3 mt-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? (
                <span className="flex items-center gap-2"><Spinner /> {mode === 'login' ? 'Signing in…' : 'Creating account…'}</span>
              ) : (
                mode === 'login' ? 'Sign In' : 'Create Account'
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}

function Spinner() {
  return (
    <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
}

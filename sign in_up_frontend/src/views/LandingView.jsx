// ── Landing: Choose Staff or Guest ───────────────────────────
export default function LandingView({ onStaff, onGuest }) {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-4 animate-fadeIn">
      {/* Background glow */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[600px] h-[300px] bg-brand-600/10 rounded-full blur-3xl" />
        <div className="absolute bottom-1/4 left-1/4 w-[400px] h-[200px] bg-blue-600/5 rounded-full blur-3xl" />
      </div>

      <div className="relative z-10 flex flex-col items-center max-w-lg w-full">
        {/* Logo / Brand */}
        <div className="mb-8 flex flex-col items-center">
          <div className="w-16 h-16 rounded-2xl bg-brand-600/20 border border-brand-600/30 flex items-center justify-center mb-4 shadow-lg shadow-brand-900/50">
            <span className="text-3xl">🚨</span>
          </div>
          <h1 className="text-3xl font-bold text-white tracking-tight">Emergency Response</h1>
          <p className="text-slate-400 mt-2 text-center text-sm">Smart Hotel Crisis Management Platform</p>
        </div>

        {/* Cards */}
        <div className="w-full grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Staff */}
          <button
            id="btn-staff-entry"
            onClick={onStaff}
            className="group card hover:border-brand-600/40 transition-all duration-300 hover:scale-[1.02] text-left cursor-pointer"
          >
            <div className="w-10 h-10 rounded-xl bg-brand-600/20 flex items-center justify-center mb-4 group-hover:bg-brand-600/30 transition-colors">
              <span className="text-xl">👮</span>
            </div>
            <h2 className="text-lg font-semibold text-white mb-1">Staff Portal</h2>
            <p className="text-slate-400 text-sm">Manage alerts, floor maps, and coordinate emergency response.</p>
            <div className="mt-4 flex items-center gap-1 text-brand-400 text-sm font-medium">
              Sign in <span className="group-hover:translate-x-1 transition-transform">→</span>
            </div>
          </button>

          {/* Guest */}
          <button
            id="btn-guest-entry"
            onClick={onGuest}
            className="group card hover:border-blue-600/40 transition-all duration-300 hover:scale-[1.02] text-left cursor-pointer"
          >
            <div className="w-10 h-10 rounded-xl bg-blue-600/20 flex items-center justify-center mb-4 group-hover:bg-blue-600/30 transition-colors">
              <span className="text-xl">🧳</span>
            </div>
            <h2 className="text-lg font-semibold text-white mb-1">Guest Access</h2>
            <p className="text-slate-400 text-sm">Get your personalised evacuation route and live safety updates.</p>
            <div className="mt-4 flex items-center gap-1 text-blue-400 text-sm font-medium">
              Check in <span className="group-hover:translate-x-1 transition-transform">→</span>
            </div>
          </button>
        </div>

        <p className="text-slate-600 text-xs mt-8">
          v2.0.0 · Smart Emergency Management Platform
        </p>
      </div>
    </div>
  )
}

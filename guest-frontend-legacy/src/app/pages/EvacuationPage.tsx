import { useEffect, useRef, useState, useCallback } from 'react';
import { useNavigate } from 'react-router';
import { guestClient, PathStep } from '../../api/guestClient';
import { useApp } from '../context/EvacuationContext';
import { POLLING } from '../../api/config';

// ── CSS injected once for animations ──────────────────────────────────────────
const EVAC_CSS = `
@keyframes evac-blink {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.5; }
}
@keyframes evac-pulse-ring {
  0%   { box-shadow: 0 0 0 0   rgba(239,68,68,0.8); }
  70%  { box-shadow: 0 0 0 16px rgba(239,68,68,0);   }
  100% { box-shadow: 0 0 0 0   rgba(239,68,68,0);   }
}
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes fade-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }

.evac-blink     { animation: evac-blink 1.4s ease-in-out infinite; }
.evac-ring      { animation: evac-pulse-ring 1.8s ease-in-out infinite; }
.evac-fade-in   { animation: fade-in 0.25s ease both; }
.evac-spin      { animation: spin 0.7s linear infinite; }
`;

// ── Audio SOS beep ────────────────────────────────────────────────────────────
function playBeep() {
  try {
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain); gain.connect(ctx.destination);
    osc.type = 'sine';
    osc.frequency.setValueAtTime(880, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(440, ctx.currentTime + 0.3);
    gain.gain.setValueAtTime(0.35, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.4);
  } catch { /* blocked before user interaction */ }
}

/**
 * EvacuationPage — The most critical screen.
 *
 * Hardening Applied:
 * - Smart Polling: Compare new vs old path (Phase 11)
 * - Offline Fallback: Cache in localStorage (Phase 12)
 * - Reroute UX: Disable button, spinner, error messages (Phase 14)
 * - Edge States: Empty path → /safe, Missing session → /check-in (Phase 15)
 * - Get Help: Real-time POST → staff dashboard WebSocket broadcast
 * - Urgency UI: Blinking header, pulsing ring, sticky help button, vibration
 */
export function EvacuationPage() {
  const navigate = useNavigate();
  const { session, emergencyStatus, currentPath, setCurrentPath } = useApp();
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const cssInjected = useRef(false);

  const [steps, setSteps] = useState<PathStep[]>(currentPath || []);
  const [pathLoading, setPathLoading]     = useState(true);
  const [rerouteLoading, setRerouteLoading] = useState(false);
  const [rerouted, setRerouted]           = useState(false);
  const [rerouteError, setRerouteError]   = useState(false);
  const [offlineMode, setOfflineMode]     = useState(false);

  // Help state
  const [helpSending, setHelpSending]     = useState(false);
  const [helpSent, setHelpSent]           = useState(false);
  const [helpError, setHelpError]         = useState('');

  const prevPathRef = useRef<string>(
    currentPath ? JSON.stringify(currentPath.map(s => s.node)) : ''
  );

  // ── Inject CSS once ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (cssInjected.current) return;
    cssInjected.current = true;
    const el = document.createElement('style');
    el.textContent = EVAC_CSS;
    document.head.appendChild(el);
    return () => { el.remove(); };
  }, []);

  // ── On mount: vibrate + audio ───────────────────────────────────────────────
  useEffect(() => {
    if ('vibrate' in navigator) navigator.vibrate([200, 100, 200, 100, 600]);
    const t = setTimeout(playBeep, 300);
    return () => clearTimeout(t);
  }, []);

  // ── Session guard ───────────────────────────────────────────────────────────
  useEffect(() => {
    if (!session) navigate('/check-in', { replace: true });
  }, [session, navigate]);

  // ── Path fetcher ────────────────────────────────────────────────────────────
  const fetchPath = useCallback(async () => {
    if (!session) return;
    try {
      const res = await guestClient.getPath(session.session_id);
      const newSteps = res.steps ?? [];

      const emergencyActive =
        emergencyStatus?.active === true || emergencyStatus?.status === 'active';
      if (newSteps.length === 0 && !emergencyActive) {
        navigate('/safe', { replace: true });
        return;
      }

      setOfflineMode(false);

      const newSig = JSON.stringify(newSteps.map(s => s.node));
      if (newSig !== prevPathRef.current) {
        prevPathRef.current = newSig;
        setSteps(newSteps);
        setCurrentPath(newSteps);

        if (prevPathRef.current !== '' && steps.length > 0) {
          setRerouted(true);
          setTimeout(() => setRerouted(false), 3000);
        }
      }
    } catch {
      setOfflineMode(true);
      const cachedStr = localStorage.getItem('offline_path');
      if (cachedStr) {
        try {
          const cached = JSON.parse(cachedStr) as PathStep[];
          if (cached.length > 0 && steps.length === 0) {
            setSteps(cached);
            setCurrentPath(cached);
          }
        } catch { /* ignore */ }
      }
    } finally {
      setPathLoading(false);
    }
  }, [session, navigate, setCurrentPath, steps.length, emergencyStatus]);

  // ── Start polling ───────────────────────────────────────────────────────────
  useEffect(() => {
    if (!session) return;
    fetchPath();
    intervalRef.current = setInterval(fetchPath, POLLING.PATH);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [session, fetchPath]);

  // ── Reroute ─────────────────────────────────────────────────────────────────
  async function handleReroute() {
    if (!session || rerouteLoading || offlineMode) return;
    setRerouteLoading(true);
    setRerouteError(false);
    try {
      const res = await guestClient.reroute(session.session_id);
      const newSteps = res.steps ?? [];
      prevPathRef.current = JSON.stringify(newSteps.map(s => s.node));
      setSteps(newSteps);
      setCurrentPath(newSteps);
      setRerouted(true);
      setTimeout(() => setRerouted(false), 3000);
    } catch {
      setRerouteError(true);
      setTimeout(() => setRerouteError(false), 3000);
    } finally {
      setRerouteLoading(false);
    }
  }

  // ── Get Help → real-time POST to staff backend ──────────────────────────────
  async function handleGetHelp() {
    if (helpSent || helpSending || !session) return;
    setHelpSending(true);
    setHelpError('');
    try {
      await guestClient.requestHelp({
        sessionId:   session.session_id,
        currentNode: steps[0]?.node ?? session.room_id ?? 'unknown',
        issue:       `Emergency assistance needed — ${emergencyType || 'EVACUATION'}`,
        floorId:     session.floor_id ?? null,
      });
      setHelpSent(true);
      if ('vibrate' in navigator) navigator.vibrate([100, 50, 100]);
    } catch (e) {
      setHelpError(e instanceof Error ? e.message : 'Failed — try again');
      setTimeout(() => setHelpError(''), 5000);
    }
    setHelpSending(false);
  }

  const currentInstruction = steps[0];
  const emergencyType = emergencyStatus?.emergency_type?.toUpperCase() ?? '';

  if (!session) return null;

  return (
    <div style={S.page}>
      {/* ── EMERGENCY HEADER (blinking, full-red, sticky) ──────────────────── */}
      <div style={S.topBand} className="evac-blink" role="alert" aria-live="assertive">
        <div style={S.evacuateLabel}>🚨 EVACUATE IMMEDIATELY</div>
        {emergencyType && <div style={S.emergencyType}>{emergencyType}</div>}
      </div>

      {/* ── Status banners ─────────────────────────────────────────────────── */}
      {offlineMode && (
        <div style={S.offlineBanner} className="evac-fade-in" role="alert">
          ⚠ Network issue — follow last known route
        </div>
      )}
      {rerouted && !offlineMode && (
        <div style={S.reroutedBanner} className="evac-fade-in" role="status">
          ↩ Route updated — new path calculated
        </div>
      )}

      {/* ── Main instruction area ───────────────────────────────────────────── */}
      <div style={S.instructionArea}>
        {pathLoading && steps.length === 0 ? (
          <div style={S.loadingBlock}>
            <div className="evac-spin" style={S.spinner} />
            <p style={S.loadingText}>Calculating your route…</p>
          </div>
        ) : !currentInstruction ? (
          <div style={S.errorBlock}>
            <p style={S.errorTitle}>⚠ No path found</p>
            <p style={S.errorSub}>Stay calm. Follow floor signage to nearest exit.</p>
          </div>
        ) : (
          <>
            {/* Pulsing ring around step number */}
            <div style={S.stepBadge} className="evac-ring">
              <span style={S.stepNum}>1</span>
            </div>

            <p style={S.instructionText} aria-live="polite" className="evac-fade-in">
              {currentInstruction.instruction}
            </p>

            {steps.length > 1 && (
              <p style={S.nextHint}>
                Then: {steps[1].instruction}
              </p>
            )}

            {/* Mini route preview */}
            {steps.length > 2 && (
              <div style={S.routeRow}>
                {steps.slice(0, 4).map((s, i) => (
                  <span key={i} style={{
                    ...S.routeChip,
                    background: i === 0 ? 'rgba(239,68,68,0.25)' : 'rgba(255,255,255,0.04)',
                    border: i === 0 ? '1px solid rgba(239,68,68,0.5)' : '1px solid rgba(255,255,255,0.08)',
                    color: i === 0 ? '#FCA5A5' : '#475569',
                  }}>
                    {i + 1}. {s.node}
                  </span>
                ))}
                {steps.length > 4 && <span style={{ ...S.routeChip, color: '#374151' }}>+{steps.length - 4} more</span>}
              </div>
            )}
          </>
        )}
      </div>

      {/* ── Bottom actions ─────────────────────────────────────────────────── */}
      <div style={S.bottom}>
        {rerouteError && (
          <p style={S.rerouteErrorText} className="evac-fade-in">Reroute failed — retrying…</p>
        )}

        {/* Reroute button */}
        <button
          id="btn-reroute"
          onClick={handleReroute}
          disabled={rerouteLoading || pathLoading || offlineMode || steps.length === 0}
          style={{
            ...S.rerouteBtn,
            opacity: rerouteLoading || pathLoading || offlineMode || steps.length === 0 ? 0.45 : 1,
            cursor: rerouteLoading || pathLoading || offlineMode ? 'wait' : 'pointer',
          }}
          aria-label="Request alternate evacuation route"
        >
          {rerouteLoading ? (
            <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
              <div className="evac-spin" style={{ width: 16, height: 16, border: '2px solid rgba(252,211,77,0.3)', borderTopColor: '#FCD34D', borderRadius: '50%' }} />
              REROUTING…
            </span>
          ) : 'REQUEST REROUTE'}
        </button>

        {/* Get Help button */}
        <button
          id="btn-get-help"
          onClick={handleGetHelp}
          disabled={helpSending || helpSent}
          style={{
            ...S.helpBtn,
            ...(helpSent ? S.helpBtnSent : {}),
            opacity: helpSending ? 0.7 : 1,
          }}
          className={helpSent ? '' : 'evac-ring'}
          aria-label="Request immediate staff assistance"
        >
          {helpSending ? (
            <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
              <div className="evac-spin" style={{ width: 16, height: 16, border: '2px solid rgba(255,255,255,0.3)', borderTopColor: 'white', borderRadius: '50%' }} />
              ALERTING STAFF…
            </span>
          ) : helpSent ? (
            '✓ STAFF NOTIFIED — HELP IS ON THE WAY'
          ) : (
            '🚑 GET HELP NOW'
          )}
        </button>

        {helpError && (
          <p style={S.helpErrorText} className="evac-fade-in">{helpError}</p>
        )}
      </div>
    </div>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const S: Record<string, React.CSSProperties> = {
  page: {
    height: '100vh',
    maxHeight: '100vh',
    overflow: 'hidden',
    background: '#0B0F14',
    color: 'white',
    display: 'flex',
    flexDirection: 'column',
  },
  topBand: {
    background: '#DC2626',        // solid red — NOT transparent
    borderBottom: '3px solid #EF4444',
    padding: '18px 24px 14px',
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
    flexShrink: 0,
    boxShadow: '0 4px 24px rgba(220,38,38,0.5)',
  },
  evacuateLabel: {
    fontSize: 20,
    fontWeight: 900,
    color: '#FFFFFF',
    letterSpacing: '0.07em',
    textShadow: '0 1px 4px rgba(0,0,0,0.4)',
  },
  emergencyType: {
    fontSize: 11,
    fontFamily: 'monospace',
    color: 'rgba(255,255,255,0.75)',
    letterSpacing: '0.2em',
  },
  reroutedBanner: {
    background: 'rgba(245,158,11,0.15)',
    borderBottom: '1px solid rgba(245,158,11,0.3)',
    color: '#FCD34D',
    textAlign: 'center',
    padding: '10px',
    fontSize: 13,
    fontFamily: 'monospace',
    letterSpacing: '0.1em',
    flexShrink: 0,
  },
  offlineBanner: {
    background: 'rgba(239,68,68,0.15)',
    borderBottom: '1px solid rgba(239,68,68,0.35)',
    color: '#FCA5A5',
    textAlign: 'center',
    padding: '10px',
    fontSize: 13,
    fontFamily: 'monospace',
    letterSpacing: '0.1em',
    flexShrink: 0,
  },
  instructionArea: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '28px 24px 12px',
    gap: 20,
    textAlign: 'center',
  },
  stepBadge: {
    width: 56,
    height: 56,
    borderRadius: '50%',
    background: 'rgba(239,68,68,0.2)',
    border: '2px solid rgba(239,68,68,0.6)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  stepNum: {
    fontSize: 22,
    fontWeight: 900,
    color: '#FCA5A5',
    fontFamily: 'monospace',
  },
  instructionText: {
    fontSize: 'clamp(26px, 7.5vw, 50px)',
    fontWeight: 900,
    color: '#F1F5F9',
    lineHeight: 1.15,
    letterSpacing: '-0.01em',
    margin: 0,
  },
  nextHint: {
    fontSize: 14,
    color: '#475569',
    fontFamily: 'monospace',
    margin: 0,
    letterSpacing: '0.02em',
    maxWidth: 360,
  },
  routeRow: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: 6,
    justifyContent: 'center',
    maxWidth: 400,
  },
  routeChip: {
    fontSize: 11,
    fontFamily: 'monospace',
    padding: '3px 8px',
    borderRadius: 6,
    letterSpacing: '0.05em',
  },
  loadingBlock: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 16,
  },
  spinner: {
    width: 36,
    height: 36,
    border: '3px solid rgba(255,255,255,0.08)',
    borderTopColor: '#EF4444',
    borderRadius: '50%',
  },
  loadingText: {
    color: '#475569',
    fontFamily: 'monospace',
    fontSize: 13,
    letterSpacing: '0.1em',
    margin: 0,
  },
  errorBlock: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 12,
  },
  errorTitle: {
    color: '#F59E0B',
    fontWeight: 700,
    fontSize: 18,
    margin: 0,
  },
  errorSub: {
    color: '#94A3B8',
    fontSize: 15,
    margin: 0,
    lineHeight: 1.5,
    maxWidth: 300,
  },
  bottom: {
    padding: '16px 20px 32px',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 10,
    flexShrink: 0,
  },
  rerouteBtn: {
    width: '100%',
    maxWidth: 420,
    padding: '16px 24px',
    borderRadius: 14,
    border: '2px solid rgba(245,158,11,0.5)',
    background: 'rgba(245,158,11,0.08)',
    color: '#FCD34D',
    fontSize: 14,
    fontWeight: 800,
    fontFamily: 'monospace',
    letterSpacing: '0.1em',
    cursor: 'pointer',
    transition: 'opacity 0.2s, background 0.2s',
  },
  helpBtn: {
    width: '100%',
    maxWidth: 420,
    padding: '18px 24px',
    borderRadius: 14,
    border: '2px solid rgba(239,68,68,0.7)',
    background: '#DC2626',
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: 900,
    fontFamily: 'monospace',
    letterSpacing: '0.08em',
    cursor: 'pointer',
    transition: 'background 0.2s',
    boxShadow: '0 4px 20px rgba(220,38,38,0.35)',
  },
  helpBtnSent: {
    background: 'rgba(34,197,94,0.15)',
    border: '2px solid rgba(34,197,94,0.5)',
    color: '#4ADE80',
    cursor: 'default',
    boxShadow: 'none',
  },
  rerouteErrorText: {
    color: '#F87171',
    fontSize: 12,
    fontFamily: 'monospace',
    margin: 0,
  },
  helpErrorText: {
    color: '#F87171',
    fontSize: 12,
    fontFamily: 'monospace',
    margin: 0,
    textAlign: 'center',
  },
};

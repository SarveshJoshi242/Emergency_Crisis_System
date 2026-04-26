import { useState } from 'react';
import { guestClient } from '../../api/guestClient';
import { useApp } from '../context/EvacuationContext';

/**
 * SafeZonePage — You are safe.
 *
 * Shows:
 *   - ✅ "You Are Safe"
 *   - Assembly point instructions
 *   - "Mark Evacuation Complete" → POST /guest/reached-safe-zone
 *
 * Nothing else.
 */
export function SafeZonePage() {
  const { session, setSession } = useApp();
  const [marking, setMarking] = useState(false);
  const [marked, setMarked] = useState(false);
  const [markError, setMarkError] = useState(false);

  async function handleMarkComplete() {
    if (!session || marking || marked) return;
    setMarking(true);
    setMarkError(false);
    try {
      await guestClient.confirmSafeZone(session.session_id);
      setMarked(true);
      setSession(null); // clear session after completion
    } catch {
      setMarkError(true);
    } finally {
      setMarking(false);
    }
  }

  return (
    <div style={styles.page}>
      {/* ── Safe icon ── */}
      <div style={styles.icon} aria-hidden="true">✅</div>

      {/* ── Primary message ── */}
      <h1 style={styles.title}>You Are Safe</h1>

      {/* ── Assembly instructions ── */}
      <div style={styles.instructionCard}>
        <div style={styles.instructionItem}>
          🚶 Move away from the building immediately
        </div>
        <div style={styles.instructionItem}>
          📍 Go to the designated assembly point
        </div>
        <div style={styles.instructionItem}>
          🧑‍🚒 Wait for staff and follow their instructions
        </div>
        <div style={styles.instructionItem}>
          📵 Do not re-enter the building
        </div>
      </div>

      {/* ── Mark complete ── */}
      {!marked ? (
        <>
          <button
            id="btn-mark-complete"
            onClick={handleMarkComplete}
            disabled={marking}
            style={{
              ...styles.ctaBtn,
              opacity: marking ? 0.6 : 1,
              cursor: marking ? 'wait' : 'pointer',
            }}
            aria-label="Mark evacuation complete"
          >
            {marking ? 'Marking…' : '✓ MARK EVACUATION COMPLETE'}
          </button>
          {markError && (
            <p style={styles.errorText}>
              Could not reach server. You can proceed — staff will update your status.
            </p>
          )}
        </>
      ) : (
        <div style={styles.confirmedBadge}>
          ✓ EVACUATION RECORDED — STAY AT ASSEMBLY POINT
        </div>
      )}
    </div>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: '100vh',
    background: '#0B0F14',
    color: 'white',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '40px 24px',
    gap: 24,
  },
  icon: {
    fontSize: 72,
    lineHeight: 1,
  },
  title: {
    fontSize: 'clamp(36px, 9vw, 56px)',
    fontWeight: 900,
    color: '#22C55E',
    margin: 0,
    letterSpacing: '-0.02em',
    textAlign: 'center',
  },
  instructionCard: {
    width: '100%',
    maxWidth: 420,
    background: '#121821',
    border: '1px solid #1F2937',
    borderRadius: 16,
    padding: '20px 24px',
    display: 'flex',
    flexDirection: 'column',
    gap: 14,
  },
  instructionItem: {
    fontSize: 15,
    color: '#94A3B8',
    lineHeight: 1.4,
  },
  ctaBtn: {
    width: '100%',
    maxWidth: 420,
    padding: '18px 24px',
    borderRadius: 14,
    border: '2px solid rgba(34,197,94,0.5)',
    background: 'rgba(34,197,94,0.12)',
    color: '#22C55E',
    fontSize: 16,
    fontWeight: 800,
    fontFamily: 'monospace',
    letterSpacing: '0.08em',
    cursor: 'pointer',
  },
  confirmedBadge: {
    width: '100%',
    maxWidth: 420,
    padding: '18px 24px',
    borderRadius: 14,
    border: '1px solid rgba(34,197,94,0.3)',
    background: 'rgba(34,197,94,0.08)',
    color: '#4ADE80',
    fontSize: 14,
    fontWeight: 700,
    fontFamily: 'monospace',
    letterSpacing: '0.08em',
    textAlign: 'center',
  },
  errorText: {
    fontSize: 13,
    color: '#F87171',
    textAlign: 'center',
    maxWidth: 380,
    margin: 0,
    lineHeight: 1.5,
    fontFamily: 'monospace',
  },
};
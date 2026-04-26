import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router';
import { guestClient } from '../../api/guestClient';
import { useApp } from '../context/EvacuationContext';
import { POLLING } from '../../api/config';

/**
 * Dashboard — No Emergency state.
 *
 * Phase 10: Smart Polling (no UI flicker)
 * Phase 15: Edge states (checking system on fail, force redirect if session missing)
 */
export function DashboardPage() {
  const navigate = useNavigate();
  const { session, emergencyStatus, setEmergencyStatus } = useApp();
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Hardening: Guard against missing session mid-flow
  useEffect(() => {
    if (!session) {
      navigate('/check-in', { replace: true });
    }
  }, [session, navigate]);

  // Phase 10: Smart Polling
  useEffect(() => {
    if (!session) return;

    async function poll() {
      try {
        const newStatus = await guestClient.getEmergencyStatus();
        
        // Only update state if JSON signature changes to prevent re-renders
        setEmergencyStatus(prev => {
          if (!prev || JSON.stringify(prev) !== JSON.stringify(newStatus)) {
            return newStatus;
          }
          return prev;
        });

        // Auto redirect to evacuation if emergency goes active
        // Check both .active (primary) and .status (normalized field)
        if (newStatus.active === true || newStatus.status === 'active') {
          navigate('/evacuation', { replace: true });
        }
      } catch {
        // Handle failure by safely keeping last cached status to prevent flicker
        setEmergencyStatus(prev => prev ?? null);
      }
    }

    poll(); // immediate first call
    intervalRef.current = setInterval(poll, POLLING.EMERGENCY_STATUS);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [session, navigate, setEmergencyStatus]);

  if (!session) return null;

  const isChecking = emergencyStatus === null;
  // Check .active (primary bool) OR .status string — supports both response shapes
  const isActive = emergencyStatus?.active === true || emergencyStatus?.status === 'active';

  return (
    <div style={styles.page}>
      {/* ── Status Banner ── */}
      <div
        style={{
          ...styles.statusCard,
          borderColor: isActive
            ? 'rgba(239,68,68,0.5)'
            : isChecking
              ? 'rgba(100,116,139,0.3)'
              : 'rgba(34,197,94,0.35)',
        }}
        role="status"
        aria-live="polite"
      >
        <div
          style={{
            ...styles.statusDot,
            background: isActive ? '#EF4444' : isChecking ? '#475569' : '#22C55E',
          }}
        />
        <div>
          <div style={styles.statusLabel}>SYSTEM STATUS</div>
          <div
            style={{
              ...styles.statusValue,
              color: isActive ? '#EF4444' : isChecking ? '#94A3B8' : '#22C55E',
            }}
          >
            {isChecking
              ? 'Checking system…'
              : isActive
                ? `EMERGENCY${emergencyStatus?.emergency_type ? ` — ${emergencyStatus.emergency_type.toUpperCase()}` : ''}`
                : 'NO EMERGENCY — STAY ALERT'}
          </div>
        </div>
      </div>

      {/* ── Room Info ── */}
      <div style={styles.roomCard}>
        <div style={styles.roomLabel}>YOUR ROOM</div>
        <div style={styles.roomId}>{session.room_id}</div>
        <div style={styles.roomFloor}>
          {session.floor_id?.replace('floor_', 'Floor ') ?? ''}
        </div>
      </div>

      {/* ── Passive instruction ── */}
      <p style={styles.hint}>
        This screen updates automatically.{'\n'}No action required unless emergency is declared.
      </p>
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
    padding: '32px 20px',
    gap: 20,
  },
  statusCard: {
    width: '100%',
    maxWidth: 420,
    background: '#121821',
    border: '2px solid',
    borderRadius: 16,
    padding: '24px 24px',
    display: 'flex',
    alignItems: 'center',
    gap: 20,
  },
  statusDot: {
    width: 16,
    height: 16,
    borderRadius: '50%',
    flexShrink: 0,
  },
  statusLabel: {
    fontSize: 11,
    fontFamily: 'monospace',
    letterSpacing: '0.2em',
    color: '#475569',
    marginBottom: 6,
  },
  statusValue: {
    fontSize: 18,
    fontWeight: 800,
    letterSpacing: '0.02em',
    lineHeight: 1.2,
  },
  roomCard: {
    width: '100%',
    maxWidth: 420,
    background: '#121821',
    border: '1px solid #1F2937',
    borderRadius: 16,
    padding: '24px 24px',
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
  },
  roomLabel: {
    fontSize: 11,
    fontFamily: 'monospace',
    letterSpacing: '0.2em',
    color: '#475569',
  },
  roomId: {
    fontSize: 36,
    fontWeight: 900,
    color: '#F1F5F9',
    letterSpacing: '-0.01em',
    lineHeight: 1,
  },
  roomFloor: {
    fontSize: 13,
    fontFamily: 'monospace',
    color: '#475569',
  },
  hint: {
    maxWidth: 420,
    textAlign: 'center',
    color: '#334155',
    fontSize: 12,
    fontFamily: 'monospace',
    lineHeight: 1.8,
    whiteSpace: 'pre-line',
    marginTop: 8,
  },
};

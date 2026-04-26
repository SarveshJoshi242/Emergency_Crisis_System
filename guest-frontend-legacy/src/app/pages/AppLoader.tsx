import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { guestClient } from '../../api/guestClient';
import { useApp } from '../context/EvacuationContext';

/**
 * AppLoader — No UI. Pure routing logic.
 *
 * Phase 13 Hardening:
 *   1. Read session_id from localStorage
 *   2. Strict validation via GET /guest/session
 *   3. If invalid -> clear storage -> /check-in
 */
export function AppLoader() {
  const navigate = useNavigate();
  const { setSession, setEmergencyStatus } = useApp();
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      const storedId = localStorage.getItem('session_id');

      if (!storedId) {
        navigate('/check-in', { replace: true });
        return;
      }

      try {
        const session = await guestClient.getSession(storedId);

        if (cancelled) return;

        // If session is completely dead or abandoned
        if (!session || session.status === 'abandoned') {
          localStorage.removeItem('session_id');
          localStorage.removeItem('offline_path');
          navigate('/check-in', { replace: true });
          return;
        }

        setSession(session);

        // Already safe — go straight to safe screen
        if (session.status === 'safe') {
          navigate('/safe', { replace: true });
          return;
        }

        // Check emergency status to decide dashboard vs evacuation
        const status = await guestClient.getEmergencyStatus();
        if (cancelled) return;

        setEmergencyStatus(status);

        // Check both .active and .status for robustness
        if (status.active === true || status.status === 'active') {
          navigate('/evacuation', { replace: true });
        } else {
          navigate('/dashboard', { replace: true });
        }
      } catch {
        if (!cancelled) {
          // Hardening: If network fails during initial load, we DO NOT clear session.
          // We assume session might be valid, but we can't reach the server.
          // Route to check-in for safety, but keep ID so it can be resumed later if possible.
          navigate('/check-in', { replace: true });
        }
      } finally {
        if (!cancelled) setChecking(false);
      }
    }

    bootstrap();
    return () => { cancelled = true; };
  }, [navigate, setSession, setEmergencyStatus]);

  if (!checking) return null;

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#0B0F14',
      }}
    >
      <div style={{ textAlign: 'center' }}>
        <div
          style={{
            width: 40,
            height: 40,
            border: '3px solid #1F2937',
            borderTopColor: '#22C55E',
            borderRadius: '50%',
            animation: 'spin 0.8s linear infinite',
            margin: '0 auto 16px',
          }}
        />
        <p style={{ color: '#475569', fontFamily: 'monospace', fontSize: 13, letterSpacing: '0.1em' }}>
          CONNECTING…
        </p>
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

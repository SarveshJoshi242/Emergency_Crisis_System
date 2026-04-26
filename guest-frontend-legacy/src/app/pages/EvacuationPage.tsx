import { useEffect, useRef, useState, useCallback } from 'react';
import { useNavigate } from 'react-router';
import { guestClient } from '../../api/guestClient';
import { useApp } from '../context/EvacuationContext';

const EVAC_CSS = `
@keyframes evac-blink {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.5; }
}
.evac-blink { animation: evac-blink 1.4s ease-in-out infinite; }
`;

export function EvacuationPage() {
  const navigate = useNavigate();
  const { session } = useApp();
  const [routeBlocked, setRouteBlocked] = useState(false);
  const [blockedMessage, setBlockedMessage] = useState("");
  const [broadcasts, setBroadcasts] = useState<any[]>([]);

  useEffect(() => {
    const el = document.createElement('style');
    el.textContent = EVAC_CSS;
    document.head.appendChild(el);
    return () => { el.remove(); };
  }, []);

  useEffect(() => {
    if ('vibrate' in navigator) navigator.vibrate([200, 100, 200, 100, 600]);
  }, []);

  useEffect(() => {
    if (!session) navigate('/check-in', { replace: true });
  }, [session, navigate]);

  // WebSocket Connection for route_update and broadcast_message
  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8001/ws/live');
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.event === 'route_update') {
          setRouteBlocked(true);
          setBlockedMessage(msg.data.message || "Route blocked. Use alternate stairs.");
          if ('vibrate' in navigator) navigator.vibrate([500, 200, 500]);
        } else if (msg.event === 'broadcast_message') {
          setBroadcasts(prev => [msg.data, ...prev]);
          if ('vibrate' in navigator) navigator.vibrate([300, 100, 300]);
        }
      } catch (e) {
        console.error(e);
      }
    };
    return () => ws.close();
  }, []);

  // Fetch existing active broadcasts on mount
  useEffect(() => {
    if (session?.floor_id) {
      guestClient.getNotifications(session.floor_id)
        .then(data => {
          if (data.messages && data.messages.length > 0) {
            setBroadcasts(data.messages);
          }
        })
        .catch(err => console.error("Failed to fetch notifications", err));
    }
  }, [session]);

  if (!session) return null;

  return (
    <div style={{ height: '100vh', background: '#0B0F14', color: 'white', display: 'flex', flexDirection: 'column', fontFamily: 'sans-serif' }}>
      
      {/* HEADER */}
      <div className="evac-blink" style={{ background: '#DC2626', padding: '20px', textAlign: 'center', boxShadow: '0 4px 20px rgba(220,38,38,0.5)', zIndex: 10 }}>
        <h1 style={{ margin: 0, fontSize: '24px', fontWeight: 900, letterSpacing: '2px', color: 'white' }}>🚨 EVACUATE IMMEDIATELY</h1>
        <p style={{ margin: '5px 0 0', fontSize: '12px', fontWeight: 'bold', letterSpacing: '1px', opacity: 0.9 }}>FIRE EMERGENCY REPORTED</p>
      </div>

      {/* REROUTE WARNING */}
      {routeBlocked && (
        <div style={{ background: '#F59E0B', color: 'black', padding: '15px', textAlign: 'center', fontWeight: 'bold', fontSize: '18px', borderBottom: '4px solid #B45309' }}>
          ⚠️ {blockedMessage}
        </div>
      )}

      {/* BROADCAST MESSAGES */}
      {broadcasts.map((b, idx) => (
        <div key={b.id || idx} style={{ 
          background: b.priority === 'critical' ? '#EF4444' : b.priority === 'warning' ? '#F59E0B' : '#3B82F6', 
          color: 'white', 
          padding: '15px', 
          textAlign: 'center', 
          fontWeight: 'bold', 
          fontSize: '18px', 
          borderBottom: '4px solid rgba(0,0,0,0.2)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '10px'
        }}>
          <span>📢</span>
          <span style={{ flex: 1 }}>{b.message}</span>
          <button 
            onClick={() => setBroadcasts(prev => prev.filter(x => x !== b))}
            style={{ background: 'rgba(255,255,255,0.2)', border: 'none', color: 'white', borderRadius: '50%', width: '30px', height: '30px', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
          >
            ✕
          </button>
        </div>
      ))}

      {/* STEPS */}
      <div style={{ flex: 1, padding: '20px', overflowY: 'auto' }}>
        <h2 style={{ fontSize: '20px', color: '#94A3B8', marginBottom: '20px', textTransform: 'uppercase', letterSpacing: '1px' }}>Step-by-Step Instructions</h2>
        
        <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
          {[
            "Leave your room immediately",
            "Walk towards the corridor",
            "Use the nearest staircase",
            "Do NOT use elevators",
            "Exit the building calmly"
          ].map((step, idx) => (
            <div key={idx} style={{ 
              background: '#1E293B', 
              padding: '20px', 
              borderRadius: '12px', 
              borderLeft: '6px solid #EF4444',
              display: 'flex',
              alignItems: 'center',
              gap: '15px',
              fontSize: '22px',
              fontWeight: 'bold',
              color: '#F8FAFC'
            }}>
              <div style={{ width: '35px', height: '35px', background: '#334155', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '18px', flexShrink: 0 }}>
                {idx + 1}
              </div>
              {step}
            </div>
          ))}
        </div>
      </div>

      {/* CALL EMERGENCY BUTTON */}
      <div style={{ padding: '20px', background: '#0F172A', borderTop: '1px solid #1E293B' }}>
        <a 
          href="tel:911" 
          style={{ 
            display: 'block', 
            width: '100%', 
            padding: '20px', 
            background: '#EF4444', 
            color: 'white', 
            textAlign: 'center', 
            fontSize: '20px', 
            fontWeight: 900, 
            borderRadius: '12px', 
            textDecoration: 'none',
            letterSpacing: '1px',
            boxShadow: '0 4px 15px rgba(239,68,68,0.4)'
          }}
        >
          🔴 CALL EMERGENCY
        </a>
      </div>
    </div>
  );
}

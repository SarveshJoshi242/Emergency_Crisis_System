import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router';
import { guestClient, RoomEntry } from '../../api/guestClient';
import { useApp } from '../context/EvacuationContext';

// ─────────────────────────────────────────────────────────────────────────────
// GuestEntry — Room picker / check-in page.
//
// All rooms are fetched DYNAMICALLY from GET /guest/rooms.
// No hardcoded floor IDs or room lists.
// Any room that exists in any floor graph will appear here.
// ─────────────────────────────────────────────────────────────────────────────

function groupByFloor(rooms: RoomEntry[]): Record<string, RoomEntry[]> {
  const groups: Record<string, RoomEntry[]> = {};
  for (const room of rooms) {
    if (!groups[room.floor_id]) groups[room.floor_id] = [];
    groups[room.floor_id].push(room);
  }
  return groups;
}

function floorDisplayName(floorId: string, floorName?: string): string {
  if (floorName && floorName !== floorId) return floorName;
  // Turn "floor_1" → "Floor 1", or show raw ID
  const match = floorId.match(/floor_?(\d+)/i);
  if (match) return `Floor ${match[1]}`;
  return floorId;
}

export function GuestEntry() {
  const navigate = useNavigate();
  const { setSession } = useApp();

  const [rooms, setRooms]                     = useState<RoomEntry[]>([]);
  const [loadingRooms, setLoadingRooms]        = useState(true);
  const [submittingRoom, setSubmittingRoom]    = useState<string | null>(null);
  const [error, setError]                     = useState<string | null>(null);

  // ── Fetch all rooms dynamically on mount ────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    setLoadingRooms(true);

    guestClient.getRooms()
      .then(data => {
        if (!cancelled) {
          setRooms(data);
          setLoadingRooms(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError('Could not load room list. Please check your connection.');
          setLoadingRooms(false);
        }
      });

    return () => { cancelled = true; };
  }, []);

  // ── Check-in handler ────────────────────────────────────────────────────
  async function handleRoomClick(roomId: string) {
    if (submittingRoom) return;
    setSubmittingRoom(roomId);
    setError(null);

    try {
      const session = await guestClient.checkIn(roomId);
      setSession(session);
      navigate('/dashboard', { replace: true });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Check-in failed.';
      setError(`Check-in failed: ${msg}`);
      setSubmittingRoom(null);
    }
  }

  const grouped   = groupByFloor(rooms);
  const floorKeys = Object.keys(grouped).sort();
  const hasRooms  = rooms.length > 0;

  return (
    <div style={styles.page}>
      <div style={styles.header}>
        <h1 style={styles.title}>SELECT YOUR ROOM</h1>
        <p style={styles.subtitle}>Tap your room to check in</p>
      </div>

      {error && (
        <div style={styles.error} role="alert">
          ⚠ {error}
        </div>
      )}

      {loadingRooms ? (
        <div style={styles.center}>
          <Spinner />
          <p style={styles.loadingText}>Loading rooms…</p>
        </div>
      ) : !hasRooms ? (
        <div style={styles.center}>
          <p style={styles.emptyText}>
            No rooms available.{'\n'}
            Ask staff to create a floor with rooms via the staff portal.
          </p>
        </div>
      ) : (
        <div style={styles.floorList}>
          {floorKeys.map(floorId => {
            const floorRooms = grouped[floorId];
            const firstName  = floorRooms[0]?.floor_name;
            return (
              <div key={floorId} style={styles.floorSection}>
                <div style={styles.floorLabel}>
                  {floorDisplayName(floorId, firstName)}
                </div>
                <div style={styles.roomGrid}>
                  {floorRooms.map(room => {
                    const isSubmitting = submittingRoom === room.room_id;
                    const isDisabled   = !!submittingRoom;
                    return (
                      <button
                        key={room.room_id}
                        id={`room-${room.room_id}`}
                        onClick={() => handleRoomClick(room.room_id)}
                        disabled={isDisabled}
                        style={{
                          ...styles.roomCard,
                          ...(isDisabled && !isSubmitting ? styles.roomCardDisabled : {}),
                          ...(isSubmitting ? styles.roomCardSubmitting : {}),
                        }}
                        aria-label={`${room.label}, ${floorDisplayName(floorId, firstName)}`}
                      >
                        {isSubmitting ? (
                          <Spinner size={20} color="#fff" />
                        ) : (
                          <>
                            <span style={styles.roomNumber}>{room.label}</span>
                            <span style={styles.roomFloor}>
                              {floorDisplayName(floorId, firstName)}
                            </span>
                          </>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─── Spinner ──────────────────────────────────────────────────────────────────

function Spinner({ size = 28, color = '#22C55E' }: { size?: number; color?: string }) {
  return (
    <>
      <div
        style={{
          width: size,
          height: size,
          border: `3px solid rgba(255,255,255,0.1)`,
          borderTopColor: color,
          borderRadius: '50%',
          animation: 'spin 0.7s linear infinite',
          flexShrink: 0,
        }}
      />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: '100vh',
    background: '#0B0F14',
    color: 'white',
    padding: '32px 16px 48px',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
  },
  header: {
    textAlign: 'center',
    marginBottom: 32,
  },
  title: {
    fontSize: 28,
    fontWeight: 800,
    letterSpacing: '0.08em',
    margin: '0 0 8px',
    color: '#F1F5F9',
  },
  subtitle: {
    fontSize: 14,
    color: '#475569',
    margin: 0,
    fontFamily: 'monospace',
  },
  error: {
    background: 'rgba(239,68,68,0.12)',
    border: '1px solid rgba(239,68,68,0.4)',
    color: '#FCA5A5',
    padding: '12px 20px',
    borderRadius: 10,
    fontSize: 14,
    marginBottom: 20,
    width: '100%',
    maxWidth: 480,
    textAlign: 'center',
  },
  center: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 16,
    paddingTop: 80,
  },
  loadingText: {
    color: '#475569',
    fontFamily: 'monospace',
    fontSize: 13,
    letterSpacing: '0.1em',
    marginTop: 12,
  },
  emptyText: {
    color: '#475569',
    fontFamily: 'monospace',
    fontSize: 14,
    textAlign: 'center',
    whiteSpace: 'pre-line',
    lineHeight: 1.8,
  },
  floorList: {
    width: '100%',
    maxWidth: 480,
    display: 'flex',
    flexDirection: 'column',
    gap: 28,
  },
  floorSection: {
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
  },
  floorLabel: {
    fontSize: 11,
    fontFamily: 'monospace',
    letterSpacing: '0.2em',
    color: '#475569',
    textTransform: 'uppercase',
    paddingLeft: 4,
  },
  roomGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, 1fr)',
    gap: 10,
  },
  roomCard: {
    background: '#121821',
    border: '2px solid #1F2937',
    borderRadius: 12,
    padding: '18px 8px',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    cursor: 'pointer',
    minHeight: 80,
    transition: 'border-color 0.15s, background 0.15s',
  },
  roomCardDisabled: {
    opacity: 0.4,
    cursor: 'not-allowed',
  },
  roomCardSubmitting: {
    background: 'rgba(34,197,94,0.12)',
    border: '2px solid rgba(34,197,94,0.5)',
    cursor: 'wait',
  },
  roomNumber: {
    fontSize: 18,
    fontWeight: 800,
    color: '#F1F5F9',
    letterSpacing: '-0.01em',
    textAlign: 'center',
    wordBreak: 'break-word',
  },
  roomFloor: {
    fontSize: 10,
    fontFamily: 'monospace',
    color: '#475569',
    letterSpacing: '0.1em',
  },
};

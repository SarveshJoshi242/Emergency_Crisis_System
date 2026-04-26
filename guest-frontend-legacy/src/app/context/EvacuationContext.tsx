import React, { createContext, useContext, useState, useCallback, useMemo } from 'react';
import { GuestSession, EmergencyStatusResponse, PathStep } from '../../api/guestClient';

// ─── State shape ─────────────────────────────────────────────────────────────

interface AppState {
  session: GuestSession | null;
  emergencyStatus: EmergencyStatusResponse | null;
  currentPath: PathStep[] | null;
}

interface AppActions {
  setSession: (s: GuestSession | null) => void;
  setEmergencyStatus: (fn: ((prev: EmergencyStatusResponse | null) => EmergencyStatusResponse | null) | EmergencyStatusResponse | null) => void;
  setCurrentPath: (p: PathStep[] | null) => void;
}

type AppContextType = AppState & AppActions;

// ─── Context ──────────────────────────────────────────────────────────────────

const AppContext = createContext<AppContextType | null>(null);

export function useApp(): AppContextType {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppProvider');
  return ctx;
}

// ─── Provider ─────────────────────────────────────────────────────────────────

export const AppProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [state, setState] = useState<AppState>({
    session: null,
    emergencyStatus: null,
    currentPath: null,
  });

  const setSession = useCallback((s: GuestSession | null) => {
    setState(prev => ({ ...prev, session: s }));
    // Hardening: Persist session_id in localStorage for robust survival across tabs/refreshes
    if (s) {
      localStorage.setItem('session_id', s.session_id);
    } else {
      localStorage.removeItem('session_id');
      localStorage.removeItem('offline_path'); // clean up offline path on session end
    }
  }, []);

  const setEmergencyStatus = useCallback(
    (fn: ((prev: EmergencyStatusResponse | null) => EmergencyStatusResponse | null) | EmergencyStatusResponse | null) => {
      if (typeof fn === 'function') {
        setState(prev => ({ ...prev, emergencyStatus: fn(prev.emergencyStatus) }));
      } else {
        setState(prev => ({ ...prev, emergencyStatus: fn }));
      }
    },
    []
  );

  const setCurrentPath = useCallback((p: PathStep[] | null) => {
    setState(prev => ({ ...prev, currentPath: p }));
    // Hardening: Cache path for offline fallback
    if (p) {
      localStorage.setItem('offline_path', JSON.stringify(p));
    }
  }, []);

  const value = useMemo<AppContextType>(() => ({
    ...state,
    setSession,
    setEmergencyStatus,
    setCurrentPath,
  }), [state, setSession, setEmergencyStatus, setCurrentPath]);

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
};

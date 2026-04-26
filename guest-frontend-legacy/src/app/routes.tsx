import { createBrowserRouter, Outlet } from 'react-router';
import { AppProvider } from './context/EvacuationContext';
import { AppLoader } from './pages/AppLoader';
import { GuestEntry } from './pages/GuestEntry';
import { DashboardPage } from './pages/DashboardPage';
import { EvacuationPage } from './pages/EvacuationPage';
import { SafeZonePage } from './pages/SafeZonePage';

function Root() {
  return (
    <AppProvider>
      <div className="min-h-screen" style={{ background: '#0B0F14', color: 'white' }}>
        <Outlet />
      </div>
    </AppProvider>
  );
}

export const router = createBrowserRouter([
  {
    path: '/',
    Component: Root,
    children: [
      { index: true, Component: AppLoader },
      { path: 'check-in', Component: GuestEntry },
      { path: 'dashboard', Component: DashboardPage },
      { path: 'evacuation', Component: EvacuationPage },
      { path: 'safe', Component: SafeZonePage },
    ],
  },
]);

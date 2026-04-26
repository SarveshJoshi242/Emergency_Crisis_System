import { createBrowserRouter } from 'react-router';
import { Landing } from './pages/Landing';
import { GuestAuth } from './pages/GuestAuth';
import { GuestDashboard } from './pages/GuestDashboard';
import { StaffAuth } from './pages/StaffAuth';
import { StaffDashboard } from './pages/StaffDashboard';
import { StaffMainDashboard } from './pages/StaffMainDashboard';

export const router = createBrowserRouter([
  {
    path: '/',
    Component: Landing
  },
  {
    path: '/guest/auth',
    Component: GuestAuth
  },
  {
    path: '/guest/dashboard',
    Component: GuestDashboard
  },
  {
    path: '/staff/auth',
    Component: StaffAuth
  },
  {
    path: '/staff/dashboard',
    Component: StaffDashboard
  },
  {
    path: '/staff/main-dashboard',
    Component: StaffMainDashboard
  }
]);

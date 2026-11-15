import { useEffect } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { refreshSession } from '../api/client.js';
import { useAuthStore } from '../store/auth.js';
import { Spinner } from '../components/ui.jsx';

/** Restores the session from the refresh cookie once, then guards private routes. */
export function AuthGate() {
  const status = useAuthStore((s) => s.status);
  const location = useLocation();

  useEffect(() => {
    if (status === 'unknown') refreshSession();
  }, [status]);

  if (status === 'unknown') {
    return (
      <div className="flex min-h-screen items-center justify-center text-muted">
        <Spinner />
      </div>
    );
  }
  if (status === 'anonymous') return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <Outlet />;
}

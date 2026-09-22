import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "./authContext";

/** Redirects to /login when signed out. Security is enforced on the backend. */
export function ProtectedRoute() {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <p role="status" aria-live="polite" className="py-16 text-center text-sm text-ink-muted">
        Checking your session…
      </p>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }

  return <Outlet />;
}

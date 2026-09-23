import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "./authContext";

/** Redirects to /login when signed out. Security is enforced on the backend. */
export function ProtectedRoute() {
  const { isAuthenticated, isLoading, user } = useAuth();
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

  // An account created with a temporary password can't use anything until it
  // is replaced (the API returns 403 for everything else), so there is only
  // one place to be.
  if (user?.must_change_password && location.pathname !== "/set-password") {
    return <Navigate to="/set-password" replace />;
  }

  return <Outlet />;
}

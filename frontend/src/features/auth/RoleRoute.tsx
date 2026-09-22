import { Navigate, Outlet } from "react-router-dom";

import { useAuth } from "./authContext";
import type { Role } from "./types";

interface RoleRouteProps {
  allow: Role[];
}

/**
 * Hides UI for roles that shouldn't see it. This is NOT security: the
 * backend enforces access on every request (require_permission) regardless
 * of what the frontend shows. Render inside a ProtectedRoute so `user` is
 * never null here.
 */
export function RoleRoute({ allow }: RoleRouteProps) {
  const { user } = useAuth();

  if (!user || !allow.includes(user.role)) {
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
}

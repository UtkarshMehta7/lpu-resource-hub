import { Link, useNavigate } from "react-router-dom";

import { useAuth } from "@/features/auth/authContext";

export function Header() {
  const { isAuthenticated, isLoading, user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    void logout().then(() => navigate("/"));
  };

  return (
    <header className="border-b border-line bg-surface">
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-4">
        <Link to="/" className="flex items-center gap-3 rounded-md">
          <span
            aria-hidden="true"
            className="grid size-9 place-items-center rounded-lg bg-brand-700 text-sm font-bold text-white"
          >
            RH
          </span>
          <span className="leading-tight">
            <span className="block text-sm font-semibold sm:text-base">
              LPU Research Intelligence &amp; Collaboration Hub
            </span>
            <span className="block text-xs text-ink-muted">Prototype</span>
          </span>
        </Link>

        {isLoading ? null : isAuthenticated && user ? (
          <div className="flex items-center gap-3">
            <Link
              to="/researchers"
              className="hidden text-sm font-medium hover:underline sm:inline"
            >
              Researchers
            </Link>
            {user.role !== "student" ? (
              <Link to="/students" className="hidden text-sm font-medium hover:underline sm:inline">
                Students
              </Link>
            ) : null}
            {user.role === "research_coordinator" || user.role === "admin" ? (
              <Link
                to="/coordinator/verification-queue"
                className="hidden text-sm font-medium hover:underline sm:inline"
              >
                Verification
              </Link>
            ) : null}
            {user.role === "admin" ? (
              <Link
                to="/admin/users"
                className="hidden text-sm font-medium hover:underline sm:inline"
              >
                Admin
              </Link>
            ) : null}
            <Link to="/profile" className="hidden text-sm font-medium hover:underline sm:inline">
              Profile
            </Link>
            <Link to="/account" className="hidden text-sm font-medium hover:underline sm:inline">
              {user.full_name}
            </Link>
            <button
              type="button"
              onClick={handleLogout}
              className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm font-medium hover:bg-canvas"
            >
              Log out
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-3 text-sm font-medium">
            <Link to="/login" className="hover:underline">
              Log in
            </Link>
            <Link
              to="/register"
              className="rounded-md bg-brand-700 px-3 py-1.5 text-white hover:bg-brand-800"
            >
              Register
            </Link>
          </div>
        )}
      </div>
    </header>
  );
}

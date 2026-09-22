import { useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";

import { useAuth } from "@/features/auth/authContext";

import { Brand } from "./Brand";
import type { Role } from "@/features/auth/types";

interface NavItem {
  to: string;
  label: string;
  /** Omitted means "every signed-in role". */
  roles?: Role[];
}

/** One list drives both the desktop bar and the mobile menu, so a role can
 * never see a link on one and not the other. */
const NAV: NavItem[] = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/recommendations", label: "For you" },
  { to: "/researchers", label: "Researchers" },
  { to: "/projects", label: "Projects" },
  { to: "/publications", label: "Publications" },
  { to: "/opportunities", label: "Opportunities" },
  { to: "/students", label: "Students", roles: ["faculty", "research_coordinator", "admin"] },
  {
    to: "/collaborations",
    label: "Requests",
    roles: ["student", "faculty", "research_coordinator"],
  },
  { to: "/facilities", label: "Facilities" },
  { to: "/me/bookings", label: "My bookings" },
  { to: "/me/saved", label: "Saved" },
  {
    to: "/coordinator/verification-queue",
    label: "Verification",
    roles: ["research_coordinator", "admin"],
  },
  { to: "/coordinator/review-queue", label: "Reviews", roles: ["research_coordinator", "admin"] },
  {
    to: "/coordinator/booking-queue",
    label: "Bookings",
    roles: ["research_coordinator", "admin"],
  },
  { to: "/admin/reports", label: "Reports", roles: ["research_coordinator", "admin"] },
  { to: "/admin/users", label: "Admin", roles: ["admin"] },
  { to: "/profile", label: "Profile" },
];

const LINK = "text-sm font-medium hover:underline aria-[current=page]:text-brand-700";

export function Header() {
  const { isAuthenticated, isLoading, user, logout } = useAuth();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);

  const handleLogout = () => {
    setMenuOpen(false);
    void logout().then(() => navigate("/"));
  };

  const items = NAV.filter((item) => !item.roles || (user && item.roles.includes(user.role)));

  return (
    <header className="border-b border-line bg-surface">
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-4">
        <Brand />

        {isLoading ? null : isAuthenticated && user ? (
          <>
            <nav aria-label="Main" className="hidden items-center gap-3 lg:flex">
              {items.slice(0, 6).map((item) => (
                <NavLink key={item.to} to={item.to} className={LINK}>
                  {item.label}
                </NavLink>
              ))}
              <button
                type="button"
                aria-expanded={menuOpen}
                aria-controls="more-menu"
                onClick={() => setMenuOpen((open) => !open)}
                className="rounded-md border border-line px-3 py-1.5 text-sm font-medium"
              >
                More
              </button>
            </nav>
            <button
              type="button"
              aria-expanded={menuOpen}
              aria-controls="more-menu"
              onClick={() => setMenuOpen((open) => !open)}
              className="rounded-md border border-line px-3 py-1.5 text-sm font-medium lg:hidden"
            >
              Menu
            </button>
          </>
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

      {isAuthenticated && user && menuOpen ? (
        <nav
          id="more-menu"
          aria-label="All pages"
          className="border-t border-line bg-surface px-4 py-3"
        >
          <ul className="mx-auto grid max-w-5xl gap-2 sm:grid-cols-3">
            {items.map((item) => (
              <li key={item.to}>
                <NavLink to={item.to} onClick={() => setMenuOpen(false)} className={LINK}>
                  {item.label}
                </NavLink>
              </li>
            ))}
            <li>
              <Link to="/account" className={LINK} onClick={() => setMenuOpen(false)}>
                {user.full_name}
              </Link>
            </li>
            <li>
              <button type="button" onClick={handleLogout} className={LINK}>
                Log out
              </button>
            </li>
          </ul>
        </nav>
      ) : null}
    </header>
  );
}

import { useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";

import { useAuth } from "@/features/auth/authContext";

import { MessagesLink } from "@/features/messages/MessagesLink";
import { NotificationBell } from "@/features/notifications/NotificationBell";

import { Brand } from "./Brand";
import type { Role } from "@/features/auth/types";
import { Uid } from "@/components/ui/Uid";

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
  { to: "/search", label: "Search" },
  { to: "/recommendations", label: "For you" },
  { to: "/researchers", label: "Researchers" },
  { to: "/projects", label: "Projects" },
  { to: "/publications", label: "Publications" },
  { to: "/opportunities", label: "Opportunities" },
  { to: "/students", label: "Students", roles: ["faculty", "research_coordinator", "admin"] },
  // One route, but the label names who you actually provision, so nobody has
  // to guess. Mirrors CREATABLE_ROLE on the backend.
  // Admins manage accounts from the console at /admin/users; for a
  // coordinator or faculty member, /people is the whole of that authority.
  { to: "/people", label: "My people", roles: ["research_coordinator", "faculty"] },
  { to: "/people/new", label: "Add coordinator", roles: ["admin"] },
  { to: "/people/new", label: "Add faculty", roles: ["research_coordinator"] },
  { to: "/people/new", label: "Add student", roles: ["faculty"] },
  // Sits next to Requests on purpose: a request accepted becomes a thread.
  { to: "/messages", label: "Messages" },
  {
    to: "/collaborations",
    label: "Requests",
    roles: ["student", "faculty", "research_coordinator"],
  },
  { to: "/facilities", label: "Facilities" },
  { to: "/funding", label: "Funding" },
  { to: "/me/bookings", label: "My bookings" },
  { to: "/me/saved", label: "Saved" },
  { to: "/me/notifications", label: "Notifications" },
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
  { to: "/analytics", label: "Analytics", roles: ["research_coordinator", "admin"] },
  { to: "/admin/reports", label: "Reports", roles: ["research_coordinator", "admin"] },
  { to: "/admin", label: "Administration", roles: ["admin"] },
  { to: "/admin/coordinators", label: "Coordinators", roles: ["admin"] },
  { to: "/admin/administrators", label: "Administrators", roles: ["admin"] },
  { to: "/admin/users", label: "Accounts", roles: ["admin"] },
  { to: "/admin/audit-logs", label: "Audit log", roles: ["admin"] },
  { to: "/admin/settings", label: "Settings", roles: ["admin"] },
  { to: "/profile", label: "Profile" },
];

const LINK =
  "whitespace-nowrap text-sm font-medium hover:underline aria-[current=page]:text-brand-700";

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
                <NavLink key={item.label} to={item.to} className={LINK}>
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
            <MessagesLink />
            <NotificationBell />
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
          <Link
            to="/login"
            className="rounded-md bg-brand-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-800"
          >
            Log in
          </Link>
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
              <li key={item.label}>
                <NavLink to={item.to} onClick={() => setMenuOpen(false)} className={LINK}>
                  {item.label}
                </NavLink>
              </li>
            ))}
            <li>
              <Link to="/account" className={LINK} onClick={() => setMenuOpen(false)}>
                {user.full_name} <Uid value={user.registration_number} />
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

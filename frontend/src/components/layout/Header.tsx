import { useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";

import { useAuth } from "@/features/auth/authContext";

import { MessagesLink } from "@/features/messages/MessagesLink";
import { NotificationBell } from "@/features/notifications/NotificationBell";

import { MenuIcon, SearchIcon } from "@/components/ui/icons";

import { Brand } from "./Brand";
import { CommandPalette } from "./CommandPalette";
import { NAV_GROUPS, navigationFor } from "./navigation";
import { useCommandPalette } from "./useCommandPalette";
import { Uid } from "@/components/ui/Uid";

const LINK =
  "whitespace-nowrap rounded-md px-2.5 py-1.5 text-sm font-medium transition-colors " +
  "hover:bg-canvas aria-[current=page]:bg-brand-50 aria-[current=page]:text-brand-800";

export function Header() {
  const { isAuthenticated, isLoading, user, logout } = useAuth();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const palette = useCommandPalette();

  const handleLogout = () => {
    setMenuOpen(false);
    void logout().then(() => navigate("/"));
  };

  const items = navigationFor(user?.role);

  return (
    <header className="border-b border-line bg-surface">
      <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-3">
        <Brand />

        {isLoading ? null : isAuthenticated && user ? (
          <>
            <nav aria-label="Main" className="ml-auto hidden items-center gap-1 xl:flex">
              {items.slice(0, 6).map((item) => (
                <NavLink key={item.label} to={item.to} className={LINK}>
                  {item.label}
                </NavLink>
              ))}
            </nav>

            {/* Actions sit together on the right, in one row that cannot wrap. */}
            <div className="ml-auto flex shrink-0 items-center gap-1.5 xl:ml-0">
              <button
                type="button"
                onClick={() => palette.setOpen(true)}
                className="inline-flex shrink-0 items-center gap-2 whitespace-nowrap rounded-md border border-line px-2.5 py-1.5 text-sm text-ink-muted transition-colors hover:bg-canvas hover:text-ink"
                aria-keyshortcuts="Meta+K Control+K"
                aria-label="Go to a page"
                title="Go to a page (⌘K)"
              >
                <SearchIcon />
                <span className="hidden sm:inline">Go to</span>
                <kbd className="hidden rounded border border-line bg-canvas px-1 py-px font-sans text-[10px] font-medium sm:inline">
                  ⌘K
                </kbd>
              </button>
              <MessagesLink />
              <NotificationBell />
              <button
                type="button"
                aria-expanded={menuOpen}
                aria-controls="more-menu"
                onClick={() => setMenuOpen((open) => !open)}
                className="inline-flex shrink-0 items-center gap-2 whitespace-nowrap rounded-md border border-line px-2.5 py-1.5 text-sm font-medium transition-colors hover:bg-canvas"
              >
                <MenuIcon />
                <span className="hidden sm:inline">All pages</span>
              </button>
            </div>
          </>
        ) : (
          <Link
            to="/login"
            className="ml-auto shrink-0 whitespace-nowrap rounded-md bg-brand-700 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-brand-800"
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
          <div className="mx-auto grid max-w-7xl gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {NAV_GROUPS.map((group) => {
              const inGroup = items.filter((item) => item.group === group);
              if (inGroup.length === 0) return null;
              return (
                <div key={group}>
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                    {group}
                  </p>
                  <ul className="space-y-1.5">
                    {inGroup.map((item) => (
                      <li key={`${item.to}-${item.label}`}>
                        <NavLink to={item.to} onClick={() => setMenuOpen(false)} className={LINK}>
                          {item.label}
                        </NavLink>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                You
              </p>
              <ul className="space-y-1.5">
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
            </div>
          </div>
        </nav>
      ) : null}

      {isAuthenticated ? (
        // Mounted only while open, so every opening starts with an empty
        // query and a fresh highlight without an effect to reset them.
        <CommandPalette open={palette.open} onClose={() => palette.setOpen(false)} />
      ) : null}
    </header>
  );
}

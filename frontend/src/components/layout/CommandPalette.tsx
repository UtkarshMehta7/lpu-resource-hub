import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "@/features/auth/authContext";

import { navigationFor, searchNavigation, type NavItem } from "./navigation";

/**
 * Cmd/Ctrl+K: type two letters, press Enter, you are there.
 *
 * The platform has 28 destinations and a top bar with room for six. Everything
 * else sat behind a "More" menu, so reaching the verification queue was a
 * click to open, a scan of twenty-two labels, and a click to go. For somebody
 * working through queues all day that is the interface's main cost.
 *
 * Keyboard-first on purpose, and it only ever offers pages the signed-in role
 * can actually reach -- the same list the navigation uses, so the palette can
 * never advertise a page that answers 403.
 */
export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);

  const results = useMemo(
    () => searchNavigation(navigationFor(user?.role), query).slice(0, 8),
    [user?.role, query],
  );

  // Clamped during render rather than reset in an effect: typing shortens the
  // list, and an out-of-range highlight would survive a frame otherwise.
  const highlighted = Math.min(active, Math.max(results.length - 1, 0));

  if (!open) return null;

  const go = (item: NavItem | undefined) => {
    if (!item) return;
    onClose();
    void navigate(item.to);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-ink/30 px-4 pt-[15vh]"
      // A click on the backdrop closes it; a click inside must not.
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Go to"
        className="w-full max-w-lg overflow-hidden rounded-card border border-line bg-surface shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="border-b border-line p-2">
          <label htmlFor="command-query" className="sr-only">
            Go to page
          </label>
          <input
            id="command-query"
            autoFocus
            value={query}
            placeholder="Go to…  (try “verify”, “accounts”, “chat”)"
            autoComplete="off"
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setActive(Math.min(highlighted + 1, results.length - 1));
              } else if (event.key === "ArrowUp") {
                event.preventDefault();
                setActive(Math.max(highlighted - 1, 0));
              } else if (event.key === "Enter") {
                event.preventDefault();
                go(results[highlighted]);
              } else if (event.key === "Escape") {
                onClose();
              }
            }}
            className="w-full border-0 bg-transparent text-sm focus:outline-none"
          />
        </div>

        {results.length === 0 ? (
          <p className="p-4 text-sm text-ink-muted">Nothing matches “{query}”.</p>
        ) : (
          <ul role="listbox" aria-label="Results" className="max-h-80 overflow-y-auto p-1">
            {results.map((item, index) => (
              <li key={`${item.to}-${item.label}`}>
                <button
                  type="button"
                  role="option"
                  aria-selected={index === highlighted}
                  onMouseEnter={() => setActive(index)}
                  onClick={() => go(item)}
                  className={`flex w-full items-center justify-between gap-3 rounded-md px-3 py-2 text-left text-sm ${
                    index === highlighted ? "bg-brand-50 text-brand-800" : "hover:bg-canvas"
                  }`}
                >
                  <span className="font-medium">{item.label}</span>
                  <span className="text-xs text-ink-muted">{item.group}</span>
                </button>
              </li>
            ))}
          </ul>
        )}

        <p className="border-t border-line bg-canvas px-3 py-2 text-xs text-ink-muted">
          ↑↓ to choose · Enter to go · Esc to close
        </p>
      </div>
    </div>
  );
}

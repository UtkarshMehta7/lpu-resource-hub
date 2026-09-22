import { Link } from "react-router-dom";

export function Header() {
  return (
    <header className="border-b border-line bg-surface">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4">
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
      </div>
    </header>
  );
}

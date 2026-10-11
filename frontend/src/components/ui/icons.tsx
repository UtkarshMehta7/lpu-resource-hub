/**
 * The handful of icons the shell needs, as inline SVG.
 *
 * Emoji were standing in for these (🔍 💬 🔔). They render as a different
 * glyph on every platform, sit on their own baseline, carry their own colour
 * and ignore `currentColor` -- three different sizes in one header. These
 * inherit size and colour like text, which is the whole point.
 */
const STROKE = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.75,
  strokeLinecap: "round",
  strokeLinejoin: "round",
} as const;

function Svg({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
      className={className ?? "size-4"}
      {...STROKE}
    >
      {children}
    </svg>
  );
}

export function SearchIcon({ className }: { className?: string }) {
  return (
    <Svg className={className}>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.2-3.2" />
    </Svg>
  );
}

export function MessageIcon({ className }: { className?: string }) {
  return (
    <Svg className={className}>
      <path d="M21 12a8 8 0 0 1-8 8H8l-4 3v-4.6A8 8 0 0 1 11 4h2a8 8 0 0 1 8 8Z" />
    </Svg>
  );
}

export function BellIcon({ className }: { className?: string }) {
  return (
    <Svg className={className}>
      <path d="M18 9a6 6 0 1 0-12 0c0 5-2 7-2 7h16s-2-2-2-7" />
      <path d="M10.5 20a2 2 0 0 0 3 0" />
    </Svg>
  );
}

export function MenuIcon({ className }: { className?: string }) {
  return (
    <Svg className={className}>
      <path d="M4 7h16M4 12h16M4 17h16" />
    </Svg>
  );
}

export function StarIcon({ className, filled = false }: { className?: string; filled?: boolean }) {
  // The only icon that carries state, so it takes a fill rather than a second
  // glyph: ★ and ☆ are different characters at different widths, and the row
  // shifted as you saved.
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
      className={className ?? "size-4"}
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="m12 3.6 2.6 5.3 5.8.8-4.2 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8L3.6 9.7l5.8-.8Z" />
    </svg>
  );
}

export function CloseIcon({ className }: { className?: string }) {
  return (
    <Svg className={className}>
      <path d="M6 6l12 12M18 6 6 18" />
    </Svg>
  );
}

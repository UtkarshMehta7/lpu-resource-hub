import type { ReactNode } from "react";

/**
 * A workflow state, coloured by what it means rather than by which page it
 * is on.
 *
 * Statuses were plain bordered spans everywhere, so "Pending", "Accepted" and
 * "Declined" looked identical and a list of them had to be read word by word.
 * Colour does the first pass of that reading; the word still does the rest,
 * because colour alone is not an accessible signal.
 */
export type PillTone = "neutral" | "positive" | "warning" | "negative" | "info";

const TONES: Record<PillTone, string> = {
  neutral: "border-line bg-canvas text-ink-muted",
  positive: "border-green-200 bg-green-50 text-green-800",
  warning: "border-amber-200 bg-amber-50 text-amber-800",
  negative: "border-red-200 bg-red-50 text-red-800",
  info: "border-brand-200 bg-brand-50 text-brand-800",
};

export function StatusPill({
  tone = "neutral",
  children,
}: {
  tone?: PillTone;
  children: ReactNode;
}) {
  return (
    <span
      className={`inline-flex shrink-0 items-center whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium ${TONES[tone]}`}
    >
      {children}
    </span>
  );
}

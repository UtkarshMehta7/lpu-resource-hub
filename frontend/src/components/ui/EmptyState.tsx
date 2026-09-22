import type { ReactNode } from "react";
import { Link } from "react-router-dom";

/** An empty list should always say what to do next, not just "no results". */
export function EmptyState({
  title,
  description,
  actionLabel,
  actionTo,
  children,
}: {
  title: string;
  description?: string;
  actionLabel?: string;
  actionTo?: string;
  children?: ReactNode;
}) {
  return (
    <div className="rounded-card border border-line bg-surface px-4 py-8 text-center">
      <p className="text-sm font-medium">{title}</p>
      {description ? <p className="mt-1 text-sm text-ink-muted">{description}</p> : null}
      {actionLabel && actionTo ? (
        <Link
          to={actionTo}
          className="mt-4 inline-block rounded-md bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-800"
        >
          {actionLabel}
        </Link>
      ) : null}
      {children}
    </div>
  );
}

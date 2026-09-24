import type { ReactNode } from "react";

/**
 * The top of every page: what this is, what it is for, what you can do here.
 *
 * Fifty pages each wrote their own heading block, so the gap under the title,
 * the width of the description and the position of the action varied page to
 * page. Somebody moving between pages all day feels that as the interface
 * shifting under them.
 */
export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  /** One sentence. What this page is for, or what the numbers mean. */
  description?: ReactNode;
  /** Primary action(s) for the page, right-aligned on wide screens. */
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description ? (
          <p className="mt-1 max-w-2xl text-sm text-ink-muted">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

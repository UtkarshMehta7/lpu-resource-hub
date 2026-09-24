import { Link } from "react-router-dom";

/**
 * Lovely Professional University branding.
 *
 * The full university name is shown wherever there's room; the "LPU"
 * shortform stands in for it in tight spaces. The "Prototype" label stays
 * attached to the mark: this is not an official university system, and the
 * crest appearing here does not make it one.
 */
export const UNIVERSITY_NAME = "Lovely Professional University";
export const UNIVERSITY_SHORT = "LPU";
export const PRODUCT_NAME = "Research Intelligence & Collaboration Hub";
export const PRODUCT_SHORT = "LPU Research Hub";

/** The university crest. Served from public/, so no bundler import. */
export function Crest({ className = "size-9" }: { className?: string }) {
  return (
    <img
      src="/lpu-logo.png"
      alt=""
      aria-hidden="true"
      width={600}
      height={600}
      className={`shrink-0 object-contain ${className}`}
    />
  );
}

/**
 * Kept for places that want a solid block rather than the crest — the footer
 * at small sizes, where 600px of detail turns to mud.
 */
export function Monogram({ className = "size-9 text-sm" }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={`grid shrink-0 place-items-center rounded-lg bg-brand-700 font-bold tracking-tight text-white ${className}`}
    >
      {UNIVERSITY_SHORT}
    </span>
  );
}

/**
 * The header mark: crest, university, product, prototype tag.
 *
 * Every line is `whitespace-nowrap` and the whole thing is `shrink-0`. In a
 * flex row beside the navigation it was being squeezed until it wrapped
 * mid-phrase -- four lines of brand and a header three times taller than it
 * needed to be. A mark that reflows as the window narrows reads as broken,
 * so this one shortens instead: the full product name appears only where
 * there is room for it, and the short form stands in everywhere else.
 */
export function Brand() {
  return (
    <Link
      to="/"
      className="flex shrink-0 items-center gap-2.5 rounded-md"
      aria-label={`${PRODUCT_SHORT} home`}
      title={`${UNIVERSITY_NAME} — ${PRODUCT_NAME}`}
    >
      <Crest className="size-8" />
      <span className="leading-tight">
        <span className="block whitespace-nowrap text-[11px] font-medium text-brand-700">
          {UNIVERSITY_NAME}
        </span>
        <span className="flex items-center gap-1.5 whitespace-nowrap text-sm font-semibold">
          <span className="xl:hidden">{PRODUCT_SHORT}</span>
          <span className="hidden xl:inline">{PRODUCT_NAME}</span>
          <span className="rounded border border-line px-1 py-px text-[9px] font-semibold uppercase tracking-wide text-ink-muted">
            Prototype
          </span>
        </span>
      </span>
    </Link>
  );
}

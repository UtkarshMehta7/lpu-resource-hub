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

/** The header mark: crest, university name, product name, prototype tag. */
export function Brand() {
  return (
    <Link
      to="/"
      className="flex items-center gap-3 rounded-md"
      aria-label={`${PRODUCT_SHORT} home`}
    >
      <Crest />
      <span className="leading-tight">
        <span className="block text-xs font-medium text-brand-700 sm:text-sm">
          {UNIVERSITY_NAME}
        </span>
        <span className="block text-sm font-semibold sm:text-base">
          <span className="sm:hidden">{PRODUCT_SHORT}</span>
          <span className="hidden sm:inline">{PRODUCT_NAME}</span>
          <span className="ml-2 rounded-md border border-line px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-ink-muted">
            Prototype
          </span>
        </span>
      </span>
    </Link>
  );
}

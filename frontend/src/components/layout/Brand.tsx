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

/** Who built it. Shown in the footer of every page, beside the disclaimer. */
export const AUTHOR_NAME = "Utkarsh Mehta";
export const AUTHOR_LINKEDIN = "https://www.linkedin.com/in/utkarshmehta0709";

/**
 * The university crest. Served from public/, so no bundler import.
 *
 * The file is cropped to the mark itself. It used to carry a 30px white
 * margin on all four sides of a 600px frame, so every placement paid for
 * padding it had not asked for -- on the landing page that margin stacked on
 * top of the ring and the element's own padding, and the crest sat in a white
 * band half its own width. Padding belongs to the placement, never to the
 * asset.
 */
export function Crest({ className = "size-9" }: { className?: string }) {
  return (
    <img
      src="/lpu-logo.png"
      alt=""
      aria-hidden="true"
      width={540}
      height={540}
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
 *
 * Below `sm` there is room for neither name: the mark and four action
 * icons already need more than a 360px screen has, and nothing else in the
 * header can give way. So the crest stands alone there -- with the
 * PROTOTYPE label, which is the one part that must not be dropped, since
 * it is what says this is not an official university system. The full
 * university name is in the footer of every page, and both names stay in
 * the link's `title` and `aria-label` at every width. Measured: the header
 * overflowed by 80px at 360, 50 at 390 and 26 at 414 on every page in the
 * application before this, and clears all three now.
 *
 * "Where there is room" for the LONG product name is `2xl`, not `xl`. At `xl` the navigation bar
 * appears at the same moment the long name does, and the two together
 * pushed the header 32px past the viewport at 1280 and 31px at 1366 -- the
 * two commonest laptop widths, on every page in the application. Measured
 * before and after; both are clear at `2xl`, and the full university name
 * above is shown at every width, untouched.
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
        <span className="hidden whitespace-nowrap text-[11px] font-medium text-brand-700 sm:block">
          {UNIVERSITY_NAME}
        </span>
        <span className="flex items-center gap-1.5 whitespace-nowrap text-sm font-semibold">
          <span className="hidden sm:inline 2xl:hidden">{PRODUCT_SHORT}</span>
          <span className="hidden 2xl:inline">{PRODUCT_NAME}</span>
          <span className="rounded border border-line px-1 py-px text-[9px] font-semibold uppercase tracking-wide text-ink-muted">
            Prototype
          </span>
        </span>
      </span>
    </Link>
  );
}

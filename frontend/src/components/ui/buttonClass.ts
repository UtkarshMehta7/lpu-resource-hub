/**
 * The button recipe, in one place.
 *
 * Separate from Button.tsx so a file that only needs the class string -- a
 * react-hook-form submit, a third-party component -- can have it without
 * importing a component, and so Button.tsx exports components only.
 */
export type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";
export type ButtonSize = "sm" | "md";

const BASE =
  "inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors " +
  "disabled:cursor-not-allowed disabled:opacity-50";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-brand-700 text-white hover:bg-brand-800",
  secondary: "border border-line bg-surface text-ink hover:bg-canvas",
  // Destructive actions read as destructive before they are pressed, not only
  // in the confirmation that follows.
  danger: "border border-red-300 bg-surface text-red-700 hover:bg-red-50",
  ghost: "text-ink-muted hover:bg-canvas hover:text-ink",
};

const SIZES: Record<ButtonSize, string> = {
  sm: "px-2.5 py-1.5 text-xs",
  md: "px-3 py-2 text-sm",
};

export function buttonClass(
  variant: ButtonVariant = "primary",
  size: ButtonSize = "md",
  extra = "",
): string {
  return `${BASE} ${VARIANTS[variant]} ${SIZES[size]} ${extra}`.trim();
}

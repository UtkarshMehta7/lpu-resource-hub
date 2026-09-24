import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link } from "react-router-dom";

import { buttonClass, type ButtonSize, type ButtonVariant } from "./buttonClass";

/**
 * The one button.
 *
 * Forty-three places had hand-written `rounded-md bg-brand-700 px-3 py-2 …`
 * strings, which drifted: three paddings, two radii, and disabled styling on
 * some but not others. A button people press fifty times a day should look
 * and behave identically every time, and a new page should not have to
 * remember the recipe.
 */
interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  children: ReactNode;
}

export function Button({
  variant = "primary",
  size = "md",
  className = "",
  type = "button",
  children,
  ...rest
}: ButtonProps) {
  return (
    <button type={type} className={buttonClass(variant, size, className)} {...rest}>
      {children}
    </button>
  );
}

/** A link that has to look like a button: same shape, correct semantics. */
export function ButtonLink({
  to,
  variant = "primary",
  size = "md",
  className = "",
  children,
}: {
  to: string;
  variant?: ButtonVariant;
  size?: ButtonSize;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Link to={to} className={buttonClass(variant, size, className)}>
      {children}
    </Link>
  );
}

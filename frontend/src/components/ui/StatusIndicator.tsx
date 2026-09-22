export type StatusTone = "neutral" | "success" | "warning" | "danger";

const DOT_CLASSES: Record<StatusTone, string> = {
  neutral: "bg-slate-400 animate-pulse",
  success: "bg-emerald-500",
  warning: "bg-amber-500",
  danger: "bg-red-500",
};

const TEXT_CLASSES: Record<StatusTone, string> = {
  neutral: "text-ink-muted",
  success: "text-emerald-700",
  warning: "text-amber-700",
  danger: "text-red-700",
};

interface StatusIndicatorProps {
  tone: StatusTone;
  label: string;
}

/** Coloured dot plus text label. Colour is never the only signal. */
export function StatusIndicator({ tone, label }: StatusIndicatorProps) {
  return (
    <span className={`inline-flex items-center gap-2 text-sm font-medium ${TEXT_CLASSES[tone]}`}>
      <span aria-hidden="true" className={`size-2.5 rounded-full ${DOT_CLASSES[tone]}`} />
      {label}
    </span>
  );
}

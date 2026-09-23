/**
 * A person's LPU registration number, shown beside their name.
 *
 * Names repeat across a university of this size; the registration number is
 * the UID people actually use to tell two of them apart, so it belongs
 * wherever a student, researcher, coordinator or administrator is named.
 * Monospaced and muted so it reads as an identifier, not as part of the name.
 */
export function Uid({ value, className = "" }: { value: string; className?: string }) {
  if (!value) return null;
  return (
    <span className={`font-mono text-xs font-normal text-ink-muted ${className}`.trimEnd()}>
      {value}
    </span>
  );
}

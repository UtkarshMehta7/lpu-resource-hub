import { useQuery } from "@tanstack/react-query";

import { SkeletonList } from "@/components/ui/Skeleton";
import { fetchPlatformSettings } from "@/features/analytics/api";

/** Read-only view of how this deployment is configured. No secrets. */
export function PlatformSettingsPage() {
  const { data, isPending, isError } = useQuery({
    queryKey: ["platform-settings"],
    queryFn: fetchPlatformSettings,
  });

  if (isPending) return <SkeletonList rows={3} />;
  if (isError) {
    return (
      <p role="alert" className="text-sm text-red-700">
        Could not load platform settings.
      </p>
    );
  }

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-semibold tracking-tight">Platform settings</h1>
      <p className="mt-1 text-sm text-ink-muted">
        What this deployment is configured to do. These come from environment variables, so changing
        them is a deploy rather than a click — and no secrets are shown here.
      </p>

      <p className="mt-4 inline-block rounded-md border border-line bg-surface px-3 py-1.5 text-sm">
        Environment: <span className="font-medium">{data.environment}</span>
      </p>

      <dl className="mt-6 divide-y divide-line rounded-card border border-line bg-surface">
        {Object.entries(data.settings).map(([key, value]) => (
          <div key={key} className="flex flex-wrap items-baseline justify-between gap-2 px-4 py-3">
            <dt className="text-sm capitalize">{key.replace(/_/g, " ")}</dt>
            <dd className="font-mono text-xs text-ink-muted">{format(value)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function format(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "on" : "off";
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => `${key} ${JSON.stringify(item)}`)
      .join(" · ");
  }
  if (typeof value === "number" || typeof value === "string") return String(value);
  return JSON.stringify(value);
}

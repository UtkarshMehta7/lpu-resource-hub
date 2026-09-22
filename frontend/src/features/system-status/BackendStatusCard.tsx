import { StatusIndicator, type StatusTone } from "@/components/ui/StatusIndicator";
import { config } from "@/lib/config";

import { type BackendHealth, useBackendHealth } from "./useBackendHealth";

interface StatusView {
  tone: StatusTone;
  label: string;
  description: string;
}

function describe(health: BackendHealth): StatusView {
  switch (health.state) {
    case "loading":
      return { tone: "neutral", label: "Checking…", description: "Contacting the backend API." };
    case "connected":
      return {
        tone: "success",
        label: "Connected",
        description: "The API is running and PostgreSQL is reachable.",
      };
    case "degraded":
      return {
        tone: "warning",
        label: "Degraded",
        description:
          "The API is running but cannot reach PostgreSQL. Check that the database is started and DATABASE_URL is correct.",
      };
    case "unreachable":
      return {
        tone: "danger",
        label: "Unreachable",
        description: `${health.error.message} Is the backend running on ${config.apiBaseUrl}?`,
      };
  }
}

export function BackendStatusCard() {
  const { health, retry } = useBackendHealth();
  const view = describe(health);
  const endpoint = `${config.apiBaseUrl}/health/ready`;

  return (
    <section
      aria-labelledby="backend-status-heading"
      className="rounded-card border border-line bg-surface p-6 shadow-sm"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 id="backend-status-heading" className="text-base font-semibold">
            Backend connection
          </h2>
          <p className="mt-1 break-all font-mono text-xs text-ink-muted">GET {endpoint}</p>
        </div>
        <div role="status" aria-live="polite">
          <StatusIndicator tone={view.tone} label={view.label} />
        </div>
      </div>

      <p className="mt-4 text-sm text-ink-muted">{view.description}</p>

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-ink-muted">
          {health.state === "loading"
            ? " "
            : `Last checked ${health.checkedAt.toLocaleTimeString()}`}
        </p>
        <button
          type="button"
          onClick={retry}
          disabled={health.state === "loading"}
          className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm font-medium hover:bg-canvas disabled:cursor-not-allowed disabled:opacity-50"
        >
          Check again
        </button>
      </div>
    </section>
  );
}

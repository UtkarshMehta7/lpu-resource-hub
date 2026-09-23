import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonList } from "@/components/ui/Skeleton";

import { applicationStages, fetchNetwork, fetchOverview, statusCounts } from "./api";
import { NetworkGraph } from "./NetworkGraph";

const BRAND = "#1a5b65";
const ACCENT = "#8a6d1f";
const MUTED = "#6b8a90";

export function AnalyticsPage() {
  const { data, isPending, isError } = useQuery({
    queryKey: ["analytics-overview"],
    queryFn: fetchOverview,
  });
  const { data: network } = useQuery({ queryKey: ["analytics-network"], queryFn: fetchNetwork });

  if (isPending) return <SkeletonList rows={4} />;
  if (isError) {
    return (
      <p role="alert" className="text-sm text-red-700">
        Could not load analytics.
      </p>
    );
  }

  const projects = statusCounts(data.projects_by_status);
  const stages = applicationStages(data.opportunity_funnel);
  const backlog = data.verification_backlog;

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Analytics</h1>
      <p className="mt-1 text-sm text-ink-muted">
        {data.scope === "platform"
          ? "Across the whole platform."
          : "For your department only — the numbers stop at your scope."}{" "}
        Aggregates only; no personal data.
      </p>

      <section className="mt-6">
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Awaiting verification" value={backlog.pending} />
          <Stat
            label="Oldest waiting"
            value={
              backlog.oldest_waiting_since
                ? new Date(backlog.oldest_waiting_since).toLocaleDateString()
                : "—"
            }
          />
          <Stat label="Accepted collaborations" value={data.accepted_collaborations} />
          <Stat label="Open reports" value={data.open_reports} />
        </dl>
      </section>

      <Panel title="Activity over the last six months">
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={data.trends} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e3e7ea" />
            <XAxis dataKey="month" tick={{ fontSize: 11 }} />
            <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
            <Tooltip />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line type="monotone" dataKey="projects" stroke={BRAND} strokeWidth={2} />
            <Line type="monotone" dataKey="applications" stroke={ACCENT} strokeWidth={2} />
            <Line type="monotone" dataKey="bookings" stroke={MUTED} strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </Panel>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Projects by status">
          {projects.length === 0 ? (
            <EmptyState title="No projects yet" />
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={projects} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e3e7ea" />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="count" fill={BRAND} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Panel>

        <Panel title="Application funnel">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={stages} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e3e7ea" />
              <XAxis dataKey="label" tick={{ fontSize: 10 }} interval={0} angle={-12} dy={8} />
              <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {stages.map((stage) => (
                  <Cell
                    key={stage.label}
                    fill={
                      stage.label === "Accepted"
                        ? BRAND
                        : stage.label === "Rejected"
                          ? "#a24a4a"
                          : MUTED
                    }
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="Research areas">
          {data.projects_by_area.length === 0 ? (
            <EmptyState title="No tagged projects yet" />
          ) : (
            <ul className="space-y-2">
              {data.projects_by_area.map((area) => (
                <BarRow
                  key={area.label}
                  label={area.label}
                  value={area.count}
                  max={data.projects_by_area[0]?.count ?? 1}
                />
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Most-used equipment">
          {data.equipment_utilisation.length === 0 ? (
            <EmptyState title="No approved bookings yet" />
          ) : (
            <ul className="space-y-2">
              {data.equipment_utilisation.map((item) => (
                <BarRow
                  key={item.label}
                  label={`${item.label} · ${item.bookings} booking${item.bookings === 1 ? "" : "s"}`}
                  value={item.hours}
                  max={data.equipment_utilisation[0]?.hours ?? 1}
                  suffix="h"
                />
              ))}
            </ul>
          )}
        </Panel>
      </div>

      {data.funding_interest.length > 0 ? (
        <Panel title="Most-saved funding calls">
          <ul className="space-y-2">
            {data.funding_interest.map((call) => (
              <BarRow
                key={call.label}
                label={call.label}
                value={call.count}
                max={data.funding_interest[0]?.count ?? 1}
              />
            ))}
          </ul>
        </Panel>
      ) : null}

      <Panel title="Collaboration network">
        {network ? <NetworkGraph graph={network} /> : <SkeletonList rows={1} />}
      </Panel>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-8">
      <h2 className="text-base font-semibold">{title}</h2>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-card border border-line bg-surface p-4">
      <dt className="text-xs text-ink-muted">{label}</dt>
      <dd className="mt-1 text-xl font-semibold">{value}</dd>
    </div>
  );
}

function BarRow({
  label,
  value,
  max,
  suffix = "",
}: {
  label: string;
  value: number;
  max: number;
  suffix?: string;
}) {
  const width = max > 0 ? Math.max(4, Math.round((value / max) * 100)) : 0;
  return (
    <li>
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="truncate">{label}</span>
        <span className="shrink-0 text-ink-muted">
          {value}
          {suffix}
        </span>
      </div>
      <div className="mt-1 h-2 rounded-full bg-line/60">
        <div className="h-2 rounded-full bg-brand-700" style={{ width: `${width}%` }} />
      </div>
    </li>
  );
}

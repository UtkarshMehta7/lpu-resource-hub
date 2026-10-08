import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { ButtonLink } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { SkeletonList } from "@/components/ui/Skeleton";
import { StatusPill } from "@/components/ui/StatusPill";
import { useAuth } from "@/features/auth/authContext";

import { fetchPatents } from "./api";
import {
  officeLabel,
  STATUS_LABEL,
  STATUS_TONE,
  VERIFICATION_LABEL,
  VERIFICATION_TONE,
} from "./labels";
import type { PatentStatus } from "./types";

const FIELD = "mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm";

/** Roles that may record one. A dean and a custodian read; they do not write. */
const CAN_RECORD = new Set(["student", "faculty", "research_coordinator", "admin"]);

export function PatentsPage({ mine = false }: { mine?: boolean }) {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const q = searchParams.get("q") ?? "";
  const status = (searchParams.get("status") ?? "") as PatentStatus | "";
  const page = Number(searchParams.get("page") ?? "1");

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    setSearchParams(next);
  };

  const { data, isPending, isError } = useQuery({
    queryKey: ["patents", { q, status, page, mine, userId: user?.id }],
    queryFn: () =>
      fetchPatents({
        q: q || undefined,
        status: status || undefined,
        page,
        inventor_id: mine ? user?.id : undefined,
      }),
  });

  const canRecord = user ? CAN_RECORD.has(user.role) : false;
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div>
      <PageHeader
        title={mine ? "My patents" : "Patents"}
        description={
          mine
            ? "Patents you invented or recorded, at every stage from filing to grant."
            : "Inventions filed from this university, with where each one has got to at the patent office."
        }
        actions={
          <>
            {canRecord && !mine ? (
              <ButtonLink to="/patents/mine" variant="secondary">
                My patents
              </ButtonLink>
            ) : null}
            {canRecord ? <ButtonLink to="/patents/new">Record a patent</ButtonLink> : null}
          </>
        }
      />

      <div className="mb-6 grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="patent-q" className="block text-sm font-medium">
            Search
          </label>
          <input
            id="patent-q"
            className={FIELD}
            placeholder="Title, abstract or assignee"
            defaultValue={q}
            onBlur={(event) => setParam("q", event.target.value)}
          />
        </div>
        <div>
          <label htmlFor="patent-status" className="block text-sm font-medium">
            Stage
          </label>
          <select
            id="patent-status"
            className={FIELD}
            value={status}
            onChange={(event) => setParam("status", event.target.value)}
          >
            <option value="">Any stage</option>
            {Object.entries(STATUS_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {isPending ? <SkeletonList rows={4} /> : null}
      {isError ? <p className="text-sm text-red-700">Patents could not be loaded.</p> : null}

      {data && data.items.length === 0 ? (
        <EmptyState
          title="No patents yet"
          description={
            canRecord
              ? "Record the first one. A coordinator checks it before it counts."
              : "Nothing has been recorded that matches."
          }
        />
      ) : null}

      <ul className="space-y-3">
        {data?.items.map((patent) => (
          <li key={patent.id} className="rounded-card border border-line bg-surface p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <Link
                to={`/patents/${patent.id}`}
                className="text-base font-semibold text-brand-800 hover:underline"
              >
                {patent.title}
              </Link>
              <div className="flex shrink-0 gap-2">
                <StatusPill tone={STATUS_TONE[patent.status]}>
                  {STATUS_LABEL[patent.status]}
                </StatusPill>
                <StatusPill tone={VERIFICATION_TONE[patent.verification_status]}>
                  {VERIFICATION_LABEL[patent.verification_status]}
                </StatusPill>
              </div>
            </div>
            <p className="mt-1 text-sm text-ink-muted">
              {patent.inventors.map((inventor) => inventor.name).join(", ")}
            </p>
            <p className="mt-1 text-xs text-ink-muted">
              {officeLabel(patent.jurisdiction)} · filed {patent.filing_date}
              {patent.grant_number ? ` · granted as ${patent.grant_number}` : ""}
            </p>
          </li>
        ))}
      </ul>

      {data && totalPages > 1 ? (
        <div className="mt-6 flex items-center gap-3 text-sm">
          <button
            type="button"
            className="rounded-md border border-line px-3 py-1.5 disabled:opacity-50"
            disabled={page <= 1}
            onClick={() => setParam("page", String(page - 1))}
          >
            Previous
          </button>
          <span className="text-ink-muted">
            Page {page} of {totalPages}
          </span>
          <button
            type="button"
            className="rounded-md border border-line px-3 py-1.5 disabled:opacity-50"
            disabled={page >= totalPages}
            onClick={() => setParam("page", String(page + 1))}
          >
            Next
          </button>
        </div>
      ) : null}
    </div>
  );
}

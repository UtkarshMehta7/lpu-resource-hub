import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonList } from "@/components/ui/Skeleton";
import { toApiError } from "@/lib/api/errors";

import { fetchReports, resolveReport, type ContentReport, type ReportStatus } from "./api";

const STATUSES: ReportStatus[] = ["open", "dismissed", "actioned"];
const TAB =
  "rounded-md border border-line px-3 py-1.5 text-sm font-medium capitalize aria-selected:bg-brand-700 aria-selected:text-white";

/** Coordinator/admin review queue for reported content. */
export function ModerationQueuePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const status: ReportStatus = STATUSES.find((s) => s === searchParams.get("status")) ?? "open";
  const queryClient = useQueryClient();
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  const { data, isPending, isError } = useQuery({
    queryKey: ["reports", status],
    queryFn: () => fetchReports(status),
  });

  const resolve = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: "dismissed" | "actioned" }) =>
      resolveReport(id, decision, notes[id]?.trim() || null),
    onSuccess: async () => {
      setError(null);
      await queryClient.invalidateQueries({ queryKey: ["reports"] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (caught) => setError(toApiError(caught).message),
  });

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Reported content</h1>
      <div className="mt-4 flex flex-wrap gap-2" role="tablist">
        {STATUSES.map((value) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={status === value}
            onClick={() => setSearchParams({ status: value })}
            className={TAB}
          >
            {value}
          </button>
        ))}
      </div>

      {error ? (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {error}
        </p>
      ) : null}
      {isPending ? (
        <div className="mt-6">
          <SkeletonList />
        </div>
      ) : null}
      {isError ? (
        <p role="alert" className="mt-6 text-sm text-red-700">
          Could not load reports.
        </p>
      ) : null}
      {data && data.length === 0 ? (
        <div className="mt-6">
          <EmptyState
            title={status === "open" ? "Nothing to review" : "No reports here"}
            description={status === "open" ? "Reported content will appear here." : undefined}
          />
        </div>
      ) : null}

      <ul className="mt-6 space-y-3">
        {data?.map((report) => (
          <li key={report.id} className="rounded-card border border-line bg-surface p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <p className="text-sm font-semibold">
                {report.target_title ?? "(content no longer visible)"}
                <span className="ml-2 font-normal text-ink-muted">{report.target_type}</span>
              </p>
              <span className="rounded-md border border-line px-2 py-1 text-xs capitalize">
                {report.status}
              </span>
            </div>
            <p className="mt-2 text-sm">{report.reason}</p>
            <p className="mt-1 text-xs text-ink-muted">
              Reported by {report.reporter_name} ·{" "}
              {new Date(report.created_at).toLocaleDateString()}
              {targetLink(report) ? (
                <>
                  {" · "}
                  <Link
                    to={targetLink(report) as string}
                    className="text-brand-700 hover:underline"
                  >
                    View content
                  </Link>
                </>
              ) : null}
            </p>
            {report.status === "open" ? (
              <div className="mt-3 space-y-2">
                <label htmlFor={`note-${report.id}`} className="block text-xs font-medium">
                  Resolution note (optional)
                </label>
                <textarea
                  id={`note-${report.id}`}
                  rows={2}
                  value={notes[report.id] ?? ""}
                  onChange={(event) =>
                    setNotes((prev) => ({ ...prev, [report.id]: event.target.value }))
                  }
                  className="w-full rounded-md border border-line bg-surface px-3 py-2 text-sm"
                />
                <div className="flex gap-2">
                  <button
                    type="button"
                    disabled={resolve.isPending}
                    onClick={() => resolve.mutate({ id: report.id, decision: "actioned" })}
                    className="rounded-md bg-brand-700 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                  >
                    Action it
                  </button>
                  <button
                    type="button"
                    disabled={resolve.isPending}
                    onClick={() => resolve.mutate({ id: report.id, decision: "dismissed" })}
                    className="rounded-md border border-line px-3 py-1.5 text-sm disabled:opacity-50"
                  >
                    Dismiss
                  </button>
                </div>
              </div>
            ) : report.resolution_note ? (
              <p className="mt-2 text-xs text-ink-muted">Note: {report.resolution_note}</p>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

function targetLink(report: ContentReport): string | null {
  switch (report.target_type) {
    case "project":
      return `/projects/${report.target_id}`;
    case "opportunity":
      return `/opportunities/${report.target_id}`;
    case "publication":
      return `/publications/${report.target_id}`;
    case "profile":
      return `/researchers/${report.target_id}`;
    default:
      return null;
  }
}

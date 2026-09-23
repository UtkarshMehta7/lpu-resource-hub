import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonList } from "@/components/ui/Skeleton";
import { apiClient } from "@/lib/api/client";

interface AuditEntry {
  id: string;
  actor_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  ip: string | null;
  created_at: string;
}

interface AuditPage {
  items: AuditEntry[];
  page: number;
  page_size: number;
  total: number;
}

const FIELD = "mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm";

/** Admin view of the append-only audit log: who did what, and to what. */
export function AuditLogPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const action = searchParams.get("action") ?? "";
  const entityType = searchParams.get("entity_type") ?? "";
  const page = Number(searchParams.get("page") ?? "1");

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    setSearchParams(next);
  };

  const { data, isPending, isError } = useQuery({
    queryKey: ["audit-logs", { action, entityType, page }],
    queryFn: async () => {
      const response = await apiClient.get<AuditPage>("/api/v1/admin/audit-logs", {
        params: {
          ...(action ? { action } : {}),
          ...(entityType ? { entity_type: entityType } : {}),
          page,
        },
      });
      return response.data;
    },
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Audit log</h1>
      <p className="mt-1 text-sm text-ink-muted">
        Every sensitive action — role changes, verifications, reviews, decisions, moderation — in
        the order it happened. Entries are never edited or deleted.
      </p>

      <div className="mt-6 grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="audit-action" className="block text-sm font-medium">
            Action
          </label>
          <input
            id="audit-action"
            type="search"
            defaultValue={action}
            placeholder="e.g. user.role_changed"
            onChange={(event) => setParam("action", event.target.value)}
            className={FIELD}
          />
        </div>
        <div>
          <label htmlFor="audit-entity" className="block text-sm font-medium">
            Entity type
          </label>
          <input
            id="audit-entity"
            type="search"
            defaultValue={entityType}
            placeholder="e.g. project"
            onChange={(event) => setParam("entity_type", event.target.value)}
            className={FIELD}
          />
        </div>
      </div>

      {isPending ? (
        <div className="mt-6">
          <SkeletonList rows={5} />
        </div>
      ) : null}
      {isError ? (
        <p role="alert" className="mt-6 text-sm text-red-700">
          Could not load the audit log.
        </p>
      ) : null}
      {data && data.items.length === 0 ? (
        <div className="mt-6">
          <EmptyState title="Nothing matches these filters" />
        </div>
      ) : null}

      {data && data.items.length > 0 ? (
        <div className="mt-6 overflow-x-auto rounded-card border border-line bg-surface">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line text-xs uppercase text-ink-muted">
              <tr>
                <th className="px-4 py-3 font-medium">When</th>
                <th className="px-4 py-3 font-medium">Action</th>
                <th className="px-4 py-3 font-medium">Entity</th>
                <th className="px-4 py-3 font-medium">Change</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line align-top">
              {data.items.map((entry) => (
                <tr key={entry.id}>
                  <td className="whitespace-nowrap px-4 py-3 text-ink-muted">
                    {new Date(entry.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-3 font-medium">{entry.action}</td>
                  <td className="px-4 py-3 text-ink-muted">
                    {entry.entity_type}
                    <span className="block font-mono text-[11px]">
                      {entry.entity_id.slice(0, 8)}…
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-ink-muted">
                    {entry.before ? <Change label="before" value={entry.before} /> : null}
                    {entry.after ? <Change label="after" value={entry.after} /> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {data && totalPages > 1 ? (
        <div className="mt-6 flex items-center justify-between">
          <button
            type="button"
            disabled={data.page <= 1}
            onClick={() => setParam("page", String(data.page - 1))}
            className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm disabled:opacity-50"
          >
            Previous
          </button>
          <span className="text-xs text-ink-muted">
            Page {data.page} of {totalPages} · {data.total} entries
          </span>
          <button
            type="button"
            disabled={data.page >= totalPages}
            onClick={() => setParam("page", String(data.page + 1))}
            className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm disabled:opacity-50"
          >
            Next
          </button>
        </div>
      ) : null}
    </div>
  );
}

/** Audit payloads are free-form JSON, so render any shape readably. */
function describe(item: unknown): string {
  if (item === null || item === undefined) return "—";
  if (typeof item === "string") return item;
  if (typeof item === "number" || typeof item === "boolean") return String(item);
  return JSON.stringify(item) ?? "—";
}

function Change({ label, value }: { label: string; value: Record<string, unknown> }) {
  return (
    <p>
      <span className="font-medium">{label}:</span>{" "}
      {Object.entries(value)
        .map(([key, item]) => `${key}=${describe(item)}`)
        .join(", ")}
    </p>
  );
}

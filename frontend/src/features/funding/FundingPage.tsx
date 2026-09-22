import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonList } from "@/components/ui/Skeleton";
import { useAuth } from "@/features/auth/authContext";
import { useNow } from "@/lib/useNow";

import { amountLabel, daysUntil, fetchFundingList } from "./api";

const FIELD = "mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm";

/** Funding calls relevant to Lovely Professional University researchers. */
export function FundingPage() {
  const { user } = useAuth();
  const now = useNow();
  const [searchParams, setSearchParams] = useSearchParams();
  const q = searchParams.get("q") ?? "";
  const openOnly = searchParams.get("open_only") !== "false";
  const page = Number(searchParams.get("page") ?? "1");

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    setSearchParams(next);
  };

  const { data, isPending, isError } = useQuery({
    queryKey: ["funding", { q, openOnly, page }],
    queryFn: () => fetchFundingList({ q: q || undefined, open_only: openOnly, page }),
  });

  const canManage = user?.role === "research_coordinator" || user?.role === "admin";
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Funding calls</h1>
          <p className="mt-1 text-sm text-ink-muted">
            Grants and fellowships for LPU researchers. Save a call and you&apos;ll be reminded
            before it closes.
          </p>
        </div>
        {canManage ? (
          <Link
            to="/funding/new"
            className="rounded-md bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-800"
          >
            Add a call
          </Link>
        ) : null}
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-[1fr_12rem]">
        <div>
          <label htmlFor="funding-q" className="block text-sm font-medium">
            Search
          </label>
          <input
            id="funding-q"
            type="search"
            defaultValue={q}
            placeholder="Title, organisation or description"
            onChange={(event) => setParam("q", event.target.value)}
            className={FIELD}
          />
        </div>
        <div>
          <label htmlFor="funding-open" className="block text-sm font-medium">
            Show
          </label>
          <select
            id="funding-open"
            value={openOnly ? "open" : "all"}
            onChange={(event) =>
              setParam("open_only", event.target.value === "open" ? "" : "false")
            }
            className={FIELD}
          >
            <option value="open">Open calls</option>
            <option value="all">All calls</option>
          </select>
        </div>
      </div>

      {isPending ? (
        <div className="mt-6">
          <SkeletonList />
        </div>
      ) : null}
      {isError ? (
        <p role="alert" className="mt-6 text-sm text-red-700">
          Could not load funding calls.
        </p>
      ) : null}
      {data && data.items.length === 0 ? (
        <div className="mt-6">
          <EmptyState
            title="No funding calls here"
            description="Research coordinators and admins add calls for the university."
          />
        </div>
      ) : null}

      <ul className="mt-6 space-y-3">
        {data?.items.map((call) => {
          const days = daysUntil(call.deadline, now);
          return (
            <li key={call.id} className="rounded-card border border-line bg-surface p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <Link to={`/funding/${call.id}`} className="text-sm font-semibold hover:underline">
                  {call.title}
                </Link>
                <span className="rounded-md border border-line px-2 py-1 text-xs text-ink-muted">
                  {call.status === "open" && days !== null && days >= 0
                    ? `Closes in ${days} day${days === 1 ? "" : "s"}`
                    : `Closes ${call.deadline}`}
                </span>
              </div>
              <p className="mt-1 text-xs text-ink-muted">
                {[call.organization, amountLabel(call)].filter(Boolean).join(" · ")}
                {call.is_demo ? " · demo data" : ""}
              </p>
              <p className="mt-2 text-sm text-ink-muted">{call.description.slice(0, 180)}</p>
            </li>
          );
        })}
      </ul>

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
            Page {data.page} of {totalPages}
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

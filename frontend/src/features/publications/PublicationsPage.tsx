import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { useAuth } from "@/features/auth/authContext";

import { fetchPublications } from "./api";
import { PublicationItem } from "./PublicationList";
import { SkeletonList } from "@/components/ui/Skeleton";

const FIELD_CLASS = "mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm";

/** Lists publications. `mine` shows ones the caller authored or created. */
export function PublicationsPage({ mine = false }: { mine?: boolean }) {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const q = searchParams.get("q") ?? "";
  const yearParam = searchParams.get("year") ?? "";
  const year = /^\d{4}$/.test(yearParam) ? Number(yearParam) : undefined;
  const page = Number(searchParams.get("page") ?? "1");

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value) {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    if (key !== "page") next.delete("page");
    setSearchParams(next);
  };

  const authorId = mine ? user?.id : undefined;
  const { data, isPending, isError } = useQuery({
    queryKey: ["publications", { q, year, page, authorId }],
    queryFn: () => fetchPublications({ q: q || undefined, year, page, author_id: authorId }),
  });

  const canCreate = user?.role === "faculty" || user?.role === "research_coordinator";
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">
          {mine ? "My publications" : "Publications"}
        </h1>
        <div className="flex gap-2">
          {canCreate && !mine ? (
            <Link
              to="/publications/mine"
              className="rounded-md border border-line bg-surface px-3 py-2 text-sm font-medium"
            >
              My publications
            </Link>
          ) : null}
          {canCreate ? (
            <Link
              to="/publications/new"
              className="rounded-md bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-800"
            >
              New publication
            </Link>
          ) : null}
        </div>
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-[1fr_8rem]">
        <div>
          <label htmlFor="publication-q" className="block text-sm font-medium">
            Search
          </label>
          <input
            id="publication-q"
            type="search"
            defaultValue={q}
            placeholder="Title, abstract or venue"
            onChange={(event) => setParam("q", event.target.value)}
            className={FIELD_CLASS}
          />
        </div>
        <div>
          <label htmlFor="publication-year" className="block text-sm font-medium">
            Year
          </label>
          <input
            id="publication-year"
            inputMode="numeric"
            defaultValue={yearParam}
            placeholder="Any"
            onChange={(event) => setParam("year", event.target.value)}
            className={FIELD_CLASS}
          />
        </div>
      </div>

      {isPending ? (
        <div className="mt-6">
          <SkeletonList rows={3} />
        </div>
      ) : null}
      {isError ? (
        <p role="alert" className="mt-6 text-sm text-red-700">
          Could not load publications.
        </p>
      ) : null}
      {data && data.items.length === 0 ? (
        <p className="mt-6 rounded-card border border-line bg-surface px-4 py-6 text-sm text-ink-muted">
          {mine ? "You don't have any publications yet." : "No publications match these filters."}
        </p>
      ) : null}

      {data && data.items.length > 0 ? (
        <>
          <ul className="mt-6 space-y-3">
            {data.items.map((publication) => (
              <PublicationItem key={publication.id} publication={publication} />
            ))}
          </ul>
          {totalPages > 1 ? (
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
        </>
      ) : null}
    </div>
  );
}

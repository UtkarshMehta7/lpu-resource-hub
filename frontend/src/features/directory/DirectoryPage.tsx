import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import type { Availability } from "@/features/profiles/types";

import { fetchResearchers, type DirectoryFilters } from "./api";
import { fetchDepartments, fetchSchools } from "./api-org";
import { ResearcherCardItem } from "./ResearcherCardItem";

const FIELD_CLASS = "mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm";

/**
 * Filters live in the URL, so a filtered directory is shareable and the back
 * button works. The query key includes them, so TanStack Query caches each
 * combination separately.
 */
export function DirectoryPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  const filters: DirectoryFilters = {
    q: searchParams.get("q") ?? undefined,
    school_id: searchParams.get("school_id") ?? undefined,
    department_id: searchParams.get("department_id") ?? undefined,
    availability: (searchParams.get("availability") as Availability | null) ?? undefined,
    verified_only: searchParams.get("verified_only") === "true",
    page: Number(searchParams.get("page") ?? "1"),
  };

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value) {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    if (key !== "page") next.delete("page");
    setSearchParams(next);
  };

  const { data: schools } = useQuery({ queryKey: ["schools"], queryFn: fetchSchools });
  const { data: departments } = useQuery({
    queryKey: ["departments", filters.school_id],
    queryFn: () => fetchDepartments(filters.school_id),
  });
  const { data, isPending, isError } = useQuery({
    queryKey: ["researchers", filters],
    queryFn: () => fetchResearchers(filters),
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Researchers</h1>
      <p className="mt-1 text-sm text-ink-muted">
        Find researchers across departments by expertise, skill or availability.
      </p>

      <div className="mt-6 grid gap-6 md:grid-cols-[16rem_1fr]">
        <aside className="space-y-4">
          <div>
            <label htmlFor="q" className="block text-sm font-medium">
              Search
            </label>
            <input
              id="q"
              type="search"
              defaultValue={filters.q ?? ""}
              placeholder="Name, skill or area"
              onChange={(event) => setFilter("q", event.target.value)}
              className={FIELD_CLASS}
            />
          </div>

          <div>
            <label htmlFor="school" className="block text-sm font-medium">
              School
            </label>
            <select
              id="school"
              value={filters.school_id ?? ""}
              onChange={(event) => {
                setFilter("department_id", "");
                setFilter("school_id", event.target.value);
              }}
              className={FIELD_CLASS}
            >
              <option value="">All schools</option>
              {(schools ?? []).map((school) => (
                <option key={school.id} value={school.id}>
                  {school.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="department" className="block text-sm font-medium">
              Department
            </label>
            <select
              id="department"
              value={filters.department_id ?? ""}
              onChange={(event) => setFilter("department_id", event.target.value)}
              className={FIELD_CLASS}
            >
              <option value="">All departments</option>
              {(departments ?? []).map((department) => (
                <option key={department.id} value={department.id}>
                  {department.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="availability" className="block text-sm font-medium">
              Availability
            </label>
            <select
              id="availability"
              value={filters.availability ?? ""}
              onChange={(event) => setFilter("availability", event.target.value)}
              className={FIELD_CLASS}
            >
              <option value="">Any</option>
              <option value="available">Available</option>
              <option value="limited">Limited</option>
              <option value="unavailable">Unavailable</option>
            </select>
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={filters.verified_only ?? false}
              onChange={(event) => setFilter("verified_only", event.target.checked ? "true" : "")}
            />
            Verified researchers only
          </label>
        </aside>

        <section>
          {isPending ? <p className="text-sm text-ink-muted">Loading researchers…</p> : null}

          {isError ? (
            <p role="alert" className="text-sm text-red-700">
              Could not load the directory.
            </p>
          ) : null}

          {data && data.items.length === 0 ? (
            <p className="rounded-card border border-line bg-surface px-4 py-6 text-sm text-ink-muted">
              No researchers match these filters. Try removing one.
            </p>
          ) : null}

          {data && data.items.length > 0 ? (
            <>
              <p className="text-sm text-ink-muted">{data.total} researchers</p>
              <ul className="mt-3 space-y-3">
                {data.items.map((researcher) => (
                  <ResearcherCardItem key={researcher.user_id} researcher={researcher} />
                ))}
              </ul>

              {totalPages > 1 ? (
                <div className="mt-6 flex items-center justify-between gap-3">
                  <button
                    type="button"
                    disabled={data.page <= 1}
                    onClick={() => setFilter("page", String(data.page - 1))}
                    className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm font-medium hover:bg-canvas disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Previous
                  </button>
                  <span className="text-xs text-ink-muted">
                    Page {data.page} of {totalPages}
                  </span>
                  <button
                    type="button"
                    disabled={data.page >= totalPages}
                    onClick={() => setFilter("page", String(data.page + 1))}
                    className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm font-medium hover:bg-canvas disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Next
                  </button>
                </div>
              ) : null}
            </>
          ) : null}
        </section>
      </div>
    </div>
  );
}

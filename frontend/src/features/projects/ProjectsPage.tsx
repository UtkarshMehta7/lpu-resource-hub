import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { useAuth } from "@/features/auth/authContext";

import { fetchProjects, STATUS_LABEL, type ProjectStatus } from "./api";

const FIELD_CLASS = "mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm";

/** Lists projects. `mine` shows the caller's own and joined projects. */
export function ProjectsPage({ mine = false }: { mine?: boolean }) {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const q = searchParams.get("q") ?? "";
  const status = (searchParams.get("status") as ProjectStatus | null) ?? undefined;
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

  const { data, isPending, isError } = useQuery({
    queryKey: ["projects", { q, status, page, mine }],
    queryFn: () => fetchProjects({ q: q || undefined, status, page, mine }),
  });

  const canCreate = user?.role === "faculty" || user?.role === "research_coordinator";
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">
          {mine ? "My projects" : "Research projects"}
        </h1>
        {canCreate ? (
          <Link
            to="/projects/new"
            className="rounded-md bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-800"
          >
            New project
          </Link>
        ) : null}
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-[1fr_12rem]">
        <div>
          <label htmlFor="project-q" className="block text-sm font-medium">
            Search
          </label>
          <input
            id="project-q"
            type="search"
            defaultValue={q}
            placeholder="Title, summary or description"
            onChange={(event) => setParam("q", event.target.value)}
            className={FIELD_CLASS}
          />
        </div>
        <div>
          <label htmlFor="project-status" className="block text-sm font-medium">
            Status
          </label>
          <select
            id="project-status"
            value={status ?? ""}
            onChange={(event) => setParam("status", event.target.value)}
            className={FIELD_CLASS}
          >
            <option value="">Any visible</option>
            {Object.entries(STATUS_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {isPending ? <p className="mt-6 text-sm text-ink-muted">Loading projects…</p> : null}
      {isError ? (
        <p role="alert" className="mt-6 text-sm text-red-700">
          Could not load projects.
        </p>
      ) : null}
      {data && data.items.length === 0 ? (
        <p className="mt-6 rounded-card border border-line bg-surface px-4 py-6 text-sm text-ink-muted">
          {mine ? "You don't have any projects yet." : "No projects match these filters."}
        </p>
      ) : null}

      {data && data.items.length > 0 ? (
        <>
          <ul className="mt-6 space-y-3">
            {data.items.map((project) => (
              <li key={project.id} className="rounded-card border border-line bg-surface p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <Link
                    to={`/projects/${project.id}`}
                    className="text-sm font-semibold hover:underline"
                  >
                    {project.title}
                  </Link>
                  <span className="rounded-md border border-line px-2 py-1 text-xs text-ink-muted">
                    {STATUS_LABEL[project.status]}
                  </span>
                </div>
                <p className="mt-1 text-sm text-ink-muted">{project.summary}</p>
                <p className="mt-2 text-xs text-ink-muted">Led by {project.owner_name}</p>
              </li>
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

import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonList } from "@/components/ui/Skeleton";
import { useAuth } from "@/features/auth/authContext";
import { fetchDepartments } from "@/features/directory/api-org";

import { fetchFacilities } from "./api";

const FIELD = "mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm";

/** The LPU facility directory: labs and workshops across departments. */
export function FacilitiesPage() {
  const { user } = useAuth();
  const canManage = user?.role === "research_coordinator" || user?.role === "admin";
  const [searchParams, setSearchParams] = useSearchParams();
  const q = searchParams.get("q") ?? "";
  const departmentId = searchParams.get("department_id") ?? "";
  const page = Number(searchParams.get("page") ?? "1");

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    setSearchParams(next);
  };

  const { data: departments } = useQuery({
    queryKey: ["departments"],
    queryFn: () => fetchDepartments(),
  });
  const { data, isPending, isError } = useQuery({
    queryKey: ["facilities", { q, departmentId, page }],
    queryFn: () =>
      fetchFacilities({ q: q || undefined, department_id: departmentId || undefined, page }),
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">LPU facilities</h1>
          <p className="mt-1 text-sm text-ink-muted">
            Labs, workshops and shared equipment across Lovely Professional University departments.
          </p>
        </div>
        {canManage ? (
          <Link
            to="/facilities/new"
            className="rounded-md bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-800"
          >
            New facility
          </Link>
        ) : null}
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="facility-q" className="block text-sm font-medium">
            Search
          </label>
          <input
            id="facility-q"
            type="search"
            defaultValue={q}
            placeholder="Name, description or location"
            onChange={(event) => setParam("q", event.target.value)}
            className={FIELD}
          />
        </div>
        <div>
          <label htmlFor="facility-dept" className="block text-sm font-medium">
            Department
          </label>
          <select
            id="facility-dept"
            value={departmentId}
            onChange={(event) => setParam("department_id", event.target.value)}
            className={FIELD}
          >
            <option value="">Any department</option>
            {departments?.map((department) => (
              <option key={department.id} value={department.id}>
                {department.name}
              </option>
            ))}
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
          Could not load facilities.
        </p>
      ) : null}
      {data && data.items.length === 0 ? (
        <div className="mt-6">
          <EmptyState
            title="No facilities match these filters"
            description="Research coordinators and admins add facilities for their department."
          />
        </div>
      ) : null}

      <ul className="mt-6 space-y-3">
        {data?.items.map((facility) => (
          <li key={facility.id} className="rounded-card border border-line bg-surface p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <Link
                to={`/facilities/${facility.id}`}
                className="text-sm font-semibold hover:underline"
              >
                {facility.name}
              </Link>
              <span className="rounded-md border border-line px-2 py-1 text-xs text-ink-muted">
                {facility.equipment_count} {facility.equipment_count === 1 ? "item" : "items"} of
                equipment
              </span>
            </div>
            {facility.description ? (
              <p className="mt-1 text-sm text-ink-muted">{facility.description}</p>
            ) : null}
            <p className="mt-1 text-xs text-ink-muted">
              {[facility.location, facility.contact].filter(Boolean).join(" · ")}
            </p>
          </li>
        ))}
      </ul>

      {totalPages > 1 && data ? (
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

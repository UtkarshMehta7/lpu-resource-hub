import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { useAuth } from "@/features/auth/authContext";
import { fetchDepartments } from "@/features/directory/api-org";
import { searchSkills } from "@/features/taxonomy/api";
import { Uid } from "@/components/ui/Uid";

import { fetchOpportunities } from "./api";
import {
  OPPORTUNITY_STATUS_LABEL,
  TYPE_LABEL,
  type OpportunityStatus,
  type OpportunityType,
} from "./labels";

const FIELD_CLASS = "mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm";

/** The opportunity board. `mine` lists the caller's own postings (any status). */
export function OpportunitiesPage({ mine = false }: { mine?: boolean }) {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const get = (key: string) => searchParams.get(key) ?? "";
  const q = get("q");
  const type = (get("type") || undefined) as OpportunityType | undefined;
  // The public board defaults to open postings; "any" shows every visible one.
  const statusParam = get("status") || (mine ? "any" : "open");
  const status = statusParam === "any" ? undefined : (statusParam as OpportunityStatus);
  const departmentId = get("department_id");
  const skillId = get("skill_id");
  const deadlineBefore = get("deadline_before");
  const page = Number(get("page") || "1");

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

  const { data: departments } = useQuery({
    queryKey: ["departments"],
    queryFn: () => fetchDepartments(),
  });
  const { data: skills } = useQuery({ queryKey: ["skills", ""], queryFn: () => searchSkills() });

  const { data, isPending, isError } = useQuery({
    queryKey: [
      "opportunities",
      { q, type, status, departmentId, skillId, deadlineBefore, page, mine },
    ],
    queryFn: () =>
      fetchOpportunities({
        q: q || undefined,
        type,
        status,
        department_id: departmentId || undefined,
        skill_id: skillId || undefined,
        deadline_before: deadlineBefore || undefined,
        page,
        mine,
      }),
  });

  const canCreate = user?.role === "faculty" || user?.role === "research_coordinator";
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">
          {mine ? "My opportunities" : "Opportunity board"}
        </h1>
        <div className="flex gap-2">
          <Link
            to="/me/applications"
            className="rounded-md border border-line bg-surface px-3 py-2 text-sm font-medium"
          >
            My applications
          </Link>
          {canCreate && !mine ? (
            <Link
              to="/opportunities/mine"
              className="rounded-md border border-line bg-surface px-3 py-2 text-sm font-medium"
            >
              My postings
            </Link>
          ) : null}
          {canCreate ? (
            <Link
              to="/opportunities/new"
              className="rounded-md bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-800"
            >
              New opportunity
            </Link>
          ) : null}
        </div>
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-3">
        <div className="sm:col-span-3">
          <label htmlFor="opp-q" className="block text-sm font-medium">
            Search
          </label>
          <input
            id="opp-q"
            type="search"
            defaultValue={q}
            placeholder="Title, description or eligibility"
            onChange={(event) => setParam("q", event.target.value)}
            className={FIELD_CLASS}
          />
        </div>
        <div>
          <label htmlFor="opp-type" className="block text-sm font-medium">
            Type
          </label>
          <select
            id="opp-type"
            value={type ?? ""}
            onChange={(event) => setParam("type", event.target.value)}
            className={FIELD_CLASS}
          >
            <option value="">Any type</option>
            {Object.entries(TYPE_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="opp-status" className="block text-sm font-medium">
            Status
          </label>
          <select
            id="opp-status"
            value={statusParam}
            onChange={(event) => setParam("status", event.target.value)}
            className={FIELD_CLASS}
          >
            <option value="any">Any visible</option>
            {Object.entries(OPPORTUNITY_STATUS_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="opp-dept" className="block text-sm font-medium">
            Department
          </label>
          <select
            id="opp-dept"
            value={departmentId}
            onChange={(event) => setParam("department_id", event.target.value)}
            className={FIELD_CLASS}
          >
            <option value="">Any department</option>
            {departments?.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="opp-skill" className="block text-sm font-medium">
            Skill
          </label>
          <select
            id="opp-skill"
            value={skillId}
            onChange={(event) => setParam("skill_id", event.target.value)}
            className={FIELD_CLASS}
          >
            <option value="">Any skill</option>
            {skills?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="opp-deadline" className="block text-sm font-medium">
            Deadline on or before
          </label>
          <input
            id="opp-deadline"
            type="date"
            value={deadlineBefore}
            onChange={(event) => setParam("deadline_before", event.target.value)}
            className={FIELD_CLASS}
          />
        </div>
      </div>

      {isPending ? <p className="mt-6 text-sm text-ink-muted">Loading opportunities…</p> : null}
      {isError ? (
        <p role="alert" className="mt-6 text-sm text-red-700">
          Could not load opportunities.
        </p>
      ) : null}
      {data && data.items.length === 0 ? (
        <p className="mt-6 rounded-card border border-line bg-surface px-4 py-6 text-sm text-ink-muted">
          {mine
            ? "You haven't posted any opportunities yet."
            : "No opportunities match these filters."}
        </p>
      ) : null}

      {data && data.items.length > 0 ? (
        <>
          <ul className="mt-6 space-y-3">
            {data.items.map((o) => (
              <li key={o.id} className="rounded-card border border-line bg-surface p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <Link
                    to={`/opportunities/${o.id}`}
                    className="text-sm font-semibold hover:underline"
                  >
                    {o.title}
                  </Link>
                  <span className="rounded-md border border-line px-2 py-1 text-xs text-ink-muted">
                    {TYPE_LABEL[o.opportunity_type]} · {OPPORTUNITY_STATUS_LABEL[o.status]}
                  </span>
                </div>
                <p className="mt-1 text-xs text-ink-muted">
                  {o.project_title ? `${o.project_title} · ` : ""}Posted by {o.creator_name}{" "}
                  <Uid value={o.creator_registration_number} /> · Deadline {o.deadline} ·{" "}
                  {o.accepted_count}/{o.positions} filled
                </p>
                {o.skills.length > 0 ? (
                  <ul className="mt-2 flex flex-wrap gap-1">
                    {o.skills.map((s) => (
                      <li
                        key={s.id}
                        className="rounded-md border border-line px-2 py-0.5 text-xs text-ink-muted"
                      >
                        {s.name}
                      </li>
                    ))}
                  </ul>
                ) : null}
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

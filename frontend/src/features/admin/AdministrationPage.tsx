import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import type { Role } from "@/features/auth/types";
import { fetchDepartments, fetchSchools } from "@/features/directory/api-org";

import { fetchUsers } from "./api";

/**
 * The administrator's home.
 *
 * An admin's job on this platform is narrow and specific: appoint the
 * coordinators, keep the organisation structure right, and hold the records.
 * This page says so plainly and links to each of those, rather than dropping
 * someone into a table of 117 accounts and leaving them to infer it.
 */

const ROLE_CARDS = [
  { role: "research_coordinator" as const, label: "Coordinators", to: "/admin/coordinators" },
  { role: "faculty" as const, label: "Faculty", to: "/researchers" },
  { role: "student" as const, label: "Students", to: "/students" },
  { role: "admin" as const, label: "Admins", to: "/admin/users" },
];

const PRIVILEGES: { group: string; items: { label: string; detail: string; to: string }[] }[] = [
  {
    group: "People",
    items: [
      {
        label: "Appoint a coordinator",
        detail: "The only account type you create directly. They take it from there.",
        to: "/people/new",
      },
      {
        label: "Coordinators",
        detail: "Who oversees which department.",
        to: "/admin/coordinators",
      },
      {
        label: "Administrators",
        detail: "Promote a successor with their confirmation, or step down.",
        to: "/admin/administrators",
      },
      {
        label: "Create any account",
        detail: "The override, for what the hierarchy can't serve. Audited as one.",
        to: "/admin/accounts/new",
      },
      {
        label: "All accounts",
        detail:
          "Change a role, place someone in a department, rename, deactivate, reissue a password.",
        to: "/admin/users",
      },
    ],
  },
  {
    group: "Organisation",
    items: [
      {
        label: "Schools and departments",
        detail: "The structure every scope rule is built on.",
        to: "/admin/organisation",
      },
    ],
  },
  {
    group: "Oversight",
    items: [
      {
        label: "Verification queue",
        detail: "Researcher profiles awaiting a decision, across every department.",
        to: "/coordinator/verification-queue",
      },
      {
        label: "Project reviews",
        detail: "Projects waiting to go active.",
        to: "/coordinator/review-queue",
      },
      {
        label: "Reported content",
        detail: "Resolve a report, and hide what it points at if it warrants it.",
        to: "/admin/reports",
      },
      {
        label: "Analytics",
        detail: "Platform-wide aggregates and the collaboration network.",
        to: "/analytics",
      },
    ],
  },
  {
    group: "Records",
    items: [
      {
        label: "Audit log",
        detail: "Every sensitive action, in order, never edited or deleted.",
        to: "/admin/audit-logs",
      },
      {
        label: "Platform settings",
        detail: "The configured behaviour: scoring weights, token lifetimes, scheduler. Read-only.",
        to: "/admin/settings",
      },
    ],
  },
];

/** One count per role, asked of the server rather than tallied from a page:
 * a page of 100 doesn't see the coordinators among 117 accounts. */
function useRoleCount(role: Role) {
  return useQuery({
    queryKey: ["admin", "users", "count", role],
    queryFn: () => fetchUsers({ role, page_size: 1 }),
    select: (page) => page.total,
  });
}

export function AdministrationPage() {
  const counts: Record<string, number | undefined> = {
    research_coordinator: useRoleCount("research_coordinator").data,
    faculty: useRoleCount("faculty").data,
    student: useRoleCount("student").data,
    admin: useRoleCount("admin").data,
  };
  const { data: schools } = useQuery({ queryKey: ["schools"], queryFn: () => fetchSchools() });
  const { data: departments } = useQuery({
    queryKey: ["departments"],
    queryFn: () => fetchDepartments(),
  });

  const noDepartments = departments !== undefined && departments.length === 0;

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Administration</h1>
      <p className="mt-1 text-sm text-ink-muted">
        What you can do here, and what the platform currently holds.
      </p>

      {noDepartments ? (
        <div className="mt-6 rounded-card border border-brand-200 bg-brand-50 p-4 text-sm">
          <strong className="font-semibold">Start with the organisation.</strong> There are no
          departments yet, and a coordinator is appointed to oversee one — so nobody can be added
          until at least one exists.{" "}
          <Link to="/admin/organisation" className="font-medium text-brand-700 hover:underline">
            Add a school and a department
          </Link>
          .
        </div>
      ) : null}

      {/* The one thing an admin creates, said once, prominently. */}
      <section className="mt-6 rounded-card border border-line bg-surface p-5">
        <h2 className="text-sm font-semibold">How accounts come into being</h2>
        <ol className="mt-3 flex flex-wrap items-center gap-2 text-sm">
          {["You", "Coordinator", "Faculty", "Student"].map((step, index) => (
            <li key={step} className="flex items-center gap-2">
              <span
                className={
                  index === 0
                    ? "rounded-md bg-brand-700 px-2.5 py-1 font-medium text-white"
                    : "rounded-md border border-line px-2.5 py-1 text-ink-muted"
                }
              >
                {step}
              </span>
              {index < 3 ? (
                <span aria-hidden="true" className="text-ink-muted">
                  →
                </span>
              ) : null}
            </li>
          ))}
        </ol>
        <p className="mt-3 text-sm text-ink-muted">
          You appoint research coordinators. They appoint the faculty of the department they
          oversee, and faculty enrol their own students. Nobody signs themselves up, and nobody
          creates a peer or anyone above them.
        </p>
        <Link
          to="/people/new"
          className="mt-4 inline-block rounded-md bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-800"
        >
          Add coordinator
        </Link>
      </section>

      <section className="mt-6">
        <h2 className="text-sm font-semibold">On the platform</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {ROLE_CARDS.map((card) => (
            <Link
              key={card.role}
              to={card.to}
              className="rounded-card border border-line bg-surface p-4 hover:border-brand-200 hover:bg-brand-50"
            >
              <span className="block text-xs uppercase tracking-wide text-ink-muted">
                {card.label}
              </span>
              <span className="mt-1 block text-2xl font-semibold">{counts[card.role] ?? "—"}</span>
            </Link>
          ))}
          <Link
            to="/admin/organisation"
            className="rounded-card border border-line bg-surface p-4 hover:border-brand-200 hover:bg-brand-50"
          >
            <span className="block text-xs uppercase tracking-wide text-ink-muted">Schools</span>
            <span className="mt-1 block text-2xl font-semibold">{schools?.length ?? 0}</span>
          </Link>
          <Link
            to="/admin/organisation"
            className="rounded-card border border-line bg-surface p-4 hover:border-brand-200 hover:bg-brand-50"
          >
            <span className="block text-xs uppercase tracking-wide text-ink-muted">
              Departments
            </span>
            <span className="mt-1 block text-2xl font-semibold">{departments?.length ?? 0}</span>
          </Link>
        </div>
      </section>

      <section className="mt-8">
        <h2 className="text-sm font-semibold">Your privileges</h2>
        <div className="mt-3 grid gap-4 lg:grid-cols-2">
          {PRIVILEGES.map((group) => (
            <div key={group.group} className="rounded-card border border-line bg-surface p-4">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-brand-700">
                {group.group}
              </h3>
              <ul className="mt-3 space-y-3">
                {group.items.map((item) => (
                  <li key={item.to + item.label}>
                    <Link to={item.to} className="text-sm font-medium hover:underline">
                      {item.label}
                    </Link>
                    <span className="block text-xs text-ink-muted">{item.detail}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <p className="mt-3 text-xs text-ink-muted">
          Every one of these is checked again on the server. Nothing here is enforced by hiding a
          link — an admin who loses the role loses the action, immediately.
        </p>
      </section>
    </div>
  );
}

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/ui/EmptyState";
import { fetchDepartments } from "@/features/directory/api-org";

import { fetchUsers } from "./api";

/**
 * The coordinators an admin has appointed, and what each one oversees.
 *
 * A coordinator's scope is the whole of their authority — who they may
 * verify, review, approve and appoint — so it is the column that matters
 * here, not their email address.
 */
export function CoordinatorsPage() {
  const { data, isPending, isError } = useQuery({
    queryKey: ["admin", "users", "research_coordinator"],
    queryFn: () => fetchUsers({ role: "research_coordinator", page_size: 100 }),
  });
  const { data: departments } = useQuery({
    queryKey: ["departments"],
    queryFn: () => fetchDepartments(),
  });

  const departmentName = (id: string | null) =>
    departments?.find((department) => department.id === id)?.name;

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Research coordinators</h1>
          <p className="mt-1 text-sm text-ink-muted">
            Each one oversees a department: they verify its researchers, review its projects,
            approve its bookings, and appoint its faculty.
          </p>
        </div>
        <Link
          to="/people/new"
          className="rounded-md bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-800"
        >
          Add coordinator
        </Link>
      </div>

      {isPending ? <p className="mt-6 text-sm text-ink-muted">Loading…</p> : null}
      {isError ? (
        <p role="alert" className="mt-6 text-sm text-red-700">
          Could not load coordinators.
        </p>
      ) : null}

      {data && data.items.length === 0 ? (
        <div className="mt-6">
          <EmptyState title="No coordinators yet">
            Appoint one, and they can start building out their department.
          </EmptyState>
        </div>
      ) : null}

      {data && data.items.length > 0 ? (
        <div className="mt-6 overflow-x-auto rounded-card border border-line bg-surface">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line text-xs uppercase text-ink-muted">
              <tr>
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Oversees</th>
                <th className="px-4 py-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data.items.map((item) => {
                const scope = departmentName(item.coordinator_scope_id);
                return (
                  <tr key={item.id}>
                    <td className="px-4 py-3">
                      {item.full_name}
                      <span className="block font-mono text-xs text-ink-muted">
                        {item.registration_number}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {scope ?? (
                        <span className="text-ink-muted">
                          No scope —{" "}
                          <Link to="/admin/users" className="hover:underline">
                            set one
                          </Link>
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {item.is_active ? "Active" : "Inactive"}
                      {item.must_change_password ? (
                        <span className="block text-xs text-ink-muted">password not set yet</span>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

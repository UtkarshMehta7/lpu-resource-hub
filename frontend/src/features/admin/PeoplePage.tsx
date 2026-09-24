import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { Uid } from "@/components/ui/Uid";
import { SkeletonList } from "@/components/ui/Skeleton";
import { useAuth } from "@/features/auth/authContext";
import type { Role } from "@/features/auth/types";
import { fetchDepartments } from "@/features/directory/api-org";
import { toApiError } from "@/lib/api/errors";

import { deleteUser, fetchDeletionImpact, fetchManageableUsers } from "./api";
import { DeletionDetails } from "./DeletionDetails";
import type { AdminUserRead } from "./types";

const PEOPLE_QUERY_KEY = ["people", "manageable"] as const;

const ROLE_LABELS: Record<Role, string> = {
  student: "Student",
  faculty: "Faculty",
  research_coordinator: "Coordinator",
  admin: "Administrator",
};

/** What each role is responsible for, so the page says whose list this is. */
const RESPONSIBILITY: Record<Role, string> = {
  admin: "Everyone on the platform. You can remove any account but your own.",
  research_coordinator:
    "The faculty and students of the department you oversee. Removing an account is permanent — deactivate instead if the person has simply left.",
  faculty:
    "The students of your department. Removing an account is permanent — deactivate instead if the person has simply left.",
  student: "Nobody: students do not manage other accounts.",
};

/**
 * The people a coordinator or faculty member is responsible for.
 *
 * Administrators have the full console at /admin/users; this is the same
 * authority one rung down, and it exists because the API has always let a
 * coordinator remove their department's faculty while the interface gave them
 * nowhere to do it. The list comes from the same rule as the button, so every
 * row here can actually be acted on.
 */
export function PeoplePage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<AdminUserRead | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const { data, isPending, isError } = useQuery({
    queryKey: PEOPLE_QUERY_KEY,
    queryFn: () => fetchManageableUsers({ page_size: 100 }),
  });
  const { data: departments } = useQuery({
    queryKey: ["departments"],
    queryFn: () => fetchDepartments(),
  });

  const { data: impact, isPending: impactPending } = useQuery({
    queryKey: ["people", "deletion-impact", pending?.id ?? null],
    queryFn: () => fetchDeletionImpact(pending?.id as string),
    enabled: pending !== null,
  });

  const removal = useMutation({
    mutationFn: (userId: string) => deleteUser(userId),
    onSuccess: async () => {
      setPending(null);
      setActionError(null);
      await queryClient.invalidateQueries({ queryKey: PEOPLE_QUERY_KEY });
    },
    onError: (error: unknown) => setActionError(toApiError(error).message),
  });

  const departmentName = (id: string | null) =>
    departments?.find((department) => department.id === id)?.name;

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">People you manage</h1>
          <p className="mt-1 max-w-2xl text-sm text-ink-muted">
            {user ? RESPONSIBILITY[user.role] : ""}
          </p>
        </div>
        <Link
          to="/people/new"
          className="rounded-md bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-800"
        >
          Add someone
        </Link>
      </div>

      {actionError ? (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {actionError}
        </p>
      ) : null}

      {isPending ? (
        <div className="mt-6">
          <SkeletonList rows={3} />
        </div>
      ) : null}
      {isError ? (
        <p role="alert" className="mt-6 text-sm text-red-700">
          Could not load the list.
        </p>
      ) : null}

      {data && data.items.length === 0 ? (
        <div className="mt-6">
          <EmptyState
            title="Nobody yet"
            description={
              user?.role === "research_coordinator"
                ? "Once you appoint faculty to the department you oversee, they appear here. If you have just been appointed and this stays empty, ask an administrator to check the department you oversee."
                : "The students you enrol appear here."
            }
          />
        </div>
      ) : null}

      {data && data.items.length > 0 ? (
        <div className="mt-6 overflow-x-auto rounded-card border border-line bg-surface">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line text-xs uppercase text-ink-muted">
              <tr>
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Role</th>
                <th className="px-4 py-3 font-medium">Department</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data.items.map((item) => (
                <tr key={item.id}>
                  <td className="px-4 py-3">
                    {item.full_name}
                    <Uid value={item.registration_number} className="ml-2" />
                  </td>
                  <td className="px-4 py-3">{ROLE_LABELS[item.role]}</td>
                  <td className="px-4 py-3">
                    {departmentName(item.department_id) ?? (
                      <span className="text-ink-muted">None</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {item.is_active ? "Active" : "Inactive"}
                    {item.must_change_password ? (
                      <span className="block text-xs text-ink-muted">password not set yet</span>
                    ) : null}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      disabled={removal.isPending}
                      onClick={() => {
                        setActionError(null);
                        setPending(item);
                      }}
                      className="rounded-md border border-red-300 bg-surface px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
                      aria-label={`Delete ${item.full_name}`}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <ConfirmDialog
        open={pending !== null}
        title="Delete this account permanently?"
        description={
          pending
            ? `${pending.full_name} (${pending.registration_number}) will be removed for good. This cannot be undone.`
            : ""
        }
        confirmLabel="Delete permanently"
        isConfirming={removal.isPending}
        onConfirm={() => {
          if (pending) removal.mutate(pending.id);
        }}
        onCancel={() => setPending(null)}
      >
        <DeletionDetails impact={impact} loading={impactPending} />
      </ConfirmDialog>
    </div>
  );
}

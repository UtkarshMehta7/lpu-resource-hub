import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useAuth } from "@/features/auth/authContext";
import type { Role } from "@/features/auth/types";
import { toApiError } from "@/lib/api/errors";

import { changeUserRole, fetchUsers, setUserActive } from "./api";
import type { AdminUserRead } from "./types";

const ROLE_OPTIONS: Role[] = ["student", "faculty", "research_coordinator", "admin"];

const ROLE_LABELS: Record<Role, string> = {
  student: "Student",
  faculty: "Faculty",
  research_coordinator: "Coordinator",
  admin: "Admin",
};

type PendingAction =
  | { type: "role"; user: AdminUserRead; newRole: Role }
  | { type: "activate" | "deactivate"; user: AdminUserRead };

const USERS_QUERY_KEY = ["admin", "users"] as const;

export function AdminUsersPage() {
  const { user: currentUser } = useAuth();
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const { data, isPending, isError } = useQuery({
    queryKey: USERS_QUERY_KEY,
    queryFn: () => fetchUsers({ page_size: 100 }),
  });

  const invalidateUsers = () => queryClient.invalidateQueries({ queryKey: USERS_QUERY_KEY });

  const roleMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: Role }) => changeUserRole(userId, role),
    onSuccess: () => {
      setPending(null);
      void invalidateUsers();
    },
    onError: (error: unknown) => setActionError(toApiError(error).message),
  });

  const activeMutation = useMutation({
    mutationFn: ({ userId, isActive }: { userId: string; isActive: boolean }) =>
      setUserActive(userId, isActive),
    onSuccess: () => {
      setPending(null);
      void invalidateUsers();
    },
    onError: (error: unknown) => setActionError(toApiError(error).message),
  });

  const isMutating = roleMutation.isPending || activeMutation.isPending;

  const handleConfirm = () => {
    setActionError(null);
    if (!pending) return;
    if (pending.type === "role") {
      roleMutation.mutate({ userId: pending.user.id, role: pending.newRole });
    } else {
      activeMutation.mutate({
        userId: pending.user.id,
        isActive: pending.type === "activate",
      });
    }
  };

  if (isPending) {
    return <p className="text-sm text-ink-muted">Loading users…</p>;
  }

  if (isError) {
    return (
      <p role="alert" className="text-sm text-red-700">
        Could not load users.
      </p>
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Users</h1>
      <p className="mt-1 text-sm text-ink-muted">{data.total} accounts.</p>

      {actionError ? (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {actionError}
        </p>
      ) : null}

      <div className="mt-6 overflow-x-auto rounded-card border border-line bg-surface">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-line text-xs uppercase text-ink-muted">
            <tr>
              <th className="px-4 py-3 font-medium">Name</th>
              <th className="px-4 py-3 font-medium">Email</th>
              <th className="px-4 py-3 font-medium">Role</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {data.items.map((item) => {
              const isSelf = item.id === currentUser?.id;
              return (
                <tr key={item.id}>
                  <td className="px-4 py-3">{item.full_name}</td>
                  <td className="px-4 py-3 text-ink-muted">{item.email}</td>
                  <td className="px-4 py-3">
                    <select
                      aria-label={`Role for ${item.full_name}`}
                      value={item.role}
                      disabled={isSelf || isMutating}
                      onChange={(event) => {
                        const newRole = event.target.value as Role;
                        if (newRole !== item.role) {
                          setActionError(null);
                          setPending({ type: "role", user: item, newRole });
                        }
                      }}
                      className="rounded-md border border-line bg-surface px-2 py-1 text-sm disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {ROLE_OPTIONS.map((role) => (
                        <option key={role} value={role}>
                          {ROLE_LABELS[role]}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-4 py-3">{item.is_active ? "Active" : "Inactive"}</td>
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      disabled={isMutating}
                      onClick={() => {
                        setActionError(null);
                        setPending({
                          type: item.is_active ? "deactivate" : "activate",
                          user: item,
                        });
                      }}
                      className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm font-medium hover:bg-canvas disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {item.is_active ? "Deactivate" : "Activate"}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <ConfirmDialog
        open={pending !== null}
        title={pending ? _confirmTitle(pending) : ""}
        description={pending ? _confirmDescription(pending) : ""}
        isConfirming={isMutating}
        onConfirm={handleConfirm}
        onCancel={() => setPending(null)}
      />
    </div>
  );
}

function _confirmTitle(pending: PendingAction): string {
  switch (pending.type) {
    case "role":
      return "Change role?";
    case "activate":
      return "Activate account?";
    case "deactivate":
      return "Deactivate account?";
  }
}

function _confirmDescription(pending: PendingAction): string {
  switch (pending.type) {
    case "role":
      return `Change ${pending.user.full_name}'s role from ${ROLE_LABELS[pending.user.role]} to ${ROLE_LABELS[pending.newRole]}?`;
    case "activate":
      return `${pending.user.full_name} will be able to sign in again.`;
    case "deactivate":
      return `${pending.user.full_name} will be signed out everywhere and unable to sign in.`;
  }
}

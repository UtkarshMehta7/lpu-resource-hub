import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useAuth } from "@/features/auth/authContext";
import type { Role } from "@/features/auth/types";
import { fetchDepartments } from "@/features/directory/api-org";
import { toApiError } from "@/lib/api/errors";

import {
  changeUserRole,
  fetchUsers,
  resetTemporaryPassword,
  setUserActive,
  updateUser,
} from "./api";
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
  | { type: "activate" | "deactivate"; user: AdminUserRead }
  | { type: "reset"; user: AdminUserRead };

const USERS_QUERY_KEY = ["admin", "users"] as const;

const CONTROL =
  "rounded-md border border-line bg-surface px-2 py-1 text-sm disabled:cursor-not-allowed disabled:opacity-50";

export function AdminUsersPage() {
  const { user: currentUser } = useAuth();
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [editingName, setEditingName] = useState<{ id: string; value: string } | null>(null);
  const [issued, setIssued] = useState<{ name: string; password: string } | null>(null);
  const [copied, setCopied] = useState(false);

  const { data, isPending, isError } = useQuery({
    queryKey: USERS_QUERY_KEY,
    queryFn: () => fetchUsers({ page_size: 100 }),
  });
  const { data: departments } = useQuery({
    queryKey: ["departments"],
    queryFn: () => fetchDepartments(),
  });

  const invalidateUsers = () => queryClient.invalidateQueries({ queryKey: USERS_QUERY_KEY });
  const onMutationError = (error: unknown) => setActionError(toApiError(error).message);

  const roleMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: Role }) => changeUserRole(userId, role),
    onSuccess: () => {
      setPending(null);
      void invalidateUsers();
    },
    onError: onMutationError,
  });

  const activeMutation = useMutation({
    mutationFn: ({ userId, isActive }: { userId: string; isActive: boolean }) =>
      setUserActive(userId, isActive),
    onSuccess: () => {
      setPending(null);
      void invalidateUsers();
    },
    onError: onMutationError,
  });

  const detailsMutation = useMutation({
    mutationFn: ({
      userId,
      full_name,
      department_id,
    }: {
      userId: string;
      full_name?: string;
      department_id?: string | null;
    }) =>
      updateUser(userId, {
        ...(full_name ? { full_name } : {}),
        ...(department_id !== undefined ? { department_id } : {}),
      }),
    onSuccess: () => {
      setEditingName(null);
      void invalidateUsers();
    },
    onError: onMutationError,
  });

  const resetMutation = useMutation({
    mutationFn: (userId: string) => resetTemporaryPassword(userId),
    onSuccess: (result) => {
      setPending(null);
      setCopied(false);
      setIssued({ name: result.user.full_name, password: result.temporary_password });
      void invalidateUsers();
    },
    onError: onMutationError,
  });

  const isMutating =
    roleMutation.isPending ||
    activeMutation.isPending ||
    detailsMutation.isPending ||
    resetMutation.isPending;

  const handleConfirm = () => {
    setActionError(null);
    if (!pending) return;
    if (pending.type === "role") {
      roleMutation.mutate({ userId: pending.user.id, role: pending.newRole });
    } else if (pending.type === "reset") {
      resetMutation.mutate(pending.user.id);
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
      <p className="mt-1 text-sm text-ink-muted">
        {data.total} accounts. A person with no department can&apos;t use anything
        department-scoped, so place them here.
      </p>

      {actionError ? (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {actionError}
        </p>
      ) : null}

      {issued ? (
        <div className="mt-4 rounded-card border border-brand-200 bg-brand-50 p-4">
          <h2 className="text-sm font-semibold">New temporary password for {issued.name}</h2>
          <p className="mt-1 text-sm">
            Their old password no longer works and they have been signed out everywhere.
            They&apos;ll choose a new password at their next sign-in.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <code className="rounded-md border border-line bg-surface px-3 py-2 font-mono text-sm">
              {issued.password}
            </code>
            <button
              type="button"
              onClick={() => {
                void navigator.clipboard?.writeText(issued.password);
                setCopied(true);
              }}
              className="rounded-md border border-line bg-surface px-3 py-2 text-sm font-medium"
            >
              {copied ? "Copied" : "Copy"}
            </button>
            <button
              type="button"
              onClick={() => setIssued(null)}
              className="text-sm font-medium text-ink-muted hover:underline"
            >
              Dismiss
            </button>
          </div>
          <p className="mt-2 text-xs text-ink-muted">This is shown once.</p>
        </div>
      ) : null}

      <div className="mt-6 overflow-x-auto rounded-card border border-line bg-surface">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-line text-xs uppercase text-ink-muted">
            <tr>
              <th className="px-4 py-3 font-medium">Name</th>
              <th className="px-4 py-3 font-medium">Department</th>
              <th className="px-4 py-3 font-medium">Role</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {data.items.map((item) => {
              const isSelf = item.id === currentUser?.id;
              const isEditing = editingName?.id === item.id;
              return (
                <tr key={item.id}>
                  <td className="px-4 py-3">
                    {isEditing ? (
                      <form
                        onSubmit={(event) => {
                          event.preventDefault();
                          setActionError(null);
                          const value = editingName.value.trim();
                          if (!value || value === item.full_name) {
                            setEditingName(null);
                            return;
                          }
                          detailsMutation.mutate({ userId: item.id, full_name: value });
                        }}
                        className="flex flex-wrap items-center gap-2"
                      >
                        <label className="sr-only" htmlFor={`name-${item.id}`}>
                          Name for {item.full_name}
                        </label>
                        <input
                          id={`name-${item.id}`}
                          autoFocus
                          value={editingName.value}
                          onChange={(event) =>
                            setEditingName({ id: item.id, value: event.target.value })
                          }
                          className={CONTROL}
                        />
                        <button
                          type="submit"
                          disabled={isMutating}
                          className="rounded-md bg-brand-700 px-2 py-1 text-xs font-medium text-white disabled:opacity-50"
                        >
                          Save
                        </button>
                        <button
                          type="button"
                          onClick={() => setEditingName(null)}
                          className="text-xs font-medium text-ink-muted hover:underline"
                        >
                          Cancel
                        </button>
                      </form>
                    ) : (
                      <button
                        type="button"
                        onClick={() => setEditingName({ id: item.id, value: item.full_name })}
                        className="text-left hover:underline"
                        aria-label={`Rename ${item.full_name}`}
                      >
                        {item.full_name}
                      </button>
                    )}
                    <span className="block text-xs text-ink-muted">{item.email ?? "—"}</span>
                  </td>
                  <td className="px-4 py-3">
                    <select
                      aria-label={`Department for ${item.full_name}`}
                      value={item.department_id ?? ""}
                      disabled={isMutating}
                      onChange={(event) => {
                        setActionError(null);
                        detailsMutation.mutate({
                          userId: item.id,
                          department_id: event.target.value || null,
                        });
                      }}
                      className={CONTROL}
                    >
                      <option value="">No department</option>
                      {departments?.map((department) => (
                        <option key={department.id} value={department.id}>
                          {department.name}
                        </option>
                      ))}
                    </select>
                  </td>
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
                      className={CONTROL}
                    >
                      {ROLE_OPTIONS.map((role) => (
                        <option key={role} value={role}>
                          {ROLE_LABELS[role]}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-4 py-3">
                    {item.is_active ? "Active" : "Inactive"}
                    {item.must_change_password ? (
                      <span className="block text-xs text-ink-muted">password not set yet</span>
                    ) : null}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-2">
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
                      <button
                        type="button"
                        disabled={isSelf || isMutating}
                        onClick={() => {
                          setActionError(null);
                          setPending({ type: "reset", user: item });
                        }}
                        className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm font-medium hover:bg-canvas disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        New password
                      </button>
                    </div>
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
    case "reset":
      return "Issue a new temporary password?";
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
    case "reset":
      return `${pending.user.full_name}'s current password will stop working and they will be signed out everywhere. You'll see the new one once.`;
  }
}

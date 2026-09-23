import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useAuth } from "@/features/auth/authContext";
import type { Role } from "@/features/auth/types";
import { toApiError } from "@/lib/api/errors";

import { confirmAdminPromotion, fetchUsers, requestAdminPromotion, stepDownAsAdmin } from "./api";
import type { AdminUserRead } from "./types";

/**
 * Handing the platform over.
 *
 * Making another administrator is the one action where holding an admin
 * session shouldn't be enough on its own, so it takes two people: the code
 * goes to the person being promoted, and only they can pass it back. This
 * page is the requester's half of that — it never sees the code, it asks for
 * it.
 */
const STEP_DOWN_ROLES: Role[] = ["faculty", "research_coordinator", "student"];

const ROLE_LABELS: Record<Role, string> = {
  student: "Student",
  faculty: "Faculty",
  research_coordinator: "Research coordinator",
  admin: "Administrator",
};

export function AdminHandoverPage() {
  const { user: currentUser } = useAuth();
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<AdminUserRead | null>(null);
  const [code, setCode] = useState("");
  const [expiresAt, setExpiresAt] = useState<string | null>(null);
  const [promoted, setPromoted] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stepDownTo, setStepDownTo] = useState<Role>("faculty");
  const [confirmStepDown, setConfirmStepDown] = useState(false);

  const { data: candidates } = useQuery({
    queryKey: ["admin", "users", "promotable"],
    queryFn: () => fetchUsers({ page_size: 100 }),
    select: (page) => page.items.filter((item) => item.role !== "admin" && item.is_active),
  });
  const { data: admins } = useQuery({
    queryKey: ["admin", "users", "count", "admin"],
    queryFn: () => fetchUsers({ role: "admin", page_size: 1 }),
    select: (page) => page.total,
  });

  const onError = (caught: unknown) => setError(toApiError(caught).message);

  const requestMutation = useMutation({
    mutationFn: (userId: string) => requestAdminPromotion(userId),
    onSuccess: (challenge) => {
      setExpiresAt(challenge.expires_at);
      setCode("");
      setPromoted(null);
    },
    onError,
  });

  const confirmMutation = useMutation({
    mutationFn: ({ userId, value }: { userId: string; value: string }) =>
      confirmAdminPromotion(userId, value),
    onSuccess: async (user) => {
      setPromoted(user.full_name);
      setExpiresAt(null);
      setSelected(null);
      setCode("");
      await queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
    onError,
  });

  const stepDownMutation = useMutation({
    mutationFn: (role: Role) => stepDownAsAdmin(role),
    onSuccess: () => {
      // Their own role just changed, so a reload is the honest thing: the
      // whole navigation is about to be different.
      window.location.assign("/dashboard");
    },
    onError: (caught: unknown) => {
      setConfirmStepDown(false);
      onError(caught);
    },
  });

  const canStepDown = (admins ?? 0) > 1;

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-2xl font-semibold tracking-tight">Administrators</h1>
      <p className="mt-1 text-sm text-ink-muted">
        Promoting someone takes both of you: the code goes to them, and you finish it with what they
        read back.
      </p>

      {error ? (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {error}
        </p>
      ) : null}

      {promoted ? (
        <p className="mt-4 rounded-card border border-brand-200 bg-brand-50 p-4 text-sm">
          <strong className="font-semibold">{promoted}</strong> is now an administrator, with every
          power you have.
        </p>
      ) : null}

      <section className="mt-6 rounded-card border border-line bg-surface p-5">
        <h2 className="text-sm font-semibold">Make someone an administrator</h2>

        <ol className="mt-4 space-y-4 text-sm">
          <li>
            <span className="font-medium">1. Choose the person.</span>
            <label className="sr-only" htmlFor="promote-target">
              Person to promote
            </label>
            <select
              id="promote-target"
              value={selected?.id ?? ""}
              onChange={(event) => {
                setError(null);
                setExpiresAt(null);
                setSelected(candidates?.find((item) => item.id === event.target.value) ?? null);
              }}
              className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm"
            >
              <option value="">Choose someone…</option>
              {candidates?.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.full_name} · {ROLE_LABELS[item.role]} · {item.registration_number}
                </option>
              ))}
            </select>
          </li>

          <li>
            <span className="font-medium">2. Send them a code.</span>
            <p className="text-ink-muted">
              A six-digit code lands in their notifications. You never see it — ask them for it.
            </p>
            <button
              type="button"
              disabled={!selected || requestMutation.isPending}
              onClick={() => {
                setError(null);
                if (selected) requestMutation.mutate(selected.id);
              }}
              className="mt-2 rounded-md bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {requestMutation.isPending ? "Sending…" : "Send code"}
            </button>
            {expiresAt ? (
              <p className="mt-2 text-xs text-ink-muted">
                Sent. It expires at {new Date(expiresAt).toLocaleTimeString()} and works once.
              </p>
            ) : null}
          </li>

          <li>
            <span className="font-medium">3. Enter what they read back.</span>
            <form
              className="mt-2 flex flex-wrap gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                setError(null);
                if (selected && code.trim()) {
                  confirmMutation.mutate({ userId: selected.id, value: code.trim() });
                }
              }}
            >
              <label className="sr-only" htmlFor="promote-code">
                Confirmation code
              </label>
              <input
                id="promote-code"
                value={code}
                onChange={(event) => setCode(event.target.value)}
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder="000000"
                className="w-32 rounded-md border border-line bg-surface px-3 py-2 font-mono text-sm tracking-widest"
              />
              <button
                type="submit"
                disabled={!selected || !code.trim() || confirmMutation.isPending}
                className="rounded-md border border-line bg-surface px-3 py-2 text-sm font-medium hover:bg-canvas disabled:cursor-not-allowed disabled:opacity-50"
              >
                {confirmMutation.isPending ? "Confirming…" : "Promote"}
              </button>
            </form>
            <p className="mt-2 text-xs text-ink-muted">
              Five wrong codes end the attempt; sending a new code starts over.
            </p>
          </li>
        </ol>
      </section>

      <section className="mt-6 rounded-card border border-line bg-surface p-5">
        <h2 className="text-sm font-semibold">Step down</h2>
        <p className="mt-1 text-sm text-ink-muted">
          Give up your own administrator role. Only possible once somebody else holds it — the
          platform is never left without one.
        </p>

        {canStepDown ? (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <label className="sr-only" htmlFor="step-down-role">
              Role to keep
            </label>
            <select
              id="step-down-role"
              value={stepDownTo}
              onChange={(event) => setStepDownTo(event.target.value as Role)}
              className="rounded-md border border-line bg-surface px-3 py-2 text-sm"
            >
              {STEP_DOWN_ROLES.map((role) => (
                <option key={role} value={role}>
                  Stay on as {ROLE_LABELS[role].toLowerCase()}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => {
                setError(null);
                setConfirmStepDown(true);
              }}
              className="rounded-md border border-line bg-surface px-3 py-2 text-sm font-medium hover:bg-canvas"
            >
              Step down
            </button>
          </div>
        ) : (
          <p className="mt-3 text-sm text-ink-muted">
            You are the only administrator. Promote someone first.
          </p>
        )}
      </section>

      <ConfirmDialog
        open={confirmStepDown}
        title="Give up administrator?"
        description={`${currentUser?.full_name ?? "You"} will become a ${ROLE_LABELS[
          stepDownTo
        ].toLowerCase()} immediately, and lose every administration page. Another administrator would have to promote you back.`}
        isConfirming={stepDownMutation.isPending}
        onConfirm={() => stepDownMutation.mutate(stepDownTo)}
        onCancel={() => setConfirmStepDown(false)}
      />
    </div>
  );
}

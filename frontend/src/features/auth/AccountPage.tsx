import { useQuery } from "@tanstack/react-query";

import { fetchCurrentUser } from "./api";
import { ChangePasswordForm } from "./ChangePasswordForm";

const ROLE_LABELS: Record<string, string> = {
  student: "Student",
  faculty: "Faculty / researcher",
  research_coordinator: "Research coordinator",
  admin: "Administrator",
};

export function AccountPage() {
  const { data, isPending, isError, error } = useQuery({
    queryKey: ["users", "me"],
    queryFn: fetchCurrentUser,
  });

  if (isPending) {
    return <p className="text-sm text-ink-muted">Loading your profile…</p>;
  }

  if (isError) {
    return (
      <p role="alert" className="text-sm text-red-700">
        {error instanceof Error ? error.message : "Could not load your profile."}
      </p>
    );
  }

  return (
    <div className="max-w-xl">
      <h1 className="text-2xl font-semibold tracking-tight">Your account</h1>
      <dl className="mt-6 divide-y divide-line rounded-card border border-line bg-surface">
        <div className="flex justify-between gap-4 px-4 py-3">
          <dt className="text-sm text-ink-muted">Name</dt>
          <dd className="text-sm font-medium">{data.full_name}</dd>
        </div>
        <div className="flex justify-between gap-4 px-4 py-3">
          <dt className="text-sm text-ink-muted">Email</dt>
          <dd className="text-sm font-medium">{data.email}</dd>
        </div>
        <div className="flex justify-between gap-4 px-4 py-3">
          <dt className="text-sm text-ink-muted">Role</dt>
          <dd className="text-sm font-medium">{ROLE_LABELS[data.role] ?? data.role}</dd>
        </div>
        <div className="flex justify-between gap-4 px-4 py-3">
          <dt className="text-sm text-ink-muted">Member since</dt>
          <dd className="text-sm font-medium">{new Date(data.created_at).toLocaleDateString()}</dd>
        </div>
      </dl>

      <section className="mt-10">
        <h2 className="text-base font-semibold">Change password</h2>
        <p className="mt-1 text-sm text-ink-muted">
          Changing your password signs you out of every device.
        </p>
        <div className="mt-4">
          <ChangePasswordForm />
        </div>
      </section>
    </div>
  );
}

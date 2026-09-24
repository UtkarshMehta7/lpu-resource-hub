import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { SkeletonList } from "@/components/ui/Skeleton";
import { toApiError } from "@/lib/api/errors";

import { fetchMyApplications, withdrawApplication } from "./api";
import { APPLICATION_STATUS_LABEL, TYPE_LABEL, WITHDRAWABLE } from "./labels";
import { StatusTimeline } from "./StatusTimeline";

export function MyApplicationsPage() {
  const queryClient = useQueryClient();
  const [withdrawing, setWithdrawing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data, isPending, isError } = useQuery({
    queryKey: ["my-applications"],
    queryFn: fetchMyApplications,
  });

  const withdraw = useMutation({
    mutationFn: (id: string) => withdrawApplication(id),
    onSuccess: async () => {
      setWithdrawing(null);
      await queryClient.invalidateQueries({ queryKey: ["my-applications"] });
    },
    onError: (caught) => {
      setWithdrawing(null);
      setError(toApiError(caught).message);
    },
  });

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">My applications</h1>
      {error ? (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {error}
        </p>
      ) : null}
      {isPending ? (
        <div className="mt-6">
          <SkeletonList rows={3} />
        </div>
      ) : null}
      {isError ? (
        <p role="alert" className="mt-6 text-sm text-red-700">
          Could not load your applications.
        </p>
      ) : null}
      {data && data.length === 0 ? (
        <p className="mt-6 text-sm text-ink-muted">
          You haven&apos;t applied to anything yet.{" "}
          <Link to="/opportunities" className="text-brand-700 hover:underline">
            Browse opportunities
          </Link>
        </p>
      ) : null}
      <ul className="mt-6 space-y-4">
        {data?.map((application) => (
          <li key={application.id} className="rounded-card border border-line bg-surface p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <Link
                to={`/opportunities/${application.opportunity_id}`}
                className="text-sm font-semibold hover:underline"
              >
                {application.opportunity_title}
              </Link>
              <span className="rounded-md border border-line px-2 py-1 text-xs">
                {APPLICATION_STATUS_LABEL[application.status]}
              </span>
            </div>
            <p className="text-xs text-ink-muted">{TYPE_LABEL[application.opportunity_type]}</p>
            <StatusTimeline events={application.events} />
            {WITHDRAWABLE.has(application.status) ? (
              <button
                type="button"
                onClick={() => setWithdrawing(application.id)}
                className="mt-3 text-xs text-red-700 hover:underline"
              >
                Withdraw
              </button>
            ) : null}
          </li>
        ))}
      </ul>
      <ConfirmDialog
        open={withdrawing !== null}
        title="Withdraw application?"
        description="You can't apply to the same opportunity again."
        confirmLabel="Withdraw"
        isConfirming={withdraw.isPending}
        onConfirm={() => {
          if (withdrawing) withdraw.mutate(withdrawing);
        }}
        onCancel={() => setWithdrawing(null)}
      />
    </div>
  );
}

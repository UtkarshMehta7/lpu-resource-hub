import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Uid } from "@/components/ui/Uid";
import { ReportButton } from "@/features/reports/ReportButton";
import { SaveButton } from "@/features/saved/SaveButton";
import { useAuth } from "@/features/auth/authContext";
import { toApiError } from "@/lib/api/errors";

import { fetchOpportunity, runOpportunityAction } from "./api";
import { ApplyForm } from "./ApplyForm";
import { canApplyAs, OPPORTUNITY_STATUS_LABEL, TYPE_LABEL } from "./labels";

type PendingAction = "publish" | "close";

const COPY: Record<PendingAction, { title: string; body: string }> = {
  publish: {
    title: "Publish this opportunity?",
    body: "It becomes visible on the board and people can apply until the deadline.",
  },
  close: {
    title: "Close this opportunity?",
    body: "No new applications will be accepted. Existing ones can still be decided.",
  },
};

export function OpportunityDetailPage() {
  const { opportunityId = "" } = useParams<{ opportunityId: string }>();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [error, setError] = useState<string | null>(null);

  const {
    data: opportunity,
    isPending,
    isError,
  } = useQuery({
    queryKey: ["opportunity", opportunityId],
    queryFn: () => fetchOpportunity(opportunityId),
  });

  const action = useMutation({
    mutationFn: (which: PendingAction) => runOpportunityAction(opportunityId, which),
    onSuccess: async () => {
      setPending(null);
      await queryClient.invalidateQueries({ queryKey: ["opportunity", opportunityId] });
      await queryClient.invalidateQueries({ queryKey: ["opportunities"] });
    },
    onError: (caught) => {
      setPending(null);
      setError(toApiError(caught).message);
    },
  });

  if (isPending) return <p className="text-sm text-ink-muted">Loading…</p>;
  if (isError) {
    return (
      <p role="alert" className="text-sm text-red-700">
        Opportunity not found.
      </p>
    );
  }

  const isOwner = user?.id === opportunity.created_by;
  const deadlinePassed = opportunity.deadline < new Date().toISOString().slice(0, 10);
  const canApply =
    !!user &&
    !isOwner &&
    opportunity.status === "open" &&
    !deadlinePassed &&
    opportunity.my_application_id === null &&
    canApplyAs(user.role, opportunity.opportunity_type);

  return (
    <div className="mx-auto max-w-3xl">
      <p className="text-xs text-ink-muted">
        {TYPE_LABEL[opportunity.opportunity_type]} · {OPPORTUNITY_STATUS_LABEL[opportunity.status]}
      </p>
      <h1 className="mt-1 text-2xl font-semibold tracking-tight">{opportunity.title}</h1>
      <p className="mt-2 text-sm text-ink-muted">
        Posted by {opportunity.creator_name} <Uid value={opportunity.creator_registration_number} />
        {opportunity.project_id && opportunity.project_title ? (
          <>
            {" "}
            on{" "}
            <Link
              to={`/projects/${opportunity.project_id}`}
              className="text-brand-700 hover:underline"
            >
              {opportunity.project_title}
            </Link>
          </>
        ) : null}{" "}
        · Deadline {opportunity.deadline} · {opportunity.accepted_count}/{opportunity.positions}{" "}
        positions filled
      </p>

      {error ? (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {error}
        </p>
      ) : null}

      {!isOwner ? (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <SaveButton type="opportunity" targetId={opportunity.id} />
          <ReportButton targetType="opportunity" targetId={opportunity.id} />
        </div>
      ) : null}

      {isOwner ? (
        <div className="mt-4 flex flex-wrap gap-2">
          <Link
            to={`/opportunities/${opportunity.id}/applicants`}
            className="rounded-md bg-brand-700 px-3 py-1.5 text-sm font-medium text-white"
          >
            Review applicants
          </Link>
          {opportunity.status === "draft" || opportunity.status === "open" ? (
            <Link
              to={`/opportunities/${opportunity.id}/edit`}
              className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm"
            >
              Edit
            </Link>
          ) : null}
          {opportunity.status === "draft" ? (
            <button
              type="button"
              onClick={() => setPending("publish")}
              className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm"
            >
              Publish
            </button>
          ) : null}
          {opportunity.status === "draft" || opportunity.status === "open" ? (
            <button
              type="button"
              onClick={() => setPending("close")}
              className="rounded-md border border-red-300 px-3 py-1.5 text-sm text-red-700"
            >
              Close
            </button>
          ) : null}
        </div>
      ) : null}

      <section className="mt-8">
        <h2 className="text-base font-semibold">Description</h2>
        <p className="mt-2 whitespace-pre-line text-sm">{opportunity.description}</p>
      </section>
      {opportunity.eligibility ? (
        <section className="mt-6">
          <h2 className="text-base font-semibold">Eligibility</h2>
          <p className="mt-2 whitespace-pre-line text-sm">{opportunity.eligibility}</p>
        </section>
      ) : null}
      {opportunity.skills.length > 0 ? (
        <section className="mt-6">
          <h2 className="text-base font-semibold">Skills</h2>
          <ul className="mt-2 flex flex-wrap gap-2">
            {opportunity.skills.map((s) => (
              <li key={s.id} className="rounded-md border border-line px-2 py-1 text-xs">
                {s.name}
                {s.is_required ? "" : " (nice to have)"}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="mt-8">
        {opportunity.my_application_id ? (
          <p className="text-sm">
            You&apos;ve applied.{" "}
            <Link to="/me/applications" className="text-brand-700 hover:underline">
              Track your application
            </Link>
          </p>
        ) : canApply ? (
          <>
            <h2 className="text-base font-semibold">Apply</h2>
            <ApplyForm opportunityId={opportunity.id} />
          </>
        ) : !isOwner && opportunity.status === "open" && !deadlinePassed ? (
          <p className="text-sm text-ink-muted">
            {user?.role === "student"
              ? "This opening is for faculty collaborators."
              : "This opening is for students."}
          </p>
        ) : null}
      </section>

      <ConfirmDialog
        open={pending !== null}
        title={pending ? COPY[pending].title : ""}
        description={pending ? COPY[pending].body : ""}
        confirmLabel={pending === "close" ? "Close" : "Publish"}
        isConfirming={action.isPending}
        onConfirm={() => {
          if (pending) action.mutate(pending);
        }}
        onCancel={() => setPending(null)}
      />
    </div>
  );
}

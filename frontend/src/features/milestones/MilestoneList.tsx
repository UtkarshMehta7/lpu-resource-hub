import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { SkeletonList } from "@/components/ui/Skeleton";
import { StatusPill } from "@/components/ui/StatusPill";
import { toApiError } from "@/lib/api/errors";

import { changeMilestoneStatus, deleteMilestone, fetchMilestones, removeDependency } from "./api";
import { MilestoneFormDialog } from "./MilestoneFormDialog";
import { MilestoneTimeline } from "./MilestoneTimeline";
import { RISK_LABELS, RISK_TONES, STATUS_LABELS, describeDue, formatDate } from "./labels";
import type { Milestone, MilestoneStatus } from "./types";

/**
 * The plan for a project: a timeline on wide screens, always a list.
 *
 * The list is not a lesser fallback -- it is where dependencies are stated in
 * words ("waits on X"), which a chart can only imply, and it is the whole of
 * the feature on a phone.
 */

export function milestoneQueryKey(projectId: string) {
  return ["milestones", projectId] as const;
}

/** What a given viewer may do, decided by the backend and mirrored here. */
interface Abilities {
  canPlan: boolean;
  canMove: boolean;
}

export function MilestoneSection({
  projectId,
  canPlan,
  canMove,
}: { projectId: string } & Abilities) {
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<Milestone | null>(null);
  const [removing, setRemoving] = useState<Milestone | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: milestones, isPending } = useQuery({
    queryKey: milestoneQueryKey(projectId),
    queryFn: () => fetchMilestones(projectId),
  });

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: milestoneQueryKey(projectId) });
  };

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: MilestoneStatus }) =>
      changeMilestoneStatus(id, status),
    onSuccess: async () => {
      setError(null);
      await invalidate();
    },
    onError: (err: unknown) => setError(toApiError(err).message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteMilestone(id),
    onSuccess: async () => {
      setRemoving(null);
      setError(null);
      await invalidate();
    },
    onError: (err: unknown) => {
      setRemoving(null);
      setError(toApiError(err).message);
    },
  });

  const unlinkMutation = useMutation({
    mutationFn: ({ id, dependsOnId }: { id: string; dependsOnId: string }) =>
      removeDependency(id, dependsOnId),
    onSuccess: invalidate,
    onError: (err: unknown) => setError(toApiError(err).message),
  });

  return (
    <section className="mt-8">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-base font-semibold">Milestones</h2>
        {canPlan ? (
          <Button size="sm" onClick={() => setAdding(true)}>
            Add milestone
          </Button>
        ) : null}
      </div>

      {error ? (
        <p role="alert" className="mt-2 text-sm text-red-700">
          {error}
        </p>
      ) : null}

      {isPending ? (
        <div className="mt-3">
          <SkeletonList rows={3} />
        </div>
      ) : !milestones || milestones.length === 0 ? (
        <p className="mt-2 text-sm text-ink-muted">
          {canPlan
            ? "No milestones yet. Add the first one to start tracking progress."
            : "This project has no milestones yet."}
        </p>
      ) : (
        <>
          <div className="mt-4">
            <MilestoneTimeline milestones={milestones} />
          </div>
          <ul className="mt-4 space-y-2">
            {milestones.map((milestone) => (
              <MilestoneRow
                key={milestone.id}
                milestone={milestone}
                canPlan={canPlan}
                canMove={canMove}
                busy={statusMutation.isPending}
                onStatus={(status) => statusMutation.mutate({ id: milestone.id, status })}
                onEdit={() => setEditing(milestone)}
                onDelete={() => setRemoving(milestone)}
                onUnlink={(dependsOnId) => unlinkMutation.mutate({ id: milestone.id, dependsOnId })}
              />
            ))}
          </ul>
        </>
      )}

      {adding ? (
        <MilestoneFormDialog
          projectId={projectId}
          siblings={milestones ?? []}
          onClose={() => setAdding(false)}
          onSaved={invalidate}
        />
      ) : null}
      {editing ? (
        <MilestoneFormDialog
          projectId={projectId}
          milestone={editing}
          siblings={milestones ?? []}
          onClose={() => setEditing(null)}
          onSaved={invalidate}
        />
      ) : null}
      {removing ? (
        <ConfirmDialog
          open
          isConfirming={deleteMutation.isPending}
          title="Delete this milestone?"
          description={`"${removing.title}" will be removed from the plan. This cannot be undone.`}
          confirmLabel="Delete"
          onConfirm={() => deleteMutation.mutate(removing.id)}
          onCancel={() => setRemoving(null)}
        />
      ) : null}
    </section>
  );
}

function MilestoneRow({
  milestone,
  canPlan,
  canMove,
  busy,
  onStatus,
  onEdit,
  onDelete,
  onUnlink,
}: {
  milestone: Milestone;
  canPlan: boolean;
  canMove: boolean;
  busy: boolean;
  onStatus: (status: MilestoneStatus) => void;
  onEdit: () => void;
  onDelete: () => void;
  onUnlink: (dependsOnId: string) => void;
}) {
  const settled = milestone.status === "done" || milestone.status === "cancelled";
  return (
    <li className="rounded-card border border-line bg-surface p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="flex flex-wrap items-baseline gap-2">
          <span className="font-medium">{milestone.title}</span>
          <StatusPill tone="neutral">{STATUS_LABELS[milestone.status]}</StatusPill>
          {milestone.risk !== "none" ? (
            <StatusPill tone={RISK_TONES[milestone.risk]}>{RISK_LABELS[milestone.risk]}</StatusPill>
          ) : null}
        </span>
        <span className="text-xs text-ink-muted">
          {formatDate(milestone.due_date)}
          {settled ? null : ` · ${describeDue(milestone.days_until_due)}`}
        </span>
      </div>

      {milestone.description ? (
        <p className="mt-1 text-sm text-ink-muted">{milestone.description}</p>
      ) : null}

      {milestone.depends_on.length > 0 ? (
        <p className="mt-1.5 text-xs text-ink-muted">
          waits on{" "}
          {milestone.depends_on.map((dependency, index) => (
            <span key={dependency.id}>
              {index > 0 ? ", " : ""}
              <span
                className={
                  milestone.blocked_by.some((b) => b.id === dependency.id)
                    ? "font-medium text-red-700"
                    : ""
                }
              >
                {dependency.title}
              </span>
              {canPlan ? (
                <button
                  type="button"
                  onClick={() => onUnlink(dependency.id)}
                  className="ml-1 text-ink-muted underline hover:text-ink"
                  aria-label={`Stop ${milestone.title} waiting on ${dependency.title}`}
                >
                  remove
                </button>
              ) : null}
            </span>
          ))}
        </p>
      ) : null}

      <div className="mt-2 flex flex-wrap gap-2">
        {canMove && milestone.status === "pending" ? (
          <Button
            size="sm"
            variant="secondary"
            disabled={busy}
            onClick={() => onStatus("in_progress")}
          >
            Start
          </Button>
        ) : null}
        {canMove && (milestone.status === "pending" || milestone.status === "in_progress") ? (
          <Button size="sm" variant="secondary" disabled={busy} onClick={() => onStatus("done")}>
            Mark done
          </Button>
        ) : null}
        {canPlan && milestone.status === "done" ? (
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => onStatus("in_progress")}>
            Reopen
          </Button>
        ) : null}
        {canPlan && !settled ? (
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => onStatus("cancelled")}>
            Cancel
          </Button>
        ) : null}
        {canPlan ? (
          <>
            <Button size="sm" variant="ghost" onClick={onEdit}>
              Edit
            </Button>
            <Button size="sm" variant="danger" onClick={onDelete}>
              Delete
            </Button>
          </>
        ) : null}
      </div>
    </li>
  );
}

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { toApiError } from "@/lib/api/errors";

import { fetchReviewQueue, reviewProject, type ProjectCard } from "./api";

interface Pending {
  project: ProjectCard;
  decision: "approve" | "reject";
}

/** Coordinator/admin: projects awaiting review in the reviewer's scope. */
export function ReviewQueuePage() {
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<Pending | null>(null);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data, isPending, isError } = useQuery({
    queryKey: ["review-queue"],
    queryFn: fetchReviewQueue,
  });

  const mutation = useMutation({
    mutationFn: ({ project, decision }: Pending) =>
      reviewProject(project.id, decision, comment || undefined),
    onSuccess: async () => {
      setPending(null);
      setComment("");
      setError(null);
      await queryClient.invalidateQueries({ queryKey: ["review-queue"] });
    },
    onError: (caught: unknown) => setError(toApiError(caught).message),
  });

  if (isPending) return <p className="text-sm text-ink-muted">Loading the review queue…</p>;
  if (isError) {
    return (
      <p role="alert" className="text-sm text-red-700">
        Could not load the review queue.
      </p>
    );
  }

  const rejecting = pending?.decision === "reject";

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Project review queue</h1>
      <p className="mt-1 text-sm text-ink-muted">
        Projects submitted for review in your scope. {data.length} pending. You can never review
        your own project.
      </p>

      {error ? (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {error}
        </p>
      ) : null}

      {data.length === 0 ? (
        <p className="mt-6 rounded-card border border-line bg-surface px-4 py-6 text-sm text-ink-muted">
          Nothing to review right now.
        </p>
      ) : (
        <ul className="mt-6 space-y-3">
          {data.map((project) => (
            <li key={project.id} className="rounded-card border border-line bg-surface p-4">
              <Link
                to={`/projects/${project.id}`}
                className="text-sm font-semibold hover:underline"
              >
                {project.title}
              </Link>
              <p className="mt-1 text-sm text-ink-muted">{project.summary}</p>
              <p className="mt-1 text-xs text-ink-muted">Led by {project.owner_name}</p>
              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  onClick={() => setPending({ project, decision: "approve" })}
                  className="rounded-md bg-brand-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-800"
                >
                  Approve
                </button>
                <button
                  type="button"
                  onClick={() => setPending({ project, decision: "reject" })}
                  className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm font-medium hover:bg-canvas"
                >
                  Request changes
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <ConfirmDialog
        open={pending !== null}
        title={rejecting ? "Send back for changes?" : "Approve this project?"}
        description={
          rejecting
            ? "The project returns to draft with your comment. A comment is required."
            : "The project becomes active and visible to everyone."
        }
        confirmLabel={rejecting ? "Send back" : "Approve"}
        isConfirming={mutation.isPending}
        onConfirm={() => {
          if (!pending) return;
          if (rejecting && !comment.trim()) {
            setError("Please explain what needs to change.");
            return;
          }
          mutation.mutate(pending);
        }}
        onCancel={() => setPending(null)}
      >
        <label htmlFor="review-comment" className="block text-sm font-medium">
          Comment {rejecting ? "(required)" : "(optional)"}
        </label>
        <textarea
          id="review-comment"
          rows={3}
          value={comment}
          onChange={(event) => setComment(event.target.value)}
          className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm"
        />
      </ConfirmDialog>
    </div>
  );
}

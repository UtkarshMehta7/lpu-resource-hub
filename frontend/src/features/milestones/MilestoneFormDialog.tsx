import { useMutation } from "@tanstack/react-query";
import { useId, useState } from "react";

import { Button } from "@/components/ui/Button";
import { toApiError } from "@/lib/api/errors";

import { addDependency, createMilestone, updateMilestone } from "./api";
import type { Milestone } from "./types";

/**
 * Add or edit one milestone.
 *
 * Dependencies are offered only on an existing milestone: a new one has no id
 * to hang an edge on yet, and adding it first then linking is one fewer thing
 * that can half-fail.
 */
export function MilestoneFormDialog({
  projectId,
  milestone,
  siblings,
  onClose,
  onSaved,
}: {
  projectId: string;
  milestone?: Milestone;
  siblings: Milestone[];
  onClose: () => void;
  onSaved: () => Promise<void> | void;
}) {
  const titleId = useId();
  const dueId = useId();
  const descriptionId = useId();
  const dependsId = useId();

  const [title, setTitle] = useState(milestone?.title ?? "");
  const [dueDate, setDueDate] = useState(milestone?.due_date ?? "");
  const [description, setDescription] = useState(milestone?.description ?? "");
  const [dependsOn, setDependsOn] = useState("");
  const [error, setError] = useState<string | null>(null);

  const editing = milestone !== undefined;
  // A milestone may not wait on itself, and the backend refuses cycles; this
  // only trims the obvious case so the common mistake never reaches it.
  const candidates = siblings.filter(
    (candidate) =>
      candidate.id !== milestone?.id &&
      !milestone?.depends_on.some((existing) => existing.id === candidate.id),
  );

  const save = useMutation({
    mutationFn: async () => {
      const payload = {
        title: title.trim(),
        due_date: dueDate,
        description: description.trim() === "" ? null : description.trim(),
      };
      const saved = editing
        ? await updateMilestone(milestone.id, payload)
        : await createMilestone(projectId, payload);
      if (dependsOn !== "") await addDependency(saved.id, dependsOn);
      return saved;
    },
    onSuccess: async () => {
      await onSaved();
      onClose();
    },
    onError: (err: unknown) => setError(toApiError(err).message),
  });

  const valid = title.trim() !== "" && dueDate !== "";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-label={editing ? "Edit milestone" : "Add milestone"}
        className="w-full max-w-md rounded-card border border-line bg-surface p-4 shadow-lg"
      >
        <h2 className="text-base font-semibold">{editing ? "Edit milestone" : "Add milestone"}</h2>

        <div className="mt-3 space-y-3">
          <div>
            <label htmlFor={titleId} className="text-sm font-medium">
              Title
            </label>
            <input
              id={titleId}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              maxLength={200}
              className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm"
            />
          </div>

          <div>
            <label htmlFor={dueId} className="text-sm font-medium">
              Due date
            </label>
            <input
              id={dueId}
              type="date"
              value={dueDate}
              onChange={(event) => setDueDate(event.target.value)}
              className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm"
            />
          </div>

          <div>
            <label htmlFor={descriptionId} className="text-sm font-medium">
              Description <span className="font-normal text-ink-muted">(optional)</span>
            </label>
            <textarea
              id={descriptionId}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              rows={3}
              maxLength={10000}
              className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm"
            />
          </div>

          {editing && candidates.length > 0 ? (
            <div>
              <label htmlFor={dependsId} className="text-sm font-medium">
                Waits on <span className="font-normal text-ink-muted">(optional)</span>
              </label>
              <select
                id={dependsId}
                value={dependsOn}
                onChange={(event) => setDependsOn(event.target.value)}
                className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm"
              >
                <option value="">Nothing</option>
                {candidates.map((candidate) => (
                  <option key={candidate.id} value={candidate.id}>
                    {candidate.title}
                  </option>
                ))}
              </select>
            </div>
          ) : null}
        </div>

        {error ? (
          <p role="alert" className="mt-3 text-sm text-red-700">
            {error}
          </p>
        ) : null}

        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!valid || save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? "Saving…" : "Save"}
          </Button>
        </div>
      </div>
    </div>
  );
}

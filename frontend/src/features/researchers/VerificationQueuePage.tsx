import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Uid } from "@/components/ui/Uid";
import { toApiError } from "@/lib/api/errors";

import {
  decideVerification,
  fetchVerificationQueue,
  type VerificationDecision,
  type VerificationQueueItem,
} from "./api";

const QUEUE_QUERY_KEY = ["verification-queue"] as const;

interface PendingDecision {
  item: VerificationQueueItem;
  decision: VerificationDecision;
}

export function VerificationQueuePage() {
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<PendingDecision | null>(null);
  const [comment, setComment] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  const { data, isPending, isError } = useQuery({
    queryKey: QUEUE_QUERY_KEY,
    queryFn: fetchVerificationQueue,
  });

  const mutation = useMutation({
    mutationFn: ({ item, decision }: PendingDecision) =>
      decideVerification(item.user_id, decision, comment || undefined),
    onSuccess: async () => {
      setPending(null);
      setComment("");
      setActionError(null);
      await queryClient.invalidateQueries({ queryKey: QUEUE_QUERY_KEY });
    },
    onError: (error: unknown) => setActionError(toApiError(error).message),
  });

  if (isPending) {
    return <p className="text-sm text-ink-muted">Loading the verification queue…</p>;
  }

  if (isError) {
    return (
      <p role="alert" className="text-sm text-red-700">
        Could not load the verification queue.
      </p>
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Verification queue</h1>
      <p className="mt-1 text-sm text-ink-muted">
        Researcher profiles awaiting review in your scope. {data.length} pending.
      </p>

      {actionError ? (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {actionError}
        </p>
      ) : null}

      {data.length === 0 ? (
        <p className="mt-6 rounded-card border border-line bg-surface px-4 py-6 text-sm text-ink-muted">
          Nothing to review right now.
        </p>
      ) : (
        <div className="mt-6 overflow-x-auto rounded-card border border-line bg-surface">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line text-xs uppercase text-ink-muted">
              <tr>
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Email</th>
                <th className="px-4 py-3 font-medium">Designation</th>
                <th className="px-4 py-3 font-medium">Decision</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data.map((item) => (
                <tr key={item.user_id}>
                  <td className="px-4 py-3">
                    {/* Deciding on somebody without being able to read their
                        profile first is guesswork. The detail page shows an
                        unverified researcher, which is exactly who is here. */}
                    <Link
                      to={`/researchers/${item.user_id}`}
                      className="font-medium text-brand-700 hover:underline"
                    >
                      {item.full_name}
                    </Link>
                    <Uid value={item.registration_number} className="ml-2" />
                  </td>
                  <td className="px-4 py-3 text-ink-muted">{item.email}</td>
                  <td className="px-4 py-3">{item.designation}</td>
                  <td className="px-4 py-3">
                    <span className="flex gap-2">
                      <button
                        type="button"
                        disabled={mutation.isPending}
                        onClick={() => {
                          setActionError(null);
                          setComment("");
                          setPending({ item, decision: "verified" });
                        }}
                        className="rounded-md bg-brand-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-800 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Verify
                      </button>
                      <button
                        type="button"
                        disabled={mutation.isPending}
                        onClick={() => {
                          setActionError(null);
                          setComment("");
                          setPending({ item, decision: "rejected" });
                        }}
                        className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm font-medium hover:bg-canvas disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Reject
                      </button>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        open={pending !== null}
        title={pending?.decision === "rejected" ? "Reject this profile?" : "Verify this profile?"}
        description={
          pending
            ? `${pending.item.full_name} (${pending.item.designation}) will be marked ${pending.decision}.`
            : ""
        }
        confirmLabel={pending?.decision === "rejected" ? "Reject" : "Verify"}
        isConfirming={mutation.isPending}
        onConfirm={() => {
          if (pending) mutation.mutate(pending);
        }}
        onCancel={() => setPending(null)}
      >
        <label htmlFor="verification-comment" className="block text-sm font-medium">
          Comment {pending?.decision === "rejected" ? "(recommended)" : "(optional)"}
        </label>
        <textarea
          id="verification-comment"
          rows={3}
          value={comment}
          onChange={(event) => setComment(event.target.value)}
          className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm"
        />
      </ConfirmDialog>
    </div>
  );
}

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { toApiError } from "@/lib/api/errors";

import { sendNudge, type NudgeKind, type NudgeResult } from "./api";

/**
 * "Still waiting on this" — one button, wherever something of yours sits in
 * somebody else's queue.
 *
 * Deliberately says nothing about who it goes to. The backend decides that
 * from the thing being chased; letting the sender pick a recipient would turn
 * this into a way to message anyone in the institution.
 *
 * There is a one-per-day cooldown on the server. The button reflects the
 * refusal rather than pretending it worked.
 */
export function NudgeButton({
  kind,
  entityId,
  label = "Send a reminder",
}: {
  kind: NudgeKind;
  entityId: string;
  label?: string;
}) {
  const [sent, setSent] = useState<NudgeResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => sendNudge(kind, entityId),
    onSuccess: (result) => {
      setError(null);
      setSent(result);
    },
    onError: (err: unknown) => {
      setSent(null);
      setError(toApiError(err).message);
    },
  });

  if (sent) {
    return (
      <p role="status" className="text-xs text-emerald-700">
        Reminder sent to {sent.recipients} {sent.recipients === 1 ? "person" : "people"}.
      </p>
    );
  }

  return (
    <span className="inline-flex flex-col items-start gap-1">
      <Button
        size="sm"
        variant="secondary"
        disabled={mutation.isPending}
        onClick={() => mutation.mutate()}
      >
        {mutation.isPending ? "Sending…" : label}
      </Button>
      {error ? (
        <span role="alert" className="text-xs text-red-700">
          {error}
        </span>
      ) : null}
    </span>
  );
}

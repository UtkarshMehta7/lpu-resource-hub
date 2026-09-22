import { useState } from "react";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { toApiError } from "@/lib/api/errors";

import { reportContent, type ReportTargetType } from "./api";

const MIN_REASON = 10;

/** "Report" with a reason dialog. The backend 404s on anything the reporter
 * can't see, so this never reveals hidden content. */
export function ReportButton({
  targetType,
  targetId,
}: {
  targetType: ReportTargetType;
  targetId: string;
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [reported, setReported] = useState(false);

  const submit = async () => {
    const trimmed = reason.trim();
    if (trimmed.length < MIN_REASON) {
      setError(`Please describe the problem in at least ${MIN_REASON} characters.`);
      return;
    }
    setSending(true);
    setError(null);
    try {
      await reportContent({ target_type: targetType, target_id: targetId, reason: trimmed });
      setReported(true);
      setOpen(false);
      setReason("");
    } catch (caught) {
      setError(toApiError(caught).message);
    } finally {
      setSending(false);
    }
  };

  return (
    <>
      <button
        type="button"
        disabled={reported}
        onClick={() => setOpen(true)}
        className="text-xs text-ink-muted underline disabled:no-underline"
      >
        {reported ? "Reported" : "Report"}
      </button>
      <ConfirmDialog
        open={open}
        title="Report this content"
        description="A research coordinator or admin will review it."
        confirmLabel="Send report"
        isConfirming={sending}
        onConfirm={() => void submit()}
        onCancel={() => {
          setOpen(false);
          setError(null);
        }}
      >
        <label htmlFor={`report-reason-${targetId}`} className="block text-sm font-medium">
          What&apos;s wrong with it?
        </label>
        <textarea
          id={`report-reason-${targetId}`}
          rows={4}
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm"
        />
        {error ? (
          <p role="alert" className="mt-1 text-xs text-red-700">
            {error}
          </p>
        ) : null}
      </ConfirmDialog>
    </>
  );
}

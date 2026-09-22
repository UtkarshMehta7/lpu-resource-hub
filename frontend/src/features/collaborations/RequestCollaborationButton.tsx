import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useAuth } from "@/features/auth/authContext";
import { toApiError } from "@/lib/api/errors";

import { sendCollaborationRequest } from "./api";

const MAX_MESSAGE = 2000;

/** "Request collaboration" with a message dialog. Hidden for admins and yourself. */
export function RequestCollaborationButton({
  recipientId,
  recipientName,
  projectId = null,
}: {
  recipientId: string;
  recipientName: string;
  projectId?: string | null;
}) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const [sending, setSending] = useState(false);

  if (!user || user.role === "admin" || user.id === recipientId) return null;

  const send = async () => {
    const trimmed = message.trim();
    if (!trimmed) {
      setError("Write a short message.");
      return;
    }
    setSending(true);
    setError(null);
    try {
      await sendCollaborationRequest({
        recipient_id: recipientId,
        project_id: projectId,
        message: trimmed,
      });
      await queryClient.invalidateQueries({ queryKey: ["collaborations"] });
      setSent(true);
      setOpen(false);
      setMessage("");
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
        disabled={sent}
        onClick={() => setOpen(true)}
        className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm font-medium disabled:opacity-60"
      >
        {sent ? "Request sent" : "Request collaboration"}
      </button>
      <ConfirmDialog
        open={open}
        title={`Request collaboration with ${recipientName}`}
        description="They'll see your name, role and this message."
        confirmLabel="Send request"
        isConfirming={sending}
        onConfirm={() => void send()}
        onCancel={() => {
          setOpen(false);
          setError(null);
        }}
      >
        <label htmlFor={`collab-message-${recipientId}`} className="block text-sm font-medium">
          Message
        </label>
        <textarea
          id={`collab-message-${recipientId}`}
          rows={4}
          maxLength={MAX_MESSAGE}
          value={message}
          onChange={(event) => setMessage(event.target.value)}
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

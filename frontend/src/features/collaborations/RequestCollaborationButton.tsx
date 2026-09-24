import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useAuth } from "@/features/auth/authContext";
import { toApiError } from "@/lib/api/errors";

import { fetchCollaborationState, respondToCollaboration, sendCollaborationRequest } from "./api";

const MAX_MESSAGE = 2000;

/**
 * The control that reflects where two people actually stand.
 *
 * It used to offer "Request collaboration" unconditionally, so it invited you
 * to start something already running -- and the server happily obliged with a
 * second relationship and a second conversation (ADR 0023). It now asks the
 * state first and shows the one action that makes sense: request, cancel,
 * answer, or open the conversation you already have.
 *
 * Hidden for admins and for yourself.
 */
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

  const { data: summary, isPending: stateLoading } = useQuery({
    queryKey: ["collaboration-state", recipientId],
    queryFn: () => fetchCollaborationState(recipientId),
    enabled: Boolean(user) && user?.role !== "admin" && user?.id !== recipientId,
  });

  const respond = useMutation({
    mutationFn: (action: "accept" | "decline" | "cancel" | "end") =>
      respondToCollaboration(summary?.request_id ?? "", action),
    onSuccess: async () => {
      setError(null);
      await queryClient.invalidateQueries({ queryKey: ["collaboration-state", recipientId] });
      await queryClient.invalidateQueries({ queryKey: ["collaborations"] });
    },
    onError: (caught: unknown) => setError(toApiError(caught).message),
  });

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
      await queryClient.invalidateQueries({ queryKey: ["collaboration-state", recipientId] });
      setSent(true);
      setOpen(false);
      setMessage("");
    } catch (caught) {
      setError(toApiError(caught).message);
    } finally {
      setSending(false);
    }
  };

  const state = sent ? "requested" : (summary?.state ?? "none");
  const busy = respond.isPending || stateLoading;

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        {state === "active" ? (
          <>
            <Link
              to={summary?.conversation_id ? `/messages/${summary.conversation_id}` : "/messages"}
              className="rounded-md bg-brand-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-800"
            >
              Open conversation
            </Link>
            <button
              type="button"
              disabled={busy}
              onClick={() => respond.mutate("end")}
              className="rounded-md border border-red-300 bg-surface px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
            >
              End collaboration
            </button>
          </>
        ) : null}

        {state === "requested" && (sent || summary?.i_sent_it) ? (
          <>
            <span className="text-sm text-ink-muted">Request pending</span>
            <button
              type="button"
              disabled={busy || !summary?.request_id}
              onClick={() => respond.mutate("cancel")}
              className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm font-medium hover:bg-canvas disabled:opacity-50"
            >
              Cancel request
            </button>
          </>
        ) : null}

        {state === "requested" && summary?.i_sent_it === false ? (
          <>
            <span className="text-sm text-ink-muted">They asked to collaborate</span>
            <button
              type="button"
              disabled={busy}
              onClick={() => respond.mutate("accept")}
              className="rounded-md bg-brand-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-800 disabled:opacity-50"
            >
              Accept
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => respond.mutate("decline")}
              className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm font-medium hover:bg-canvas disabled:opacity-50"
            >
              Decline
            </button>
          </>
        ) : null}

        {state === "none" || state === "ended" ? (
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm font-medium"
          >
            {state === "ended" ? "Collaborate again" : "Request collaboration"}
          </button>
        ) : null}
      </div>
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

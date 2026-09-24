import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { toApiError } from "@/lib/api/errors";
import { useState } from "react";

import { openProjectConversation } from "./api";

/**
 * Opens (or reopens) a project team's thread and goes to it.
 *
 * Idempotent on the server, so this button never has to know whether a thread
 * already exists -- which is why there is no "create" and "open" distinction
 * on screen either.
 */
export function TeamThreadButton({ projectId }: { projectId: string }) {
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  const open = useMutation({
    mutationFn: () => openProjectConversation(projectId),
    onSuccess: (conversation) => navigate(`/messages/${conversation.id}`),
    onError: (caught: unknown) => setError(toApiError(caught).message),
  });

  return (
    <>
      <button
        type="button"
        disabled={open.isPending}
        onClick={() => {
          setError(null);
          open.mutate();
        }}
        className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm font-medium hover:bg-canvas disabled:opacity-50"
      >
        {open.isPending ? "Opening…" : "Message the team"}
      </button>
      {error ? (
        <p role="alert" className="mt-2 text-sm text-red-700">
          {error}
        </p>
      ) : null}
    </>
  );
}

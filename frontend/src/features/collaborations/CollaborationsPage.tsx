import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { toApiError } from "@/lib/api/errors";

import {
  COLLABORATION_STATUS_LABEL,
  fetchMyCollaborations,
  respondToCollaboration,
  type Box,
  type CollaborationRequest,
  type CollaborationStatus,
} from "./api";

const TAB =
  "rounded-md px-3 py-1.5 text-sm font-medium border border-line aria-selected:bg-brand-700 aria-selected:text-white";

/** Collaboration inbox and sent requests. */
export function CollaborationsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const box: Box = searchParams.get("box") === "sent" ? "sent" : "inbox";
  const status = (searchParams.get("status") || undefined) as CollaborationStatus | undefined;
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value) {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    setSearchParams(next);
  };

  const { data, isPending, isError } = useQuery({
    queryKey: ["collaborations", box, status],
    queryFn: () => fetchMyCollaborations(box, status),
  });

  const respond = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "accept" | "decline" | "cancel" }) =>
      respondToCollaboration(id, action),
    onSuccess: async () => {
      setError(null);
      await queryClient.invalidateQueries({ queryKey: ["collaborations"] });
    },
    onError: (caught) => setError(toApiError(caught).message),
  });

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Collaboration requests</h1>
      <div className="mt-4 flex flex-wrap items-center gap-2" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={box === "inbox"}
          onClick={() => setParam("box", "")}
          className={TAB}
        >
          Inbox
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={box === "sent"}
          onClick={() => setParam("box", "sent")}
          className={TAB}
        >
          Sent
        </button>
        <label htmlFor="collab-status" className="sr-only">
          Status
        </label>
        <select
          id="collab-status"
          value={status ?? ""}
          onChange={(event) => setParam("status", event.target.value)}
          className="ml-auto rounded-md border border-line bg-surface px-3 py-1.5 text-sm"
        >
          <option value="">Any status</option>
          {Object.entries(COLLABORATION_STATUS_LABEL).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      {error ? (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {error}
        </p>
      ) : null}
      {isPending ? <p className="mt-6 text-sm text-ink-muted">Loading…</p> : null}
      {isError ? (
        <p role="alert" className="mt-6 text-sm text-red-700">
          Could not load requests.
        </p>
      ) : null}
      {data && data.length === 0 ? (
        <p className="mt-6 text-sm text-ink-muted">
          {box === "inbox" ? "No requests received." : "You haven't sent any requests."}
        </p>
      ) : null}

      <ul className="mt-6 space-y-3">
        {data?.map((request) => (
          <RequestItem
            key={request.id}
            request={request}
            box={box}
            busy={respond.isPending}
            onAction={(action) => respond.mutate({ id: request.id, action })}
          />
        ))}
      </ul>
    </div>
  );
}

function RequestItem({
  request,
  box,
  busy,
  onAction,
}: {
  request: CollaborationRequest;
  box: Box;
  busy: boolean;
  onAction: (action: "accept" | "decline" | "cancel") => void;
}) {
  const other = box === "inbox" ? request.sender : request.recipient;
  const profileLink = other.role === "student" ? null : `/researchers/${other.id}`;
  return (
    <li className="rounded-card border border-line bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="text-sm">
          {box === "inbox" ? "From " : "To "}
          {profileLink ? (
            <Link to={profileLink} className="font-semibold hover:underline">
              {other.full_name}
            </Link>
          ) : (
            <span className="font-semibold">{other.full_name}</span>
          )}
          {request.project_id && request.project_title ? (
            <>
              {" · about "}
              <Link
                to={`/projects/${request.project_id}`}
                className="text-brand-700 hover:underline"
              >
                {request.project_title}
              </Link>
            </>
          ) : null}
        </p>
        <span className="rounded-md border border-line px-2 py-1 text-xs">
          {COLLABORATION_STATUS_LABEL[request.status]}
        </span>
      </div>
      <p className="mt-2 whitespace-pre-line text-sm">{request.message}</p>
      <p className="mt-1 text-xs text-ink-muted">{new Date(request.created_at).toLocaleString()}</p>
      {request.status === "pending" ? (
        <div className="mt-3 flex gap-2">
          {box === "inbox" ? (
            <>
              <button
                type="button"
                disabled={busy}
                onClick={() => onAction("accept")}
                className="rounded-md bg-brand-700 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
              >
                Accept
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => onAction("decline")}
                className="rounded-md border border-line px-3 py-1.5 text-sm disabled:opacity-50"
              >
                Decline
              </button>
            </>
          ) : (
            <button
              type="button"
              disabled={busy}
              onClick={() => onAction("cancel")}
              className="rounded-md border border-red-300 px-3 py-1.5 text-sm text-red-700 disabled:opacity-50"
            >
              Cancel request
            </button>
          )}
        </div>
      ) : null}
    </li>
  );
}

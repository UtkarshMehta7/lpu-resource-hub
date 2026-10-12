import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { SkeletonList } from "@/components/ui/Skeleton";
import { StatusPill } from "@/components/ui/StatusPill";
import { Uid } from "@/components/ui/Uid";
import { toApiError } from "@/lib/api/errors";

import {
  changeRequestStatus,
  downloadRequestAttachment,
  fetchRequest,
  fileSizeLabel,
  type PersonalRequest,
  type RequestStatus,
} from "./api";
import {
  ACTION_LABEL,
  CATEGORY_LABEL,
  needsReason,
  roleLabel,
  STATUS_LABEL,
  STATUS_TONE,
} from "./labels";

const FIELD = "mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm";

function Attachments({ request }: { request: PersonalRequest }) {
  if (request.attachments.length === 0) return null;
  return (
    <section className="mt-6">
      <h2 className="text-sm font-semibold">Attached</h2>
      <ul className="mt-2 space-y-2">
        {request.attachments.map((attachment) => (
          <li key={attachment.id}>
            <button
              type="button"
              onClick={() => void downloadRequestAttachment(request.id, attachment)}
              className="flex w-full items-center justify-between gap-3 rounded-md border border-line bg-surface px-3 py-2 text-left text-sm hover:bg-canvas"
            >
              <span className="min-w-0 truncate font-medium">{attachment.filename}</span>
              <span className="shrink-0 text-xs text-ink-muted">
                {fileSizeLabel(attachment.byte_size)} · Download
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * One request, and whatever this reader may do with it next.
 *
 * `next_statuses` comes from the server computed per reader, so this page
 * never offers a move the service would refuse -- the same discipline the
 * patent pipeline holds. There is no local copy of the transition table.
 */
export function RequestDetailPage() {
  const { requestId = "" } = useParams();
  const queryClient = useQueryClient();
  const [chosen, setChosen] = useState<RequestStatus | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data, isPending, isError } = useQuery({
    queryKey: ["request", requestId],
    queryFn: () => fetchRequest(requestId),
    enabled: Boolean(requestId),
  });

  const move = useMutation({
    mutationFn: (status: RequestStatus) =>
      changeRequestStatus(requestId, status, note.trim() || undefined),
    onSuccess: () => {
      setChosen(null);
      setNote("");
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["request", requestId] });
      void queryClient.invalidateQueries({ queryKey: ["requests"] });
    },
    onError: (caught) => setError(toApiError(caught).message),
  });

  if (isPending) return <SkeletonList rows={3} />;
  if (isError || !data) {
    return (
      <EmptyState
        title="Request not found"
        description="It may have been withdrawn, or it was never yours to read."
        actionLabel="Back to your requests"
        actionTo="/me/requests"
      />
    );
  }

  const other = data.viewer_is_sender
    ? { name: data.recipient_name, role: data.recipient_role, uid: null }
    : {
        name: data.sender_name,
        role: data.sender_role,
        uid: data.sender_registration_number,
      };

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title={data.subject}
        description={
          <>
            {data.viewer_is_sender ? "You asked" : "Asked by"} {other.name}
            {other.uid ? (
              <>
                {" "}
                <Uid value={other.uid} />
              </>
            ) : null}{" "}
            · {roleLabel(other.role)} · {CATEGORY_LABEL[data.category]}
          </>
        }
        actions={
          <StatusPill tone={STATUS_TONE[data.status]}>{STATUS_LABEL[data.status]}</StatusPill>
        }
      />

      <div className="rounded-card border border-line bg-surface px-4 py-4">
        <p className="whitespace-pre-wrap text-sm">{data.body}</p>
      </div>

      <Attachments request={data} />

      {data.resolution_note ? (
        <section className="mt-6">
          <h2 className="text-sm font-semibold">
            {data.status === "declined" ? "Why it was declined" : "The answer"}
          </h2>
          <p className="mt-2 whitespace-pre-wrap rounded-card border border-line bg-canvas px-4 py-3 text-sm">
            {data.resolution_note}
          </p>
        </section>
      ) : null}

      {data.next_statuses.length > 0 ? (
        <section className="mt-8">
          <h2 className="text-sm font-semibold">What happens next</h2>
          <div className="mt-2 flex flex-wrap gap-2">
            {data.next_statuses.map((status) => (
              <Button
                key={status}
                variant={status === "resolved" ? "primary" : "secondary"}
                size="sm"
                onClick={() => {
                  setError(null);
                  // Declining always asks for the reason first; the others
                  // go straight through, since a note on them is optional.
                  if (needsReason(status)) setChosen(status);
                  else move.mutate(status);
                }}
                disabled={move.isPending}
              >
                {ACTION_LABEL[status]}
              </Button>
            ))}
          </div>

          {chosen ? (
            <div className="mt-4 rounded-card border border-line bg-surface px-4 py-3">
              <label htmlFor="request-note" className="block text-sm font-medium">
                Why are you declining?
              </label>
              <p className="mt-1 text-xs text-ink-muted">
                Required. &quot;No&quot; without a reason is what stops the next person asking.
              </p>
              <textarea
                id="request-note"
                rows={3}
                className={FIELD}
                value={note}
                onChange={(event) => setNote(event.target.value)}
              />
              <div className="mt-3 flex gap-2">
                <Button
                  size="sm"
                  disabled={note.trim() === "" || move.isPending}
                  onClick={() => move.mutate(chosen)}
                >
                  {move.isPending ? "Saving…" : "Decline the request"}
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    setChosen(null);
                    setNote("");
                  }}
                >
                  Cancel
                </Button>
              </div>
            </div>
          ) : null}

          {error ? <p className="mt-3 text-sm text-red-700">{error}</p> : null}
        </section>
      ) : null}
    </div>
  );
}

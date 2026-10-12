import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { ButtonLink } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { SkeletonList } from "@/components/ui/Skeleton";
import { StatusPill } from "@/components/ui/StatusPill";
import { useAuth } from "@/features/auth/authContext";

import {
  fetchRequestInbox,
  fetchSentRequests,
  type PersonalRequest,
  type RequestStatus,
} from "./api";
import { CATEGORY_LABEL, counterpart, STATUS_LABEL, STATUS_TONE } from "./labels";

const FIELD = "mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm";

/** Roles that may put a request to somebody. Mirrors REQUEST_RECIPIENT_ROLES. */
const CAN_SEND = new Set([
  "student",
  "faculty",
  "facility_custodian",
  "research_coordinator",
  "dean_of_research",
]);

function dayLabel(value: string): string {
  return new Date(value).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function RequestRow({ request }: { request: PersonalRequest }) {
  return (
    <li className="rounded-card border border-line bg-surface">
      <Link
        to={`/requests/${request.id}`}
        className="block px-4 py-3 hover:bg-canvas focus-visible:bg-canvas"
      >
        <div className="flex flex-wrap items-start justify-between gap-2">
          <p className="min-w-0 text-sm font-medium">{request.subject}</p>
          <span className="flex shrink-0 items-center gap-2">
            <StatusPill tone="neutral">{CATEGORY_LABEL[request.category]}</StatusPill>
            <StatusPill tone={STATUS_TONE[request.status]}>
              {STATUS_LABEL[request.status]}
            </StatusPill>
          </span>
        </div>
        <p className="mt-1 line-clamp-2 text-sm text-ink-muted">{request.body}</p>
        <p className="mt-1.5 text-xs text-ink-muted">
          {request.viewer_is_sender ? "To" : "From"} {counterpart(request)} ·{" "}
          {dayLabel(request.created_at)}
          {request.attachments.length > 0
            ? ` · ${request.attachments.length} file${request.attachments.length === 1 ? "" : "s"}`
            : ""}
        </p>
      </Link>
    </li>
  );
}

/**
 * Requests you have sent, or requests put to you.
 *
 * One page, two directions, because a request reads the same either way --
 * only the other party and the moves on offer change, and both come from the
 * server per reader.
 */
export function RequestsPage({ inbox = false }: { inbox?: boolean }) {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  // Narrowed rather than cast: a stale or hand-edited ?status= must not
  // be sent to the API as if it were a real one.
  const raw = searchParams.get("status") ?? "";
  const status: RequestStatus | "" = raw in STATUS_LABEL ? (raw as RequestStatus) : "";
  const page = Number(searchParams.get("page") ?? "1");

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    setSearchParams(next);
  };

  const { data, isPending, isError } = useQuery({
    queryKey: ["requests", { inbox, status, page }],
    queryFn: () =>
      inbox
        ? fetchRequestInbox({ status: status || undefined, page })
        : fetchSentRequests({ status: status || undefined, page }),
  });

  const canSend = user ? CAN_SEND.has(user.role) : false;
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div>
      <PageHeader
        title={inbox ? "Requests to you" : "My requests"}
        description={
          inbox
            ? "Requests people below you have put to you by name. Taking one up is not answering it."
            : "Requests you have put to somebody above you, and where each one has got to."
        }
        actions={
          <>
            {inbox ? (
              <ButtonLink to="/me/requests" variant="secondary">
                My requests
              </ButtonLink>
            ) : null}
            {canSend ? <ButtonLink to="/requests/new">Make a request</ButtonLink> : null}
          </>
        }
      />

      <div className="max-w-xs">
        <label htmlFor="request-status" className="block text-sm font-medium">
          Show
        </label>
        <select
          id="request-status"
          value={status}
          onChange={(event) => setParam("status", event.target.value)}
          className={FIELD}
        >
          <option value="">Everything</option>
          {Object.entries(STATUS_LABEL).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      <div className="mt-6">
        {isPending ? <SkeletonList rows={3} /> : null}
        {isError ? (
          <EmptyState title="Requests could not be loaded" description="Please try again." />
        ) : null}
        {data && data.items.length === 0 ? (
          <EmptyState
            title={
              status
                ? "Nothing with that status"
                : inbox
                  ? "Nothing has been put to you"
                  : "You have not made any requests"
            }
            description={
              inbox
                ? "When somebody below you puts a request to you by name, it appears here."
                : "A request goes to a named person above you — your faculty, your coordinator, the Dean of Research or an administrator."
            }
          />
        ) : null}
        {data && data.items.length > 0 ? (
          <ul className="space-y-3">
            {data.items.map((request) => (
              <RequestRow key={request.id} request={request} />
            ))}
          </ul>
        ) : null}
      </div>

      {data && totalPages > 1 ? (
        <div className="mt-6 flex items-center justify-between text-sm">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => setParam("page", String(page - 1))}
            className="rounded-md border border-line px-3 py-1.5 disabled:opacity-40"
          >
            Previous
          </button>
          <span className="text-ink-muted">
            Page {page} of {totalPages}
          </span>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => setParam("page", String(page + 1))}
            className="rounded-md border border-line px-3 py-1.5 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      ) : null}
    </div>
  );
}

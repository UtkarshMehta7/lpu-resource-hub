import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/ui/EmptyState";
import { Uid } from "@/components/ui/Uid";
import { useAuth } from "@/features/auth/authContext";

import { fetchConversations, type Conversation } from "./api";
import { initials, relativeTime } from "./format";
import { CONVERSATIONS_QUERY_KEY } from "./queryKeys";

/**
 * Every thread this person takes part in.
 *
 * Polled on the same 60s heartbeat as the notification bell -- the list only
 * has to be roughly fresh, because the thread itself polls much faster while
 * it is open.
 */
export function ConversationsPage() {
  const { user } = useAuth();
  const { data, isPending, isError } = useQuery({
    queryKey: CONVERSATIONS_QUERY_KEY,
    queryFn: fetchConversations,
    refetchInterval: 60_000,
  });

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-semibold tracking-tight">Messages</h1>
      <p className="mt-1 text-sm text-ink-muted">
        Threads open when a collaboration request is accepted, or when a project team starts one.
      </p>

      {isPending ? <p className="mt-6 text-sm text-ink-muted">Loading…</p> : null}
      {isError ? (
        <p role="alert" className="mt-6 text-sm text-red-700">
          Could not load your messages.
        </p>
      ) : null}

      {data && data.length === 0 ? (
        <div className="mt-6">
          <EmptyState
            title="No conversations yet"
            description="Accept a collaboration request, or open your project team's thread from the project page, and it will appear here."
          />
        </div>
      ) : null}

      {data && data.length > 0 ? (
        <ul className="mt-6 space-y-2">
          {data.map((conversation) => (
            <ConversationRow
              key={conversation.id}
              conversation={conversation}
              viewerId={user?.id}
            />
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function ConversationRow({
  conversation,
  viewerId,
}: {
  conversation: Conversation;
  viewerId: string | undefined;
}) {
  const unread = conversation.unread_count > 0;
  // A one-to-one thread is the other person; a project thread is the project.
  const other = conversation.participants.find((person) => person.user_id !== viewerId);
  const showUid = conversation.subject_kind === "collaboration" && other;

  return (
    <li>
      <Link
        to={`/messages/${conversation.id}`}
        className={`flex items-start gap-3 rounded-card border p-4 transition hover:border-brand-200 hover:bg-brand-50 ${
          unread ? "border-brand-200 bg-brand-50/60" : "border-line bg-surface"
        }`}
      >
        <span
          aria-hidden="true"
          className="grid size-10 shrink-0 place-items-center rounded-full bg-brand-100 text-sm font-semibold text-brand-800"
        >
          {initials(conversation.title)}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-baseline gap-x-2">
            <span className={`truncate text-sm ${unread ? "font-semibold" : "font-medium"}`}>
              {conversation.title}
            </span>
            {showUid ? <Uid value={other.registration_number} /> : null}
            {conversation.subject_kind === "project" ? (
              <span className="rounded-md border border-line px-1.5 py-0.5 text-xs text-ink-muted">
                Project team
              </span>
            ) : null}
          </span>
          <span className="mt-1 block truncate text-sm text-ink-muted">
            {conversation.preview ?? "No messages yet — say hello."}
          </span>
        </span>
        <span className="flex shrink-0 flex-col items-end gap-1">
          <span className="text-xs text-ink-muted">
            {relativeTime(conversation.last_message_at ?? conversation.created_at)}
          </span>
          {unread ? (
            <span
              className="grid min-w-5 place-items-center rounded-full bg-brand-700 px-1.5 text-xs font-semibold text-white"
              aria-label={`${conversation.unread_count} unread`}
            >
              {conversation.unread_count}
            </span>
          ) : null}
        </span>
      </Link>
    </li>
  );
}

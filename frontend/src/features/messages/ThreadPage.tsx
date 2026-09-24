import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Uid } from "@/components/ui/Uid";
import { SkeletonList } from "@/components/ui/Skeleton";
import { useAuth } from "@/features/auth/authContext";
import { ReportButton } from "@/features/reports/ReportButton";
import { toApiError } from "@/lib/api/errors";

import {
  fetchConversation,
  fetchMessages,
  markConversationRead,
  sendMessage,
  type Message,
} from "./api";
import { clockTime, dayLabel, initials } from "./format";
import { CONVERSATIONS_QUERY_KEY, UNREAD_TOTAL_QUERY_KEY, threadKey } from "./queryKeys";
import { useVisible } from "./useVisible";

/** How often an open thread asks for new messages. */
const POLL_MS = 10_000;

/**
 * One conversation.
 *
 * Polling, not a socket (ADR 0022) -- but a sent message is appended
 * immediately rather than waiting for the next poll, which is what makes a
 * 10-second interval feel like a chat instead of a form.
 */
export function ThreadPage() {
  const { conversationId = "" } = useParams<{ conversationId: string }>();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const visible = useVisible();

  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const { data: conversation, isError: conversationFailed } = useQuery({
    queryKey: ["conversation", conversationId],
    queryFn: () => fetchConversation(conversationId),
    enabled: conversationId !== "",
  });

  const {
    data: page,
    isPending,
    isError,
  } = useQuery({
    queryKey: threadKey(conversationId),
    queryFn: () => fetchMessages(conversationId),
    enabled: conversationId !== "",
    // Paused when the tab is hidden: nobody is reading, so nobody needs the
    // requests, and a backgrounded tab should not keep a free instance awake.
    refetchInterval: visible ? POLL_MS : false,
  });

  const messages = useMemo(() => page?.items ?? [], [page]);
  const newest = messages.at(-1)?.id;

  // Opening the thread, and each arrival while it is open, counts as read.
  useEffect(() => {
    if (!conversationId || !newest) return;
    void markConversationRead(conversationId).then(() => {
      void queryClient.invalidateQueries({ queryKey: CONVERSATIONS_QUERY_KEY });
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
      void queryClient.invalidateQueries({ queryKey: UNREAD_TOTAL_QUERY_KEY });
    });
  }, [conversationId, newest, queryClient]);

  useEffect(() => {
    // Feature-checked: not every environment implements it (jsdom does not),
    // and failing to scroll must never break rendering the thread.
    const end = bottomRef.current;
    if (typeof end?.scrollIntoView === "function") {
      end.scrollIntoView({ block: "end" });
    }
  }, [newest]);

  const send = useMutation({
    mutationFn: (body: string) => sendMessage(conversationId, body),
    onSuccess: async () => {
      setDraft("");
      setError(null);
      await queryClient.invalidateQueries({
        queryKey: threadKey(conversationId),
      });
      await queryClient.invalidateQueries({ queryKey: CONVERSATIONS_QUERY_KEY });
    },
    onError: (caught: unknown) => setError(toApiError(caught).message),
  });

  const submit = () => {
    const body = draft.trim();
    if (!body || send.isPending) return;
    send.mutate(body);
  };

  if (conversationFailed) {
    return (
      <div className="mx-auto max-w-3xl">
        <p role="alert" className="text-sm text-red-700">
          This conversation isn&apos;t available.
        </p>
        <Link to="/messages" className="mt-2 inline-block text-sm font-medium text-brand-700">
          Back to messages
        </Link>
      </div>
    );
  }

  const others = conversation?.participants.filter((person) => person.user_id !== user?.id) ?? [];

  return (
    <div className="mx-auto flex max-w-3xl flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-line pb-4">
        <Link
          to="/messages"
          className="text-sm font-medium text-brand-700 hover:underline"
          aria-label="Back to messages"
        >
          ←
        </Link>
        <span
          aria-hidden="true"
          className="grid size-10 place-items-center rounded-full bg-brand-100 text-sm font-semibold text-brand-800"
        >
          {initials(conversation?.title ?? "")}
        </span>
        <div className="min-w-0">
          <h1 className="truncate text-lg font-semibold">
            {conversation?.title ?? "Conversation"}
          </h1>
          <p className="text-xs text-ink-muted">
            {conversation?.subject_kind === "project" ? (
              <>
                Project team ·{" "}
                <Link to={`/projects/${conversation.subject_id}`} className="hover:underline">
                  open the project
                </Link>{" "}
                · {conversation.participants.length} people
              </>
            ) : (
              others.map((person) => (
                <span key={person.user_id}>
                  {person.full_name} <Uid value={person.registration_number} />
                </span>
              ))
            )}
          </p>
        </div>
      </header>

      {error ? (
        <p role="alert" className="mt-3 text-sm text-red-700">
          {error}
        </p>
      ) : null}

      <div
        className="mt-4 flex-1 space-y-1 overflow-y-auto"
        aria-live="polite"
        aria-label="Messages"
      >
        {isPending ? <SkeletonList rows={3} /> : null}
        {isError ? (
          <p role="alert" className="text-sm text-red-700">
            Could not load the messages.
          </p>
        ) : null}
        {!isPending && messages.length === 0 ? (
          <p className="rounded-card border border-dashed border-line p-6 text-center text-sm text-ink-muted">
            No messages yet. Only{" "}
            {conversation?.subject_kind === "project" ? "the project team" : "the two of you"} can
            see this thread.
          </p>
        ) : null}

        {messages.map((message, index) => (
          <MessageBubble
            key={message.id}
            message={message}
            mine={message.sender_id === user?.id}
            showDay={
              index === 0 ||
              dayLabel(messages[index - 1]!.created_at) !== dayLabel(message.created_at)
            }
            startsRun={index === 0 || messages[index - 1]!.sender_id !== message.sender_id}
          />
        ))}
        <div ref={bottomRef} />
      </div>

      {conversation && !conversation.open ? (
        // Said here rather than discovered by pressing Send: the server
        // refuses with 409, and finding that out the hard way is worse.
        <p className="mt-4 rounded-card border border-dashed border-line bg-surface px-4 py-3 text-center text-sm text-ink-muted">
          This collaboration has ended, so the conversation is read-only. Everything said here
          stays.
        </p>
      ) : (
        <form
          className="sticky bottom-0 mt-4 flex items-end gap-2 border-t border-line bg-canvas pt-3"
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
        >
          <label htmlFor="message-body" className="sr-only">
            Message
          </label>
          <textarea
            id="message-body"
            value={draft}
            rows={1}
            maxLength={4000}
            placeholder="Write a message…"
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              // Enter sends, Shift+Enter starts a line: what people expect of a
              // chat box, and the reason this is a textarea and not an input.
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                submit();
              }
            }}
            className="max-h-40 min-h-10 flex-1 resize-y rounded-md border border-line bg-surface px-3 py-2 text-sm"
          />
          <button
            type="submit"
            disabled={!draft.trim() || send.isPending}
            className="rounded-md bg-brand-700 px-4 py-2 text-sm font-medium text-white hover:bg-brand-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {send.isPending ? "Sending…" : "Send"}
          </button>
        </form>
      )}
    </div>
  );
}

function MessageBubble({
  message,
  mine,
  showDay,
  startsRun,
}: {
  message: Message;
  mine: boolean;
  showDay: boolean;
  startsRun: boolean;
}) {
  return (
    <>
      {showDay ? (
        <p className="py-3 text-center text-xs font-medium text-ink-muted">
          {dayLabel(message.created_at)}
        </p>
      ) : null}
      <div className={`flex ${mine ? "justify-end" : "justify-start"}`}>
        <div className={`max-w-[85%] ${mine ? "text-right" : "text-left"}`}>
          {startsRun && !mine ? (
            <p className="mb-1 text-xs font-medium">
              {message.sender_name} <Uid value={message.sender_registration_number} />
            </p>
          ) : null}
          <div
            className={`group inline-block rounded-2xl px-3 py-2 text-left text-sm ${
              message.hidden
                ? "border border-dashed border-line italic text-ink-muted"
                : mine
                  ? "bg-brand-700 text-white"
                  : "border border-line bg-surface"
            }`}
          >
            {message.hidden ? (
              "This message was removed by a moderator."
            ) : (
              <span className="whitespace-pre-wrap break-words">{message.body}</span>
            )}
          </div>
          <p className="mt-0.5 flex items-center justify-end gap-2 text-xs text-ink-muted">
            <span>{clockTime(message.created_at)}</span>
            {!mine && !message.hidden ? (
              <ReportButton targetType="message" targetId={message.id} />
            ) : null}
          </p>
        </div>
      </div>
    </>
  );
}

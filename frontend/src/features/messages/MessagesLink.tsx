import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { MessageIcon } from "@/components/ui/icons";

import { fetchUnreadTotal } from "./api";
import { UNREAD_TOTAL_QUERY_KEY } from "./queryKeys";

/**
 * Header link to Messages, with the unread count.
 *
 * Next to the bell rather than in the navigation list: a conversation is
 * something people come back to repeatedly, and burying it behind "More"
 * would make every reply a three-click errand. Polls on the same gentle
 * 60-second heartbeat as the bell -- the thread itself polls faster, but only
 * while somebody has it open.
 */
export function MessagesLink() {
  const { data } = useQuery({
    queryKey: UNREAD_TOTAL_QUERY_KEY,
    queryFn: fetchUnreadTotal,
    refetchInterval: 60_000,
  });
  const unread = data ?? 0;

  return (
    <Link
      to="/messages"
      className="relative inline-flex size-9 shrink-0 items-center justify-center rounded-md text-ink-muted transition-colors hover:bg-canvas hover:text-ink"
      aria-label={unread > 0 ? `Messages (${unread} unread)` : "Messages"}
    >
      <MessageIcon className="size-5" />
      {unread > 0 ? (
        <span className="absolute right-0.5 top-0.5 grid min-w-4 place-items-center rounded-full bg-brand-700 px-1 text-[10px] font-semibold leading-4 text-white">
          {unread > 9 ? "9+" : unread}
        </span>
      ) : null}
    </Link>
  );
}

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

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
      className="relative rounded-md px-2 py-1 text-sm font-medium hover:underline"
      aria-label={unread > 0 ? `Messages (${unread} unread)` : "Messages"}
    >
      <span aria-hidden="true">💬</span>
      {unread > 0 ? (
        <span className="absolute -right-1 -top-1 grid min-w-4 place-items-center rounded-full bg-brand-700 px-1 text-[10px] font-semibold text-white">
          {unread > 9 ? "9+" : unread}
        </span>
      ) : null}
    </Link>
  );
}

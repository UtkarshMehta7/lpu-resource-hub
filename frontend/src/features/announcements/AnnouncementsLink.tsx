import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { MegaphoneIcon } from "@/components/ui/icons";

import { fetchUnreadCount } from "./api";

/**
 * Header link to the notice board, with the count of what you have not read.
 *
 * Next to the bell and the messages link rather than only in the navigation
 * list: a notice is something somebody needs to see today, and a board nobody
 * is told about is a board nobody reads. Polls on the same gentle 60-second
 * heartbeat as its neighbours.
 *
 * The count is a NOT EXISTS against `announcement_reads` on the server, so
 * this badge costs one query however many people the notice was addressed to
 * -- posting writes no row per account.
 */
export function AnnouncementsLink() {
  const { data } = useQuery({
    queryKey: ["announcements", "unread-count"],
    queryFn: fetchUnreadCount,
    refetchInterval: 60_000,
  });
  const unread = data ?? 0;

  return (
    <Link
      to="/announcements"
      className="relative inline-flex size-9 shrink-0 items-center justify-center rounded-md text-ink-muted transition-colors hover:bg-canvas hover:text-ink"
      aria-label={unread > 0 ? `Announcements (${unread} unread)` : "Announcements"}
    >
      <MegaphoneIcon className="size-5" />
      {unread > 0 ? (
        <span className="absolute right-0.5 top-0.5 grid min-w-4 place-items-center rounded-full bg-brand-700 px-1 text-[10px] font-semibold leading-4 text-white">
          {unread > 9 ? "9+" : unread}
        </span>
      ) : null}
    </Link>
  );
}

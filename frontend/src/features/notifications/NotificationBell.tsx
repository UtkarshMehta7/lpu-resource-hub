import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { fetchNotifications } from "./api";

/** Header bell with the unread count. Polls gently; there are no sockets. */
export function NotificationBell() {
  const { data } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => fetchNotifications(),
    refetchInterval: 60_000,
  });
  const unread = data?.unread_count ?? 0;

  return (
    <Link
      to="/me/notifications"
      className="relative rounded-md px-2 py-1 text-sm font-medium hover:underline"
      aria-label={unread > 0 ? `Notifications (${unread} unread)` : "Notifications"}
    >
      <span aria-hidden="true">🔔</span>
      {unread > 0 ? (
        <span className="absolute -right-1 -top-1 grid min-w-4 place-items-center rounded-full bg-brand-700 px-1 text-[10px] font-semibold text-white">
          {unread > 9 ? "9+" : unread}
        </span>
      ) : null}
    </Link>
  );
}

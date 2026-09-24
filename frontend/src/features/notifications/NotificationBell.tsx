import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { BellIcon } from "@/components/ui/icons";

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
      className="relative inline-flex size-9 shrink-0 items-center justify-center rounded-md text-ink-muted transition-colors hover:bg-canvas hover:text-ink"
      aria-label={unread > 0 ? `Notifications (${unread} unread)` : "Notifications"}
    >
      <BellIcon className="size-5" />
      {unread > 0 ? (
        <span className="absolute right-0.5 top-0.5 grid min-w-4 place-items-center rounded-full bg-brand-700 px-1 text-[10px] font-semibold leading-4 text-white">
          {unread > 9 ? "9+" : unread}
        </span>
      ) : null}
    </Link>
  );
}

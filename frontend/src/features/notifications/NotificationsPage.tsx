import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonList } from "@/components/ui/Skeleton";

import { fetchNotifications, markAllNotificationsRead, markNotificationRead } from "./api";
import { describeNotification } from "./describe";

export function NotificationsPage() {
  const queryClient = useQueryClient();
  const { data, isPending, isError } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => fetchNotifications(),
  });

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ["notifications"] });
  };
  const markOne = useMutation({
    mutationFn: (id: string) => markNotificationRead(id),
    onSuccess: invalidate,
  });
  const markAll = useMutation({ mutationFn: markAllNotificationsRead, onSuccess: invalidate });

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Notifications</h1>
        {data && data.unread_count > 0 ? (
          <button
            type="button"
            disabled={markAll.isPending}
            onClick={() => markAll.mutate()}
            className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm font-medium disabled:opacity-50"
          >
            Mark all read ({data.unread_count})
          </button>
        ) : null}
      </div>

      {isPending ? (
        <div className="mt-6">
          <SkeletonList />
        </div>
      ) : null}
      {isError ? (
        <p role="alert" className="mt-6 text-sm text-red-700">
          Could not load your notifications.
        </p>
      ) : null}
      {data && data.items.length === 0 ? (
        <div className="mt-6">
          <EmptyState
            title="Nothing yet"
            description="Applications, collaboration requests, booking decisions and deadline reminders show up here."
          />
        </div>
      ) : null}

      <ul className="mt-6 space-y-2">
        {data?.items.map((notification) => {
          const line = describeNotification(notification);
          const unread = notification.read_at === null;
          return (
            <li
              key={notification.id}
              className={`rounded-card border p-4 ${
                unread ? "border-brand-200 bg-brand-50" : "border-line bg-surface"
              }`}
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                {line.to ? (
                  <Link to={line.to} className="text-sm font-medium hover:underline">
                    {line.text}
                  </Link>
                ) : (
                  <span className="text-sm font-medium">{line.text}</span>
                )}
                {unread ? (
                  <button
                    type="button"
                    onClick={() => markOne.mutate(notification.id)}
                    className="text-xs text-brand-700 hover:underline"
                  >
                    Mark read
                  </button>
                ) : null}
              </div>
              {line.detail ? <p className="mt-1 text-xs text-ink-muted">“{line.detail}”</p> : null}
              <p className="mt-1 text-xs text-ink-muted">
                {new Date(notification.created_at).toLocaleString()}
              </p>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

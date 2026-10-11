import { Link } from "react-router-dom";

import { StatusPill } from "@/components/ui/StatusPill";
import { useAuth } from "@/features/auth/authContext";

import type { AnnouncementsPanel } from "@/features/dashboard/api";

import { audienceLabel, posterLabel } from "./labels";

/** Roles that may post. Mirrors Permission.ANNOUNCEMENT_POST on the server. */
const CAN_POST = new Set(["research_coordinator", "dean_of_research", "admin"]);

function dayLabel(value: string | null): string {
  if (!value) return "";
  return new Date(value).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/**
 * The notice board on the dashboard: what has been said lately.
 *
 * This is where everybody meets the board, which is why it sits at the TOP
 * of the dashboard and above the role sections -- a notice is addressed to
 * you, and the rest of the page is about your own work. The searchable
 * history at /announcements is for looking something up afterwards, and the
 * link to it is the only way this section hides anything.
 *
 * Rendered for every role, from a panel the server always sends, so there is
 * no role branch here at all.
 */
export function DashboardAnnouncements({ panel }: { panel?: AnnouncementsPanel }) {
  const { user } = useAuth();
  const canPost = user ? CAN_POST.has(user.role) : false;
  // Defaulted here rather than at the call site: an API that predates this
  // field sends nothing, and a dashboard that throws in render is a worse
  // outcome than a section that says nothing has been announced.
  const latest = panel?.latest ?? [];
  const unread = panel?.unread ?? 0;

  return (
    <section className="mt-8">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-base font-semibold">
          Announcements
          {unread > 0 ? <StatusPill tone="info">{unread} unread</StatusPill> : null}
        </h2>
        <span className="flex items-center gap-3 text-sm">
          {canPost ? (
            <Link to="/announcements/new" className="text-brand-700 hover:underline">
              Post a notice
            </Link>
          ) : null}
          <Link to="/announcements" className="text-brand-700 hover:underline">
            All announcements
          </Link>
        </span>
      </div>

      <div className="mt-2">
        {latest.length === 0 ? (
          <p className="rounded-card border border-line bg-surface px-4 py-6 text-center text-sm text-ink-muted">
            Nothing has been announced lately.{" "}
            <Link to="/announcements" className="text-brand-700 hover:underline">
              Search older announcements
            </Link>
          </p>
        ) : (
          <ul className="space-y-2">
            {latest.map((notice) => (
              <li
                key={notice.id}
                className={`rounded-card border bg-surface ${
                  notice.unread ? "border-brand-200" : "border-line"
                }`}
              >
                <Link
                  to={`/announcements/${notice.id}`}
                  className="block px-4 py-3 hover:bg-canvas focus-visible:bg-canvas"
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <p className="min-w-0 text-sm font-medium">
                      {/* The dot never carries the meaning alone -- colour is
                          not an accessible signal, so the word is there too. */}
                      {notice.unread ? (
                        <span className="mr-2 inline-flex items-center gap-1 align-middle text-xs font-semibold text-brand-700">
                          <span aria-hidden="true" className="size-2 rounded-full bg-brand-700" />
                          New
                        </span>
                      ) : null}
                      {notice.subject}
                    </p>
                    <StatusPill tone="neutral">{audienceLabel(notice)}</StatusPill>
                  </div>
                  <p className="mt-1 line-clamp-2 text-sm text-ink-muted">{notice.body}</p>
                  <p className="mt-1.5 text-xs text-ink-muted">
                    {posterLabel(notice)}
                    {notice.published_at ? ` · ${dayLabel(notice.published_at)}` : ""}
                    {notice.attachments.length > 0
                      ? ` · ${notice.attachments.length} file${
                          notice.attachments.length === 1 ? "" : "s"
                        }`
                      : ""}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

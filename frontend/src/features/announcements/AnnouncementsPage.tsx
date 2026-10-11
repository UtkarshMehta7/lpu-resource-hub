import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { ButtonLink } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { SkeletonList } from "@/components/ui/Skeleton";
import { StatusPill } from "@/components/ui/StatusPill";
import { useAuth } from "@/features/auth/authContext";

import { fetchAnnouncements, type Announcement } from "./api";
import { audienceLabel, posterLabel, STATUS_LABEL, STATUS_TONE } from "./labels";

const FIELD = "mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm";

/** Roles that may post. Mirrors Permission.ANNOUNCEMENT_POST on the server. */
const CAN_POST = new Set(["research_coordinator", "dean_of_research", "admin"]);

function dateLabel(value: string | null): string {
  if (!value) return "Not yet published";
  return new Date(value).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function NoticeCard({ notice }: { notice: Announcement }) {
  const attachments = notice.attachments.length;
  const links = notice.links.length;

  return (
    <li className="rounded-card border border-line bg-surface">
      <Link
        to={`/announcements/${notice.id}`}
        className="block px-4 py-3 hover:bg-canvas focus-visible:bg-canvas"
      >
        <div className="flex flex-wrap items-start justify-between gap-2">
          <p className="min-w-0 font-medium">
            {/* The dot carries no meaning on its own, so the word "New" sits
                beside it -- colour alone is not an accessible signal. */}
            {notice.unread ? (
              <span className="mr-2 inline-flex items-center gap-1 align-middle text-xs font-semibold text-brand-700">
                <span aria-hidden="true" className="size-2 rounded-full bg-brand-700" />
                New
              </span>
            ) : null}
            {notice.subject}
          </p>
          <div className="flex shrink-0 items-center gap-2">
            {notice.status === "published" ? null : (
              <StatusPill tone={STATUS_TONE[notice.status]}>
                {STATUS_LABEL[notice.status]}
              </StatusPill>
            )}
            <StatusPill tone="neutral">{audienceLabel(notice)}</StatusPill>
          </div>
        </div>
        <p className="mt-1 line-clamp-2 text-sm text-ink-muted">{notice.body}</p>
        <p className="mt-2 text-xs text-ink-muted">
          {posterLabel(notice)} · {dateLabel(notice.published_at)}
          {attachments > 0 ? ` · ${attachments} file${attachments === 1 ? "" : "s"}` : ""}
          {links > 0 ? ` · ${links} link${links === 1 ? "" : "s"}` : ""}
        </p>
      </Link>
    </li>
  );
}

/**
 * The searchable history of everything announced to you.
 *
 * The LATEST notices are on the dashboard, which is where everybody meets
 * the board (ADR 0038). This page is the archive behind it -- for finding
 * the circular from last term, which is why the search box is the first
 * thing on it and there is no attempt to repeat the dashboard's job.
 */
export function AnnouncementsPage({ mine = false }: { mine?: boolean }) {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const q = searchParams.get("q") ?? "";
  const unreadOnly = searchParams.get("unread_only") === "true";
  const page = Number(searchParams.get("page") ?? "1");

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    setSearchParams(next);
  };

  const { data, isPending, isError } = useQuery({
    queryKey: ["announcements", { q, unreadOnly, page, mine }],
    queryFn: () =>
      fetchAnnouncements({
        q: q || undefined,
        unread_only: unreadOnly || undefined,
        mine: mine || undefined,
        page,
      }),
  });

  const canPost = user ? CAN_POST.has(user.role) : false;
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div>
      <PageHeader
        title={mine ? "My announcements" : "All announcements"}
        description={
          mine
            ? "Notices you have posted, including drafts nobody else can see yet."
            : "Everything the university and your department have announced to you, oldest kept as well as newest. The latest few are on your dashboard."
        }
        actions={
          <>
            {canPost && !mine ? (
              <ButtonLink to="/announcements/mine" variant="secondary">
                My announcements
              </ButtonLink>
            ) : null}
            {canPost ? <ButtonLink to="/announcements/new">Post a notice</ButtonLink> : null}
          </>
        }
      />

      <div className="grid gap-3 sm:grid-cols-[1fr_12rem]">
        <div>
          <label htmlFor="announcement-q" className="block text-sm font-medium">
            Search
          </label>
          <input
            id="announcement-q"
            type="search"
            defaultValue={q}
            placeholder="Subject or text"
            onChange={(event) => setParam("q", event.target.value)}
            className={FIELD}
          />
        </div>
        <div>
          <label htmlFor="announcement-show" className="block text-sm font-medium">
            Show
          </label>
          <select
            id="announcement-show"
            value={unreadOnly ? "unread" : "all"}
            onChange={(event) =>
              setParam("unread_only", event.target.value === "unread" ? "true" : "")
            }
            className={FIELD}
          >
            <option value="all">Everything</option>
            <option value="unread">Unread only</option>
          </select>
        </div>
      </div>

      <div className="mt-6">
        {isPending ? <SkeletonList rows={4} /> : null}
        {isError ? (
          <EmptyState
            title="The notice board could not be loaded"
            description="Please try again in a moment."
          />
        ) : null}
        {data && data.items.length === 0 ? (
          <EmptyState
            title={
              q ? "Nothing matches that" : unreadOnly ? "Nothing unread" : "No announcements yet"
            }
            description={
              q
                ? "Try a word from the subject, or clear the search to see everything."
                : unreadOnly
                  ? "You have read everything addressed to you."
                  : mine
                    ? "Notices you post will appear here."
                    : "When the university or your department posts a notice, it will appear here."
            }
          />
        ) : null}
        {data && data.items.length > 0 ? (
          <ul className="space-y-3">
            {data.items.map((notice) => (
              <NoticeCard key={notice.id} notice={notice} />
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

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { SkeletonList } from "@/components/ui/Skeleton";
import { StatusPill } from "@/components/ui/StatusPill";
import { useAuth } from "@/features/auth/authContext";

import {
  deleteAnnouncement,
  downloadAnnouncementAttachment,
  fetchAnnouncement,
  fileSizeLabel,
  isImage,
  loadAnnouncementImage,
  markAnnouncementRead,
  publishAnnouncement,
  withdrawAnnouncement,
  type Announcement,
  type AnnouncementAttachment,
} from "./api";
import { audienceLabel, posterLabel, STATUS_LABEL, STATUS_TONE } from "./labels";

/**
 * An attached image, shown on the page.
 *
 * The bytes are fetched through the API client and rendered from a blob URL
 * rather than pointing an `<img src>` at the download route: that route is
 * authenticated, and an `<img>` sends no Authorization header. It also keeps
 * the server's `Content-Disposition: attachment` guarantee intact, so nothing
 * uploaded here is ever rendered as a document on this origin.
 */
function AttachedImage({
  announcementId,
  attachment,
}: {
  announcementId: string;
  attachment: AnnouncementAttachment;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    loadAnnouncementImage(announcementId, attachment)
      .then((value) => {
        if (cancelled) {
          URL.revokeObjectURL(value);
          return;
        }
        objectUrl = value;
        setUrl(value);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
      // The component owns the URL it created, so it releases it. Without
      // this the blob stays alive for the life of the tab.
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [announcementId, attachment]);

  if (failed) return null;
  if (!url) {
    return <div className="h-40 w-full animate-pulse rounded-md bg-canvas" />;
  }
  return (
    <img
      src={url}
      alt={attachment.filename}
      className="max-h-96 w-auto rounded-md border border-line"
    />
  );
}

function Attachments({ notice }: { notice: Announcement }) {
  if (notice.attachments.length === 0) return null;
  const images = notice.attachments.filter(isImage);
  const files = notice.attachments.filter((item) => !isImage(item));

  return (
    <section className="mt-6">
      <h2 className="text-sm font-semibold">Attachments</h2>
      {images.length > 0 ? (
        <div className="mt-3 space-y-3">
          {images.map((attachment) => (
            <AttachedImage key={attachment.id} announcementId={notice.id} attachment={attachment} />
          ))}
        </div>
      ) : null}
      <ul className="mt-3 space-y-2">
        {[...images, ...files].map((attachment) => (
          <li key={attachment.id}>
            <button
              type="button"
              onClick={() => void downloadAnnouncementAttachment(notice.id, attachment)}
              className="flex w-full items-center justify-between gap-3 rounded-md border border-line bg-surface px-3 py-2 text-left text-sm hover:bg-canvas"
            >
              <span className="min-w-0 truncate font-medium">{attachment.filename}</span>
              <span className="shrink-0 text-xs text-ink-muted">
                {fileSizeLabel(attachment.byte_size)} · Download
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Links({ notice }: { notice: Announcement }) {
  if (notice.links.length === 0) return null;
  return (
    <section className="mt-6">
      <h2 className="text-sm font-semibold">Links</h2>
      <ul className="mt-3 space-y-2">
        {notice.links.map((link) => (
          <li key={link.id}>
            <a
              href={link.url}
              // A notice is written by somebody else and read by everyone, so
              // its links leave this tab without handing the opener a
              // reference back to it.
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-brand-700 underline underline-offset-2 hover:text-brand-800"
            >
              {link.label || link.url}
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function AnnouncementDetailPage() {
  const { announcementId = "" } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState<"withdraw" | "delete" | null>(null);

  const { data, isPending, isError } = useQuery({
    queryKey: ["announcement", announcementId],
    queryFn: () => fetchAnnouncement(announcementId),
    enabled: Boolean(announcementId),
  });

  const unread = data?.unread ?? false;

  useEffect(() => {
    // Opening it IS reading it. Only when it is actually unread, so a reread
    // does not post on every render.
    if (!unread) return;
    markAnnouncementRead(announcementId)
      .then(() => {
        void queryClient.invalidateQueries({ queryKey: ["announcements"] });
        void queryClient.invalidateQueries({ queryKey: ["announcements", "unread-count"] });
        void queryClient.invalidateQueries({ queryKey: ["announcement", announcementId] });
      })
      // A failed read marker is not worth interrupting the reader for; the
      // badge simply stays until the next time.
      .catch(() => undefined);
  }, [announcementId, unread, queryClient]);

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["announcements"] });
    void queryClient.invalidateQueries({ queryKey: ["announcement", announcementId] });
  };

  const publish = useMutation({
    mutationFn: () => publishAnnouncement(announcementId),
    onSuccess: invalidate,
  });
  const withdraw = useMutation({
    mutationFn: () => withdrawAnnouncement(announcementId),
    onSuccess: () => {
      invalidate();
      setConfirming(null);
    },
  });
  const remove = useMutation({
    // Wrapped rather than passed by reference: a mutationFn is called with
    // more than one argument, and forwarding them all breaks assertions for
    // reasons that look like the click never happened.
    mutationFn: () => deleteAnnouncement(announcementId),
    onSuccess: () => {
      invalidate();
      setConfirming(null);
      void navigate("/announcements");
    },
  });

  if (isPending) return <SkeletonList rows={3} />;
  if (isError || !data) {
    return (
      <EmptyState
        title="Announcement not found"
        description="It may have been withdrawn, or it was never addressed to you."
        actionLabel="Back to the board"
        actionTo="/announcements"
      />
    );
  }

  const isAuthor = data.posted_by !== null && data.posted_by === user?.id;
  const isAdmin = user?.role === "admin";
  const canPublish = isAuthor && data.status === "draft";
  const canEdit = isAuthor && data.status === "draft";
  const canWithdraw = data.status === "published" && (isAuthor || isAdmin);
  const canDelete =
    (data.status === "draft" && isAuthor) || (data.status === "withdrawn" && isAdmin);

  return (
    <div>
      <PageHeader
        title={data.subject}
        description={
          <>
            {posterLabel(data)} · {audienceLabel(data)}
            {data.published_at
              ? ` · ${new Date(data.published_at).toLocaleDateString(undefined, {
                  day: "numeric",
                  month: "long",
                  year: "numeric",
                })}`
              : " · not yet published"}
          </>
        }
        actions={
          <>
            {data.status === "published" ? null : (
              <StatusPill tone={STATUS_TONE[data.status]}>{STATUS_LABEL[data.status]}</StatusPill>
            )}
            {canEdit ? (
              <Link
                to={`/announcements/${data.id}/edit`}
                className="rounded-md border border-line bg-surface px-3 py-2 text-sm font-medium hover:bg-canvas"
              >
                Edit
              </Link>
            ) : null}
            {canPublish ? (
              <Button onClick={() => publish.mutate()} disabled={publish.isPending}>
                {publish.isPending ? "Publishing…" : "Publish"}
              </Button>
            ) : null}
            {canWithdraw ? (
              <Button variant="secondary" onClick={() => setConfirming("withdraw")}>
                Withdraw
              </Button>
            ) : null}
            {canDelete ? (
              <Button variant="secondary" onClick={() => setConfirming("delete")}>
                Delete
              </Button>
            ) : null}
          </>
        }
      />

      {data.status === "draft" ? (
        <p className="mb-6 rounded-card border border-line bg-canvas px-4 py-3 text-sm text-ink-muted">
          This is a draft. Nobody else can see it. Attach any files first — a published notice
          cannot be changed.
        </p>
      ) : null}

      <div className="rounded-card border border-line bg-surface px-4 py-4">
        <p className="whitespace-pre-wrap text-sm">{data.body}</p>
      </div>

      <Links notice={data} />
      <Attachments notice={data} />

      <ConfirmDialog
        open={confirming === "withdraw"}
        title="Withdraw this announcement?"
        description="It will come off the board for everyone. The record of it stays."
        // Not "Withdraw": that is the label on the button that OPENED this
        // dialog, and two controls reading the same word on one screen is
        // what made four tests in this repo match the wrong element -- a
        // reader has the same trouble.
        confirmLabel="Withdraw it"
        isConfirming={withdraw.isPending}
        onConfirm={() => withdraw.mutate()}
        onCancel={() => setConfirming(null)}
      />
      <ConfirmDialog
        open={confirming === "delete"}
        title="Delete this announcement?"
        description="This cannot be undone."
        confirmLabel="Delete it"
        isConfirming={remove.isPending}
        onConfirm={() => remove.mutate()}
        onCancel={() => setConfirming(null)}
      />
    </div>
  );
}

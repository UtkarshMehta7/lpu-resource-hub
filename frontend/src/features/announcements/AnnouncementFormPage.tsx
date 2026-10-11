import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useFieldArray, useForm } from "react-hook-form";
import { useNavigate, useParams } from "react-router-dom";
import { z } from "zod";

import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/PageHeader";
import { SkeletonList } from "@/components/ui/Skeleton";
import { useAuth } from "@/features/auth/authContext";
import { toApiError } from "@/lib/api/errors";

import {
  createAnnouncement,
  fetchAnnouncement,
  fileSizeLabel,
  removeAnnouncementAttachment,
  updateAnnouncement,
  uploadAnnouncementAttachment,
  type Announcement,
} from "./api";

const schema = z.object({
  subject: z.string().trim().min(1, "A subject is required").max(200),
  body: z.string().trim().min(1, "Say what the notice is about").max(20000),
  links: z
    .array(
      z.object({
        label: z.string().max(200),
        url: z
          .string()
          .max(2000)
          .refine(
            (v) => !v || /^https?:\/\//.test(v),
            "A link must start with http:// or https://",
          ),
      }),
    )
    .max(10),
});

type FormValues = z.infer<typeof schema>;

const FIELD = "mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm";
const ACCEPT = ".pdf,.png,.jpg,.jpeg,.docx,.zip,.rar";

/**
 * Who this notice will reach, said before it is written rather than after.
 *
 * The reach is derived from the poster on the server, so there is nothing to
 * choose here -- but a coordinator who believes they are addressing the whole
 * university is the one misunderstanding worth spending four lines to prevent.
 */
function ReachNotice() {
  const { user } = useAuth();
  const institutionWide = user?.role === "admin" || user?.role === "dean_of_research";
  return (
    <p className="rounded-card border border-line bg-canvas px-4 py-3 text-sm text-ink-muted">
      {institutionWide
        ? "This notice will be addressed to everyone at the university."
        : "This notice will be addressed to your own department. Everyone in it will see it, whatever their role."}
    </p>
  );
}

/**
 * Files, which can only be attached once the notice exists as a draft.
 *
 * An upload is multipart against a saved row, so there is no way to attach
 * anything to a notice that has not been created yet -- which is exactly why
 * a draft stage exists rather than one create-and-publish form.
 */
function AttachmentEditor({ notice }: { notice: Announcement }) {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ["announcement", notice.id] }),
      queryClient.invalidateQueries({ queryKey: ["announcements"] }),
    ]);

  const upload = async (file: File) => {
    setBusy(true);
    setError(null);
    try {
      await uploadAnnouncementAttachment(notice.id, file);
      await refresh();
    } catch (caught) {
      setError(toApiError(caught).message);
    } finally {
      setBusy(false);
    }
  };

  const drop = async (attachmentId: string) => {
    setBusy(true);
    setError(null);
    try {
      await removeAnnouncementAttachment(notice.id, attachmentId);
      await refresh();
    } catch (caught) {
      setError(toApiError(caught).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="mt-8">
      <h2 className="text-sm font-semibold">Attachments</h2>
      <p className="mt-1 text-sm text-ink-muted">
        PDF, images, Word documents and archives, up to 5 MB each. Add them before publishing — a
        published notice cannot be changed.
      </p>
      {notice.attachments.length > 0 ? (
        <ul className="mt-3 space-y-2">
          {notice.attachments.map((attachment) => (
            <li
              key={attachment.id}
              className="flex items-center justify-between gap-3 rounded-md border border-line bg-surface px-3 py-2 text-sm"
            >
              <span className="min-w-0 truncate">{attachment.filename}</span>
              <span className="flex shrink-0 items-center gap-3">
                <span className="text-xs text-ink-muted">
                  {fileSizeLabel(attachment.byte_size)}
                </span>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void drop(attachment.id)}
                  className="text-xs font-medium text-red-700 hover:underline disabled:opacity-40"
                >
                  Remove
                </button>
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      <label htmlFor="announcement-file" className="mt-3 block text-sm font-medium">
        Add a file
      </label>
      <input
        id="announcement-file"
        type="file"
        accept={ACCEPT}
        disabled={busy}
        className={FIELD}
        onChange={(event) => {
          const file = event.target.files?.[0];
          // Cleared so choosing the same file twice in a row still fires.
          event.target.value = "";
          if (file) void upload(file);
        }}
      />
      {error ? <p className="mt-2 text-sm text-red-700">{error}</p> : null}
    </section>
  );
}

/** Write a notice, or edit one that is still a draft. */
export function AnnouncementFormPage() {
  const { announcementId } = useParams();
  const isEditing = Boolean(announcementId);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const existing = useQuery({
    queryKey: ["announcement", announcementId],
    queryFn: () => fetchAnnouncement(announcementId ?? ""),
    enabled: isEditing,
  });

  const {
    register,
    control,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { subject: "", body: "", links: [] },
  });
  const links = useFieldArray({ control, name: "links" });

  useEffect(() => {
    if (!existing.data) return;
    reset({
      subject: existing.data.subject,
      body: existing.data.body,
      links: existing.data.links.map((link) => ({ label: link.label ?? "", url: link.url })),
    });
  }, [existing.data, reset]);

  const submit = handleSubmit(async (values) => {
    setError(null);
    const payload = {
      subject: values.subject,
      body: values.body,
      links: values.links
        .filter((link) => link.url.trim() !== "")
        .map((link) => ({ label: link.label.trim() || null, url: link.url.trim() })),
    };
    try {
      const saved = isEditing
        ? await updateAnnouncement(announcementId ?? "", payload)
        : await createAnnouncement(payload);
      await queryClient.invalidateQueries({ queryKey: ["announcements"] });
      void navigate(`/announcements/${saved.id}`, { replace: true });
    } catch (caught) {
      setError(toApiError(caught).message);
    }
  });

  if (isEditing && existing.isPending) return <SkeletonList rows={3} />;

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader
        title={isEditing ? "Edit the draft" : "Post a notice"}
        description="It is saved as a draft first, so you can attach files and read it over before anyone else sees it."
      />

      <ReachNotice />

      <form onSubmit={(event) => void submit(event)} className="mt-6 space-y-5" noValidate>
        <div>
          <label htmlFor="subject" className="block text-sm font-medium">
            Subject
          </label>
          <input
            id="subject"
            className={FIELD}
            placeholder="Invention disclosure window closes on Friday"
            {...register("subject")}
          />
          {errors.subject ? (
            <p className="mt-1 text-xs text-red-700">{errors.subject.message}</p>
          ) : null}
        </div>

        <div>
          <label htmlFor="body" className="block text-sm font-medium">
            Notice
          </label>
          <textarea id="body" rows={8} className={FIELD} {...register("body")} />
          {errors.body ? <p className="mt-1 text-xs text-red-700">{errors.body.message}</p> : null}
        </div>

        <fieldset>
          <legend className="text-sm font-medium">Links</legend>
          <p className="mt-1 text-sm text-ink-muted">
            A labelled link reads better than a URL pasted into the notice.
          </p>
          <ul className="mt-3 space-y-3">
            {links.fields.map((field, index) => (
              <li key={field.id} className="grid gap-2 sm:grid-cols-[1fr_1.5fr_auto]">
                <input
                  aria-label={`Link ${index + 1} label`}
                  placeholder="The form"
                  className={FIELD}
                  {...register(`links.${index}.label`)}
                />
                <div>
                  <input
                    aria-label={`Link ${index + 1} address`}
                    placeholder="https://example.org/form"
                    className={FIELD}
                    {...register(`links.${index}.url`)}
                  />
                  {errors.links?.[index]?.url ? (
                    <p className="mt-1 text-xs text-red-700">{errors.links[index]?.url?.message}</p>
                  ) : null}
                </div>
                <button
                  type="button"
                  onClick={() => links.remove(index)}
                  className="mt-1 self-start rounded-md border border-line bg-surface px-3 py-2 text-sm font-medium hover:bg-canvas"
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
          {links.fields.length < 10 ? (
            <Button
              variant="secondary"
              size="sm"
              className="mt-3"
              onClick={() => links.append({ label: "", url: "" })}
            >
              Add a link
            </Button>
          ) : null}
        </fieldset>

        {error ? <p className="text-sm text-red-700">{error}</p> : null}

        <div className="flex items-center gap-3">
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Saving…" : isEditing ? "Save the draft" : "Save as a draft"}
          </Button>
          <Button variant="secondary" onClick={() => void navigate("/announcements")}>
            Cancel
          </Button>
        </div>
      </form>

      {isEditing && existing.data ? <AttachmentEditor notice={existing.data} /> : null}
    </div>
  );
}

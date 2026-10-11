import type { Role } from "@/features/auth/types";
import type { Page } from "@/features/directory/api";
import { apiClient } from "@/lib/api/client";

/**
 * These types are hand-written mirrors of the Pydantic schemas in
 * backend/app/modules/announcements/schemas.py, and they have drifted twice
 * elsewhere in this codebase. Change one and change the other in the same
 * commit.
 */

export type AnnouncementAudience = "institution" | "department";
export type AnnouncementStatus = "draft" | "published" | "withdrawn";

export interface AnnouncementLink {
  id: string;
  label: string | null;
  url: string;
}

export interface AnnouncementAttachment {
  id: string;
  filename: string;
  content_type: string;
  byte_size: number;
}

export interface Announcement {
  id: string;
  subject: string;
  body: string;
  audience: AnnouncementAudience;
  department_id: string | null;
  department_name: string | null;
  posted_by: string | null;
  posted_by_name: string;
  posted_by_role: Role;
  status: AnnouncementStatus;
  published_at: string | null;
  links: AnnouncementLink[];
  attachments: AnnouncementAttachment[];
  unread: boolean;
  created_at: string;
  updated_at: string;
}

/**
 * No `audience` here, and there must never be one.
 *
 * The reach is derived from the poster on the server (announcements/
 * policies.py: reach_of), so a coordinator addresses their own department and
 * cannot name another. A field here would be ignored, which is worse than
 * absent: the form would imply a choice the server does not offer.
 */
export interface AnnouncementInput {
  subject: string;
  body: string;
  links: { label: string | null; url: string }[];
}

function clean(params: object): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== "" && v !== false),
  );
}

export async function fetchAnnouncements(filters: {
  q?: string;
  unread_only?: boolean;
  mine?: boolean;
  page?: number;
}): Promise<Page<Announcement>> {
  const response = await apiClient.get<Page<Announcement>>("/api/v1/announcements", {
    params: clean(filters),
  });
  return response.data;
}

export async function fetchAnnouncement(id: string): Promise<Announcement> {
  const response = await apiClient.get<Announcement>(`/api/v1/announcements/${id}`);
  return response.data;
}

export async function fetchUnreadCount(): Promise<number> {
  const response = await apiClient.get<{ unread: number }>("/api/v1/announcements/unread-count");
  return response.data.unread;
}

export async function createAnnouncement(input: AnnouncementInput): Promise<Announcement> {
  const response = await apiClient.post<Announcement>("/api/v1/announcements", input);
  return response.data;
}

export async function updateAnnouncement(
  id: string,
  input: Partial<AnnouncementInput>,
): Promise<Announcement> {
  const response = await apiClient.patch<Announcement>(`/api/v1/announcements/${id}`, input);
  return response.data;
}

export async function publishAnnouncement(id: string): Promise<Announcement> {
  const response = await apiClient.post<Announcement>(`/api/v1/announcements/${id}/publish`);
  return response.data;
}

export async function withdrawAnnouncement(id: string): Promise<Announcement> {
  const response = await apiClient.post<Announcement>(`/api/v1/announcements/${id}/withdraw`);
  return response.data;
}

export async function deleteAnnouncement(id: string): Promise<void> {
  await apiClient.delete(`/api/v1/announcements/${id}`);
}

export async function markAnnouncementRead(id: string): Promise<void> {
  await apiClient.post(`/api/v1/announcements/${id}/read`);
}

export async function uploadAnnouncementAttachment(id: string, file: File): Promise<Announcement> {
  const form = new FormData();
  form.append("file", file);
  const response = await apiClient.post<Announcement>(
    `/api/v1/announcements/${id}/attachments`,
    form,
  );
  return response.data;
}

export async function removeAnnouncementAttachment(
  id: string,
  attachmentId: string,
): Promise<void> {
  await apiClient.delete(`/api/v1/announcements/${id}/attachments/${attachmentId}`);
}

async function fetchAttachmentBlob(announcementId: string, attachmentId: string): Promise<Blob> {
  const response = await apiClient.get<Blob>(
    `/api/v1/announcements/${announcementId}/attachments/${attachmentId}`,
    { responseType: "blob" },
  );
  return response.data;
}

/**
 * Fetch the bytes and hand the browser a download.
 *
 * Deliberately not an `<a href>`: the download route is authenticated like
 * every other, and a plain link carries no Authorization header. A
 * departmental notice's attachment must not be reachable by whoever holds
 * its URL.
 */
export async function downloadAnnouncementAttachment(
  announcementId: string,
  attachment: AnnouncementAttachment,
): Promise<void> {
  const blob = await fetchAttachmentBlob(announcementId, attachment.id);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = attachment.filename;
  document.body.append(link);
  link.click();
  link.remove();
  // Revoked on the next tick rather than immediately: Safari cancels a
  // download whose blob URL is released in the same frame as the click.
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

/**
 * A blob URL for an image attachment, so a poster can be seen on the page.
 *
 * The server always answers `Content-Disposition: attachment` with
 * `nosniff`, which is what stops an uploaded file running as the application
 * on this origin. Pointing an `<img src>` at that route would be sending the
 * request without the Authorization header anyway; fetching the bytes and
 * rendering them from a blob keeps both properties. The caller owns the URL
 * and must revoke it.
 */
export async function loadAnnouncementImage(
  announcementId: string,
  attachment: AnnouncementAttachment,
): Promise<string> {
  const blob = await fetchAttachmentBlob(announcementId, attachment.id);
  return URL.createObjectURL(blob);
}

export function isImage(attachment: AnnouncementAttachment): boolean {
  return attachment.content_type === "image/png" || attachment.content_type === "image/jpeg";
}

export function fileSizeLabel(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

import type { Role } from "@/features/auth/types";
import { apiClient } from "@/lib/api/client";

/** Mirrors the backend's messages schemas (app/modules/messages/schemas.py). */
export type SubjectKind = "collaboration" | "project";

export interface Participant {
  user_id: string;
  full_name: string;
  registration_number: string;
  role: Role;
}

export interface Conversation {
  id: string;
  subject_kind: SubjectKind;
  subject_id: string;
  title: string;
  participants: Participant[];
  /** False once the collaboration behind it has ended: readable, not writable. */
  open: boolean;
  unread_count: number;
  last_message_at: string | null;
  preview: string | null;
  created_at: string;
}

export interface Attachment {
  id: string;
  filename: string;
  content_type: string;
  byte_size: number;
}

export interface Message {
  id: string;
  conversation_id: string;
  sender_id: string;
  sender_name: string;
  sender_registration_number: string;
  /** null when a moderator has hidden it; the message keeps its place. */
  body: string | null;
  hidden: boolean;
  created_at: string;
  /** Empty for a plain message, and empty for a hidden one: hiding withholds
   *  what was shared as well as what was said. */
  attachments: Attachment[];
}

/**
 * What the file picker offers, mirroring app/modules/uploads/validation.py.
 *
 * The browser treats this as a hint only, so it is a convenience and never
 * the check: the server decides from the file's own bytes, and a renamed
 * executable is refused there whatever this list says.
 */
export const ACCEPTED_UPLOAD_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "image/png",
  "image/jpeg",
  "application/vnd.rar",
  "application/zip",
].join(",");

/** Matches `upload_max_bytes`. Checked here so an oversized file is refused
 *  before it is uploaded, and again on the server, which is the authority. */
export const MAX_UPLOAD_BYTES = 5 * 1024 * 1024;

export interface MessagePage {
  items: Message[];
  /** Pass back as `after` to fetch only what has arrived since. */
  next_after: string | null;
}

export async function fetchConversations(): Promise<Conversation[]> {
  const response = await apiClient.get<Conversation[]>("/api/v1/me/conversations");
  return response.data;
}

export async function fetchUnreadTotal(): Promise<number> {
  const response = await apiClient.get<number>("/api/v1/me/conversations/unread-count");
  return response.data;
}

export async function fetchConversation(conversationId: string): Promise<Conversation> {
  const response = await apiClient.get<Conversation>(`/api/v1/conversations/${conversationId}`);
  return response.data;
}

export async function fetchMessages(
  conversationId: string,
  after?: string | null,
): Promise<MessagePage> {
  const response = await apiClient.get<MessagePage>(
    `/api/v1/conversations/${conversationId}/messages`,
    { params: after ? { after } : undefined },
  );
  return response.data;
}

export async function sendMessage(conversationId: string, body: string): Promise<Message> {
  const response = await apiClient.post<Message>(
    `/api/v1/conversations/${conversationId}/messages`,
    { body },
  );
  return response.data;
}

/** Share a file in a thread. It arrives as a message, with the draft text as
 *  its caption, so it obeys every rule an ordinary message does. */
export async function sendAttachment(
  conversationId: string,
  file: File,
  caption: string,
): Promise<Message> {
  const form = new FormData();
  form.append("file", file);
  form.append("caption", caption);
  const response = await apiClient.post<Message>(
    `/api/v1/conversations/${conversationId}/attachments`,
    form,
  );
  return response.data;
}

/**
 * Fetch the bytes and hand the browser a download.
 *
 * Deliberately not an `<a href>`: the download route is authenticated like
 * every other, and a plain link carries no Authorization header. That is the
 * whole point — an attachment in a private thread must not be reachable by
 * whoever holds its URL.
 */
export async function downloadAttachment(
  conversationId: string,
  attachment: Attachment,
): Promise<void> {
  const response = await apiClient.get<Blob>(
    `/api/v1/conversations/${conversationId}/attachments/${attachment.id}`,
    { responseType: "blob" },
  );
  const url = URL.createObjectURL(response.data);
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

export async function markConversationRead(conversationId: string): Promise<void> {
  await apiClient.post(`/api/v1/conversations/${conversationId}/read`);
}

/** Opens the team thread for a project, or returns the existing one. */
export async function openProjectConversation(projectId: string): Promise<Conversation> {
  const response = await apiClient.post<Conversation>(`/api/v1/projects/${projectId}/conversation`);
  return response.data;
}

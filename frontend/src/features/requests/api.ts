import type { Role } from "@/features/auth/types";
import type { Page } from "@/features/directory/api";
import { apiClient } from "@/lib/api/client";

/**
 * Hand-written mirrors of backend/app/modules/requests/schemas.py. They have
 * drifted twice elsewhere in this codebase; change one and change the other
 * in the same commit.
 */

export type RequestCategory = "academic" | "facility" | "funding" | "administrative" | "other";

export type RequestStatus = "submitted" | "under_review" | "resolved" | "declined" | "withdrawn";

export interface RequestAttachment {
  id: string;
  filename: string;
  content_type: string;
  byte_size: number;
}

/** Somebody the caller may address. Built from the same filter the submit enforces. */
export interface RequestRecipient {
  id: string;
  full_name: string;
  registration_number: string;
  role: Role;
  department_id: string | null;
  department_name: string | null;
}

export interface PersonalRequest {
  id: string;
  subject: string;
  body: string;
  category: RequestCategory;
  status: RequestStatus;

  sender_id: string;
  sender_name: string;
  sender_registration_number: string;
  sender_role: Role;

  /** Null once the recipient's account is gone; the name and role still read. */
  recipient_id: string | null;
  recipient_name: string;
  recipient_role: Role;

  resolution_note: string | null;
  decided_at: string | null;

  attachments: RequestAttachment[];
  /** Computed per reader, so the interface cannot offer a move the service refuses. */
  next_statuses: RequestStatus[];
  viewer_is_sender: boolean;

  created_at: string;
  updated_at: string;
}

export interface RequestInput {
  recipient_id: string;
  subject: string;
  body: string;
  category: RequestCategory;
}

function clean(params: object): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== "" && v !== false),
  );
}

export async function fetchRecipients(): Promise<RequestRecipient[]> {
  const response = await apiClient.get<RequestRecipient[]>("/api/v1/requests/recipients");
  return response.data;
}

export async function fetchSentRequests(filters: {
  status?: RequestStatus;
  page?: number;
}): Promise<Page<PersonalRequest>> {
  const response = await apiClient.get<Page<PersonalRequest>>("/api/v1/me/requests", {
    params: clean(filters),
  });
  return response.data;
}

export async function fetchRequestInbox(filters: {
  status?: RequestStatus;
  page?: number;
}): Promise<Page<PersonalRequest>> {
  const response = await apiClient.get<Page<PersonalRequest>>("/api/v1/requests/inbox", {
    params: clean(filters),
  });
  return response.data;
}

export async function fetchWaitingCount(): Promise<number> {
  const response = await apiClient.get<{ waiting: number }>("/api/v1/requests/inbox/count");
  return response.data.waiting;
}

export async function fetchRequest(id: string): Promise<PersonalRequest> {
  const response = await apiClient.get<PersonalRequest>(`/api/v1/requests/${id}`);
  return response.data;
}

export async function submitRequest(input: RequestInput): Promise<PersonalRequest> {
  const response = await apiClient.post<PersonalRequest>("/api/v1/requests", input);
  return response.data;
}

export async function changeRequestStatus(
  id: string,
  status: RequestStatus,
  note?: string,
): Promise<PersonalRequest> {
  const response = await apiClient.post<PersonalRequest>(`/api/v1/requests/${id}/status`, {
    status,
    note: note ?? null,
  });
  return response.data;
}

export async function uploadRequestAttachment(id: string, file: File): Promise<PersonalRequest> {
  const form = new FormData();
  form.append("file", file);
  const response = await apiClient.post<PersonalRequest>(
    `/api/v1/requests/${id}/attachments`,
    form,
  );
  return response.data;
}

export async function removeRequestAttachment(id: string, attachmentId: string): Promise<void> {
  await apiClient.delete(`/api/v1/requests/${id}/attachments/${attachmentId}`);
}

/**
 * Fetch the bytes and hand the browser a download.
 *
 * Deliberately not an `<a href>`: the route is authenticated like every
 * other, and a plain link carries no Authorization header. A document
 * attached to somebody's request must not be reachable by whoever holds
 * its URL.
 */
export async function downloadRequestAttachment(
  id: string,
  attachment: RequestAttachment,
): Promise<void> {
  const response = await apiClient.get<Blob>(
    `/api/v1/requests/${id}/attachments/${attachment.id}`,
    { responseType: "blob" },
  );
  const url = URL.createObjectURL(response.data);
  const link = document.createElement("a");
  link.href = url;
  link.download = attachment.filename;
  document.body.append(link);
  link.click();
  link.remove();
  // Revoked on the next tick: Safari cancels a download whose blob URL is
  // released in the same frame as the click.
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function fileSizeLabel(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

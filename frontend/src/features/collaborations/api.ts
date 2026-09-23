import type { Role } from "@/features/auth/types";
import { apiClient } from "@/lib/api/client";

export type CollaborationStatus = "pending" | "accepted" | "declined" | "cancelled";
export type Box = "inbox" | "sent";

export const COLLABORATION_STATUS_LABEL: Record<CollaborationStatus, string> = {
  pending: "Pending",
  accepted: "Accepted",
  declined: "Declined",
  cancelled: "Cancelled",
};

interface Party {
  id: string;
  full_name: string;
  registration_number: string;
  role: Role;
}

/** Matches the backend's CollaborationRead schema. */
export interface CollaborationRequest {
  id: string;
  sender: Party;
  recipient: Party;
  project_id: string | null;
  project_title: string | null;
  message: string;
  status: CollaborationStatus;
  responded_at: string | null;
  created_at: string;
}

export async function sendCollaborationRequest(input: {
  recipient_id: string;
  project_id?: string | null;
  message: string;
}): Promise<CollaborationRequest> {
  const response = await apiClient.post<CollaborationRequest>("/api/v1/collaborations", input);
  return response.data;
}

export async function fetchMyCollaborations(
  box: Box,
  status?: CollaborationStatus,
): Promise<CollaborationRequest[]> {
  const response = await apiClient.get<CollaborationRequest[]>("/api/v1/me/collaborations", {
    params: status ? { box, status } : { box },
  });
  return response.data;
}

export async function respondToCollaboration(
  id: string,
  action: "accept" | "decline" | "cancel",
): Promise<CollaborationRequest> {
  const response = await apiClient.post<CollaborationRequest>(
    `/api/v1/collaborations/${id}/${action}`,
  );
  return response.data;
}

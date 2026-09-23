import { apiClient } from "@/lib/api/client";

import type { VerificationStatus } from "@/features/profiles/types";

/** Matches the backend's VerificationQueueItem schema. */
export interface VerificationQueueItem {
  user_id: string;
  full_name: string;
  registration_number: string;
  email: string;
  designation: string;
  department_id: string | null;
  verification_status: VerificationStatus;
  created_at: string;
}

export type VerificationDecision = "verified" | "rejected";

export async function fetchVerificationQueue(): Promise<VerificationQueueItem[]> {
  const response = await apiClient.get<VerificationQueueItem[]>(
    "/api/v1/coordinator/verification-queue",
  );
  return response.data;
}

export async function decideVerification(
  userId: string,
  decision: VerificationDecision,
  comment?: string,
): Promise<VerificationQueueItem> {
  const response = await apiClient.post<VerificationQueueItem>(
    `/api/v1/researchers/${userId}/verify`,
    { decision, comment: comment ?? null },
  );
  return response.data;
}

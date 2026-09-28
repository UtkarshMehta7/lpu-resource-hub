import { apiClient } from "@/lib/api/client";

/** Matches NudgeKind in backend/app/modules/nudges/models.py. */
export type NudgeKind =
  "profile_verification" | "project_review" | "booking_approval" | "application_decision";

export interface NudgeResult {
  kind: NudgeKind;
  /** How many people were told, so the sender knows it went somewhere. */
  recipients: number;
  next_allowed_at: string;
}

export async function sendNudge(kind: NudgeKind, entityId: string): Promise<NudgeResult> {
  const response = await apiClient.post<NudgeResult>("/api/v1/nudges", {
    kind,
    entity_id: entityId,
  });
  return response.data;
}

import { apiClient } from "@/lib/api/client";

/** Matches NudgeKind in backend/app/modules/nudges/models.py. */
export type NudgeKind =
  | "profile_verification"
  | "project_review"
  | "booking_approval"
  | "application_decision"
  /**
   * The only kind that travels downward. Every other is "my own thing is
   * stuck"; this is an institutional reader asking the people who can act to
   * look at somebody else's slipping project.
   */
  | "project_at_risk";

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

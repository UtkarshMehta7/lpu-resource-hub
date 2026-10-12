import type { PillTone } from "@/components/ui/StatusPill";
import type { Role } from "@/features/auth/types";

import type { PersonalRequest, RequestCategory, RequestStatus } from "./api";

/**
 * Derived from `Record<…, string>` maps rather than written out as second
 * lists, so adding a status or a category makes the compiler name every
 * place that has to answer for it. Two hand-written lists of the same thing
 * is how every dean on the accounts page came to read "Student".
 */
export const STATUS_LABEL: Record<RequestStatus, string> = {
  submitted: "Submitted",
  under_review: "Being looked at",
  resolved: "Resolved",
  declined: "Declined",
  withdrawn: "Withdrawn",
};

export const STATUS_TONE: Record<RequestStatus, PillTone> = {
  submitted: "info",
  under_review: "warning",
  resolved: "positive",
  declined: "negative",
  withdrawn: "neutral",
};

export const CATEGORY_LABEL: Record<RequestCategory, string> = {
  academic: "Academic",
  facility: "Facility",
  funding: "Funding",
  administrative: "Administrative",
  other: "Other",
};

export const CATEGORY_OPTIONS = Object.entries(CATEGORY_LABEL) as [RequestCategory, string][];

const ROLE_LABEL: Record<Role, string> = {
  student: "Student",
  faculty: "Faculty",
  research_coordinator: "Research Coordinator",
  facility_custodian: "Facility Custodian",
  dean_of_research: "Dean of Research",
  admin: "Administration",
};

export function roleLabel(role: Role): string {
  return ROLE_LABEL[role];
}

/**
 * What a move is called from the reader's side.
 *
 * "Withdraw" and "Decline" are both refusals, but one is the sender
 * retracting and the other is the recipient answering no -- naming them the
 * same way would make a list of outcomes unreadable.
 */
export const ACTION_LABEL: Record<RequestStatus, string> = {
  submitted: "Put it back",
  under_review: "Take it up",
  resolved: "Mark resolved",
  declined: "Decline",
  withdrawn: "Withdraw",
};

/** Declining is the one move that cannot be made without a reason. */
export function needsReason(status: RequestStatus): boolean {
  return status === "declined";
}

/** The other party, from this reader's side. */
export function counterpart(request: PersonalRequest): string {
  return request.viewer_is_sender
    ? `${request.recipient_name} · ${roleLabel(request.recipient_role)}`
    : `${request.sender_name} · ${roleLabel(request.sender_role)}`;
}

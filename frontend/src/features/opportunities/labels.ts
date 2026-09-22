import type { Role } from "@/features/auth/types";

export type OpportunityType =
  | "research_assistant"
  | "student_researcher"
  | "project_assistant"
  | "research_internship"
  | "collaboration";

export type OpportunityStatus = "draft" | "open" | "closed" | "filled";

export type ApplicationStatus =
  "submitted" | "under_review" | "shortlisted" | "accepted" | "rejected" | "withdrawn";

export const TYPE_LABEL: Record<OpportunityType, string> = {
  research_assistant: "Research assistant",
  student_researcher: "Student researcher",
  project_assistant: "Project assistant",
  research_internship: "Research internship",
  collaboration: "Collaboration",
};

export const OPPORTUNITY_STATUS_LABEL: Record<OpportunityStatus, string> = {
  draft: "Draft",
  open: "Open",
  closed: "Closed",
  filled: "Filled",
};

export const APPLICATION_STATUS_LABEL: Record<ApplicationStatus, string> = {
  submitted: "Submitted",
  under_review: "Under review",
  shortlisted: "Shortlisted",
  accepted: "Accepted",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};

/** Mirrors the backend's reviewer transitions (applications/policies.py). */
export const REVIEWER_NEXT: Record<ApplicationStatus, ApplicationStatus[]> = {
  submitted: ["under_review", "shortlisted", "rejected"],
  under_review: ["shortlisted", "accepted", "rejected"],
  shortlisted: ["accepted", "rejected"],
  accepted: [],
  rejected: [],
  withdrawn: [],
};

export const WITHDRAWABLE: ReadonlySet<ApplicationStatus> = new Set([
  "submitted",
  "under_review",
  "shortlisted",
]);

/** Students apply to student openings; faculty/coordinators only to collaborations. */
export function canApplyAs(role: Role, type: OpportunityType): boolean {
  if (role === "student") return type !== "collaboration";
  if (role === "faculty" || role === "research_coordinator") return type === "collaboration";
  return false;
}

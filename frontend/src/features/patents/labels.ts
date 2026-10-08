import type { PillTone } from "@/components/ui/StatusPill";

import type { PatentStatus, VerificationStatus } from "./types";

/**
 * Two vocabularies, deliberately kept apart on screen as well as in the
 * database: STATUS is what the patent office has done, VERIFICATION is
 * whether this university has checked the record. Showing them in one pill
 * would say a coordinator's approval and a grant were the same event.
 */
export const STATUS_LABEL: Record<PatentStatus, string> = {
  disclosed: "Disclosed",
  under_assessment: "Under assessment",
  approved_to_file: "Approved to file",
  declined: "Not taken forward",
  filed: "Filed",
  published: "Published",
  granted: "Granted",
  lapsed: "Lapsed",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};

export const STATUS_TONE: Record<PatentStatus, PillTone> = {
  disclosed: "warning",
  under_assessment: "warning",
  approved_to_file: "info",
  declined: "neutral",
  filed: "info",
  published: "info",
  granted: "positive",
  lapsed: "warning",
  rejected: "negative",
  withdrawn: "neutral",
};

/** What moving there actually means, on the button that does it. */
export const STATUS_ACTION: Record<PatentStatus, string> = {
  disclosed: "Send back for more detail",
  under_assessment: "Start assessment",
  approved_to_file: "Approve for filing",
  declined: "Do not take forward",
  filed: "Record the filing",
  published: "Record publication",
  granted: "Record grant",
  lapsed: "Mark lapsed",
  rejected: "Record refusal",
  withdrawn: "Mark withdrawn",
};

/** Statuses that cannot be entered without the date the office issued. */
export const DATE_LABEL: Partial<Record<PatentStatus, string>> = {
  filed: "Filing date",
  published: "Publication date",
  granted: "Grant date",
};

export const NUMBER_LABEL: Partial<Record<PatentStatus, string>> = {
  filed: "Application number",
  published: "Publication number",
  granted: "Grant number",
};

/** Declining without a reason is what stops the next person disclosing. */
export const NOTE_REQUIRED: ReadonlySet<PatentStatus> = new Set<PatentStatus>(["declined"]);

/**
 * Everything still inside the university. The detail page uses this to decide
 * whether to show the disclosure or the office's paperwork, because a record
 * that has not been filed has no numbers to show.
 */
export const BEFORE_THE_OFFICE: ReadonlySet<PatentStatus> = new Set<PatentStatus>([
  "disclosed",
  "under_assessment",
  "approved_to_file",
  "declined",
]);

/**
 * How long a grace period can be relied on varies by jurisdiction and is a
 * question for the IP cell, not for this interface. What the interface can do
 * is make sure nobody discovers the date after it is too late to act on.
 */
export const DISCLOSURE_WARNING =
  "This invention was already public before any filing. A paper, poster, thesis or demonstration " +
  "can affect novelty, and the rules differ sharply between patent offices. Raise it with the IP " +
  "cell now rather than later.";

export const VERIFICATION_LABEL: Record<VerificationStatus, string> = {
  unverified: "Not checked",
  pending: "Awaiting review",
  verified: "Verified",
  rejected: "Returned",
};

export const VERIFICATION_TONE: Record<VerificationStatus, PillTone> = {
  unverified: "neutral",
  pending: "warning",
  verified: "positive",
  rejected: "negative",
};

/**
 * The offices that actually appear here, by their ST.3 code. Anything else
 * shows its code, which is what a patent attorney would read anyway -- a
 * complete country table would be 200 rows to spell out four.
 */
const OFFICES: Record<string, string> = {
  IN: "India",
  US: "United States",
  EP: "European Patent Office",
  WO: "PCT (WIPO)",
  GB: "United Kingdom",
  JP: "Japan",
  CN: "China",
  KR: "South Korea",
  AU: "Australia",
  CA: "Canada",
  DE: "Germany",
};

export function officeLabel(code: string): string {
  return OFFICES[code] ? `${OFFICES[code]} (${code})` : code;
}

export const OFFICE_OPTIONS = Object.entries(OFFICES).map(([code, name]) => ({ code, name }));

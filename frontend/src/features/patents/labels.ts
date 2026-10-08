import type { PillTone } from "@/components/ui/StatusPill";

import type { PatentStatus, VerificationStatus } from "./types";

/**
 * Two vocabularies, deliberately kept apart on screen as well as in the
 * database: STATUS is what the patent office has done, VERIFICATION is
 * whether this university has checked the record. Showing them in one pill
 * would say a coordinator's approval and a grant were the same event.
 */
export const STATUS_LABEL: Record<PatentStatus, string> = {
  filed: "Filed",
  published: "Published",
  granted: "Granted",
  lapsed: "Lapsed",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};

export const STATUS_TONE: Record<PatentStatus, PillTone> = {
  filed: "info",
  published: "info",
  granted: "positive",
  lapsed: "warning",
  rejected: "negative",
  withdrawn: "neutral",
};

/** What moving there actually means, on the button that does it. */
export const STATUS_ACTION: Record<PatentStatus, string> = {
  filed: "Back to filed",
  published: "Record publication",
  granted: "Record grant",
  lapsed: "Mark lapsed",
  rejected: "Record refusal",
  withdrawn: "Mark withdrawn",
};

/** Statuses that cannot be entered without the date the office issued. */
export const DATE_LABEL: Partial<Record<PatentStatus, string>> = {
  published: "Publication date",
  granted: "Grant date",
};

export const NUMBER_LABEL: Partial<Record<PatentStatus, string>> = {
  published: "Publication number",
  granted: "Grant number",
};

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

import type { PillTone } from "@/components/ui/StatusPill";
import type { Role } from "@/features/auth/types";

import type { Announcement, AnnouncementStatus } from "./api";

/**
 * Derived from a `Record<AnnouncementStatus, …>` rather than written out as a
 * second list, so adding a status makes the compiler name every place that
 * has to answer for it. The accounts page kept two hand-written lists of the
 * roles and they fell out of step, which showed every dean as a student.
 */
export const STATUS_LABEL: Record<AnnouncementStatus, string> = {
  draft: "Draft",
  published: "Published",
  withdrawn: "Withdrawn",
};

export const STATUS_TONE: Record<AnnouncementStatus, PillTone> = {
  draft: "neutral",
  published: "positive",
  withdrawn: "warning",
};

/** How the board names the person who spoke, not what they are now. */
const POSTER_ROLE_LABEL: Record<Role, string> = {
  student: "Student",
  faculty: "Faculty",
  research_coordinator: "Research Coordinator",
  facility_custodian: "Facility Custodian",
  dean_of_research: "Dean of Research",
  admin: "Administration",
};

export function posterLabel(notice: Announcement): string {
  return `${notice.posted_by_name} · ${POSTER_ROLE_LABEL[notice.posted_by_role]}`;
}

/**
 * Who a notice was addressed to, in words.
 *
 * A departmental notice names its department, because "Department" alone
 * leaves a reader on three committees guessing which one.
 */
export function audienceLabel(notice: Announcement): string {
  if (notice.audience === "institution") return "Whole university";
  return notice.department_name ?? "Department";
}

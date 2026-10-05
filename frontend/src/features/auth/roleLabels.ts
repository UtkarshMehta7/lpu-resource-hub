import type { Role } from "./types";

/**
 * What each role is called, in one place.
 *
 * Five copies of this map had grown across the admin pages and drifted from
 * each other: the same person read "Faculty" on one screen and
 * "Faculty / researcher" on the next, "Admin" here and "Administrator"
 * there. A `Record<Role, string>` also makes the compiler refuse a missing
 * case, which is what stops a new role from quietly rendering as its raw
 * enum value -- the accounts page once showed every dean as "Student"
 * because a second hand-written list fell behind this one.
 */
export const ROLE_LABELS: Record<Role, string> = {
  student: "Student",
  faculty: "Faculty / researcher",
  research_coordinator: "Research coordinator",
  facility_custodian: "Facility custodian",
  dean_of_research: "Dean of Research",
  admin: "Administrator",
};

/** Derived, never hand-written, for the same reason. */
export const ROLE_OPTIONS = Object.keys(ROLE_LABELS) as Role[];

/**
 * The roles that belong to no department, mirroring `INSTITUTION_WIDE_ROLES`
 * in app/core/permissions.py.
 *
 * A dean reads every department and an administrator serves all of them, so
 * placing either in one says something untrue. The server clears it either
 * way; this is only so the interface does not offer what the server will
 * undo.
 */
export const INSTITUTION_WIDE_ROLES: ReadonlySet<Role> = new Set<Role>([
  "admin",
  "dean_of_research",
]);

/** The same question asked of a role that arrived as a plain string. */
export function isInstitutionWide(role: string): boolean {
  return INSTITUTION_WIDE_ROLES.has(role as Role);
}

/**
 * The roles that build a research profile and are matched on it.
 *
 * Onboarding is a profile and a set of skills, and "matches will be rough"
 * is a consequence only these roles can feel. An administrator and a dean
 * have no profile; a facility custodian looks after rooms and is not matched
 * with anybody either — yet all three were being told their profile was
 * incomplete, which is a job with no page behind it.
 *
 * Deliberately not the inverse of `INSTITUTION_WIDE_ROLES`: a custodian
 * belongs to a department, so that set is the wrong question.
 */
export const RESEARCH_PROFILE_ROLES: ReadonlySet<Role> = new Set<Role>([
  "student",
  "faculty",
  "research_coordinator",
]);

export function buildsResearchProfile(role: string): boolean {
  return RESEARCH_PROFILE_ROLES.has(role as Role);
}

/**
 * A label for a role that arrived as a plain string -- a dashboard key, say.
 *
 * Falls back to the words of the enum rather than CSS `capitalize`, which
 * title-cases every word and turned `dean_of_research` into
 * "Dean Of Research".
 */
export function roleLabel(role: string): string {
  return ROLE_LABELS[role as Role] ?? role.replace(/_/g, " ");
}

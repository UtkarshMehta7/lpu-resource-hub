import type { Role } from "@/features/auth/types";

/**
 * Every destination in the platform, grouped.
 *
 * One list drives the top bar, the full menu and the command palette, so a
 * role can never reach a page through one and not another, and a page added
 * here is instantly findable everywhere.
 *
 * The groups exist because the flat list had grown to 28 entries: six on the
 * bar and twenty-two behind "More", in the order they happened to be written.
 * Finding "Verification" meant reading the lot.
 */
export type NavGroup = "Discover" | "My work" | "Review" | "Administration";

export interface NavItem {
  to: string;
  label: string;
  group: NavGroup;
  /** Omitted means "every signed-in role". */
  roles?: Role[];
  /** Extra words the command palette should match on, never displayed. */
  keywords?: string;
}

export const NAV_GROUPS: NavGroup[] = ["Discover", "My work", "Review", "Administration"];

export const NAV: NavItem[] = [
  // Discover -- finding people, work and money.
  { to: "/dashboard", label: "Dashboard", group: "Discover", keywords: "home start overview" },
  // No `roles`: the board is for every signed-in role, which is the point
  // of the feature. What each person sees is scoped on the server.
  //
  // The LATEST notices are a section on the dashboard, where everybody meets
  // them; this entry is the searchable history behind it. It is listed here
  // and not only linked from that section, because a page reachable from one
  // place is still missing from the other two surfaces this file drives.
  {
    to: "/announcements",
    label: "Announcements",
    group: "Discover",
    keywords: "notices notice board circular news bulletin updates history archive older past",
  },
  { to: "/search", label: "Search", group: "Discover", keywords: "find lookup" },
  { to: "/recommendations", label: "For you", group: "Discover", keywords: "recommended matches" },
  { to: "/researchers", label: "Researchers", group: "Discover", keywords: "faculty directory" },
  { to: "/projects", label: "Projects", group: "Discover", keywords: "research work" },
  { to: "/publications", label: "Publications", group: "Discover", keywords: "papers doi" },
  {
    to: "/patents",
    label: "Patents",
    group: "Discover",
    keywords:
      "ipr invention filing granted espacenet prior art intellectual property disclosure idf",
  },
  { to: "/opportunities", label: "Opportunities", group: "Discover", keywords: "openings apply" },
  { to: "/facilities", label: "Facilities", group: "Discover", keywords: "labs equipment rooms" },
  { to: "/funding", label: "Funding", group: "Discover", keywords: "grants calls money" },
  {
    to: "/students",
    label: "Students",
    group: "Discover",
    roles: ["faculty", "research_coordinator", "admin"],
  },

  // My work -- the things that are mine and waiting on me.
  { to: "/messages", label: "Messages", group: "My work", keywords: "chat conversations threads" },
  {
    // "Requests" until personal requests arrived (ADR 0039), at which point
    // one menu had two unrelated things under the same word. Named for what
    // it is now.
    to: "/collaborations",
    label: "Collaboration requests",
    group: "My work",
    roles: ["student", "faculty", "research_coordinator"],
    keywords: "collaboration invites work together co-author",
  },
  // A person's OWN work, which was reachable only by landing on the general
  // page first and noticing a button there. The routes all existed; they
  // were missing from this file, which is to say missing from the top bar,
  // the "All pages" menu and the command palette at once -- exactly what
  // happened to /admin/accounts/new, and reported the same way: as the
  // feature not existing.
  {
    to: "/projects/mine",
    label: "My projects",
    group: "My work",
    // Students belong here too: `mine` means owned OR joined, so this is
    // where somebody accepted onto a team finds it again.
    roles: ["student", "faculty", "research_coordinator"],
    keywords: "own projects joined team research work",
  },
  {
    to: "/projects/new",
    label: "New project",
    group: "My work",
    roles: ["faculty", "research_coordinator"],
    keywords: "start create propose research",
  },
  {
    to: "/opportunities/mine",
    label: "My opportunities",
    group: "My work",
    roles: ["faculty", "research_coordinator"],
    keywords: "posted openings positions applicants mine",
  },
  {
    to: "/opportunities/new",
    label: "Post an opportunity",
    group: "My work",
    roles: ["faculty", "research_coordinator"],
    keywords: "new opening position advertise recruit assistant",
  },
  // Personal requests travel UPWARD to a named person (ADR 0039). Everyone
  // reads the ones put to them, so the inbox has no `roles`; making one is
  // offered to everybody but an administrator, who is at the top of the
  // chain and addresses nobody -- the page says so rather than vanishing.
  {
    to: "/me/requests",
    label: "My requests",
    group: "My work",
    keywords: "asked escalation permission approval help sent upward",
  },
  {
    to: "/requests/inbox",
    label: "Requests to you",
    group: "My work",
    roles: ["faculty", "research_coordinator", "dean_of_research", "admin"],
    keywords: "inbox asked of me escalations approvals waiting",
  },
  {
    to: "/requests/new",
    label: "Make a request",
    group: "My work",
    roles: ["student", "faculty", "facility_custodian", "research_coordinator", "dean_of_research"],
    keywords: "ask escalate permission approval supervisor coordinator dean",
  },
  {
    to: "/me/applications",
    label: "My applications",
    group: "My work",
    // Everyone who may apply (Permission.APPLICATION_SUBMIT). Faculty apply
    // to COLLABORATION openings, so this is not students only.
    roles: ["student", "faculty", "research_coordinator"],
    keywords: "applied applications status tracking opportunities",
  },
  {
    to: "/publications/mine",
    label: "My publications",
    group: "My work",
    roles: ["faculty", "research_coordinator"],
    keywords: "own papers authored mine doi",
  },
  {
    to: "/publications/new",
    label: "Add a publication",
    group: "My work",
    roles: ["faculty", "research_coordinator"],
    keywords: "new paper record doi journal conference start writing",
  },
  {
    to: "/patents/mine",
    label: "My patents",
    group: "My work",
    // A student may record a patent (Permission.PATENT_CREATE), which is
    // deliberate -- student inventors are ordinary here.
    roles: ["student", "faculty", "research_coordinator", "admin"],
    keywords: "own inventions disclosed filed mine ipr",
  },
  {
    to: "/patents/new",
    label: "Record a patent",
    group: "My work",
    roles: ["student", "faculty", "research_coordinator", "admin"],
    keywords: "new invention disclosure ipr file idf",
  },
  { to: "/me/bookings", label: "My bookings", group: "My work", keywords: "slots reservations" },
  { to: "/me/saved", label: "Saved", group: "My work", keywords: "bookmarks starred" },
  { to: "/me/notifications", label: "Notifications", group: "My work", keywords: "alerts bell" },
  { to: "/profile", label: "Profile", group: "My work", keywords: "me account skills" },
  {
    to: "/announcements/mine",
    label: "My announcements",
    group: "My work",
    roles: ["research_coordinator", "dean_of_research", "admin"],
    keywords: "notices posted drafts board",
  },
  {
    to: "/announcements/new",
    label: "Post announcement",
    group: "My work",
    roles: ["research_coordinator", "dean_of_research", "admin"],
    keywords: "notice circular new write broadcast tell everyone",
  },
  {
    to: "/people",
    label: "My people",
    group: "My work",
    roles: ["research_coordinator", "faculty"],
    keywords: "team members manage remove",
  },
  // One route; the label names who you actually provision, mirroring
  // CREATABLE_ROLE on the backend, so nobody has to guess.
  {
    to: "/people/new",
    label: "Add coordinator",
    group: "My work",
    roles: ["admin"],
    keywords: "new account provision",
  },
  {
    to: "/people/new",
    label: "Add faculty",
    group: "My work",
    roles: ["research_coordinator"],
    keywords: "new account provision",
  },
  {
    to: "/people/custodians/new",
    label: "Add custodian",
    group: "My work",
    roles: ["research_coordinator", "admin"],
    keywords: "facility custodian appoint rooms labs equipment",
  },
  {
    to: "/people/new",
    label: "Add student",
    group: "My work",
    roles: ["faculty"],
    keywords: "new account provision enrol",
  },

  // Review -- queues somebody is waiting on.
  {
    to: "/coordinator/verification-queue",
    label: "Verification",
    group: "Review",
    roles: ["research_coordinator", "admin"],
    keywords: "verify researchers approve",
  },
  {
    to: "/coordinator/review-queue",
    label: "Reviews",
    group: "Review",
    // A dean decides what crosses departments; their queue is filtered to
    // exactly that, so the same page serves both (ADR 0032).
    roles: ["research_coordinator", "dean_of_research", "admin"],
    keywords: "approve projects",
  },
  {
    to: "/coordinator/booking-queue",
    label: "Bookings",
    group: "Review",
    // A custodian belongs here and nowhere else in Review: the queue is
    // filtered to the facilities assigned to them.
    roles: ["research_coordinator", "facility_custodian", "admin"],
    keywords: "approve slots",
  },
  {
    to: "/coordinator/at-risk",
    label: "At-risk projects",
    group: "Review",
    roles: ["research_coordinator", "dean_of_research", "admin"],
    keywords: "milestones overdue slipping late deadlines",
  },
  {
    to: "/analytics/report",
    label: "Research report",
    group: "Review",
    roles: ["research_coordinator", "dean_of_research", "admin"],
    keywords: "institutional annual academic year export pdf csv statistics",
  },
  {
    to: "/admin/reports",
    label: "Reports",
    group: "Review",
    roles: ["research_coordinator", "admin"],
    keywords: "moderation flagged",
  },
  {
    to: "/coordinator/patents",
    label: "Patents & disclosures",
    group: "Review",
    roles: ["research_coordinator", "admin"],
    keywords: "ipr verify approve assess invention disclosure filing ip cell",
  },
  {
    to: "/coordinator/duplicates",
    label: "Duplicates",
    group: "Review",
    roles: ["research_coordinator", "admin"],
    keywords: "deduplicate merge publications same paper curation",
  },
  {
    to: "/analytics",
    label: "Analytics",
    group: "Review",
    roles: ["research_coordinator", "dean_of_research", "admin"],
    keywords: "stats numbers network",
  },

  // Administration -- running the platform.
  { to: "/admin", label: "Administration", group: "Administration", roles: ["admin"] },
  {
    to: "/admin/users",
    label: "Accounts",
    group: "Administration",
    roles: ["admin"],
    keywords: "users roles deactivate delete",
  },
  {
    // The admin override: the only route that names a role, and so the only
    // way to create a facility custodian or a dean of research. It was
    // reachable from one tile on /admin and from nowhere else -- not the top
    // bar, not the full menu, not the command palette -- which is exactly
    // what this file exists to prevent.
    to: "/admin/accounts/new",
    label: "Add any account",
    group: "Administration",
    roles: ["admin"],
    keywords: "new custodian dean create provision override facility role",
  },
  {
    to: "/admin/coordinators",
    label: "Coordinators",
    group: "Administration",
    roles: ["admin"],
    keywords: "scope departments",
  },
  {
    to: "/admin/administrators",
    label: "Administrators",
    group: "Administration",
    roles: ["admin"],
    keywords: "promote handover otp",
  },
  {
    to: "/admin/audit-logs",
    label: "Audit log",
    group: "Administration",
    roles: ["admin"],
    keywords: "history who did what",
  },
  { to: "/admin/settings", label: "Settings", group: "Administration", roles: ["admin"] },
];

/** The destinations this role may actually reach. */
export function navigationFor(role: Role | undefined): NavItem[] {
  if (!role) return [];
  return NAV.filter((item) => !item.roles || item.roles.includes(role));
}

/**
 * Ranked matches for what someone typed.
 *
 * A label that starts with the query beats one that merely contains it, which
 * beats a keyword hit -- so typing "pro" offers Projects before Profile, and
 * "verify" still finds Verification even though the word is not in its label.
 */
export function searchNavigation(items: NavItem[], query: string): NavItem[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return items;

  const scored = items
    .map((item) => {
      const label = item.label.toLowerCase();
      if (label.startsWith(needle)) return { item, score: 0 };
      if (label.includes(needle)) return { item, score: 1 };
      if ((item.keywords ?? "").includes(needle)) return { item, score: 2 };
      return null;
    })
    .filter((row): row is { item: NavItem; score: number } => row !== null);

  return scored.sort((a, b) => a.score - b.score).map((row) => row.item);
}

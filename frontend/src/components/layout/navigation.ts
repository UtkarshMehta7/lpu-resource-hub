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
  { to: "/search", label: "Search", group: "Discover", keywords: "find lookup" },
  { to: "/recommendations", label: "For you", group: "Discover", keywords: "recommended matches" },
  { to: "/researchers", label: "Researchers", group: "Discover", keywords: "faculty directory" },
  { to: "/projects", label: "Projects", group: "Discover", keywords: "research work" },
  { to: "/publications", label: "Publications", group: "Discover", keywords: "papers doi" },
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
    to: "/collaborations",
    label: "Requests",
    group: "My work",
    roles: ["student", "faculty", "research_coordinator"],
    keywords: "collaboration invites",
  },
  { to: "/me/bookings", label: "My bookings", group: "My work", keywords: "slots reservations" },
  { to: "/me/saved", label: "Saved", group: "My work", keywords: "bookmarks starred" },
  { to: "/me/notifications", label: "Notifications", group: "My work", keywords: "alerts bell" },
  { to: "/profile", label: "Profile", group: "My work", keywords: "me account skills" },
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
    roles: ["research_coordinator", "admin"],
    keywords: "approve projects",
  },
  {
    to: "/coordinator/booking-queue",
    label: "Bookings",
    group: "Review",
    roles: ["research_coordinator", "admin"],
    keywords: "approve slots",
  },
  {
    to: "/admin/reports",
    label: "Reports",
    group: "Review",
    roles: ["research_coordinator", "admin"],
    keywords: "moderation flagged",
  },
  {
    to: "/analytics",
    label: "Analytics",
    group: "Review",
    roles: ["research_coordinator", "admin"],
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

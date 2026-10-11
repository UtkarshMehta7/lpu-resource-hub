import type { ResearcherCard } from "@/features/directory/api";
import type { OpportunityCard } from "@/features/opportunities/api";
import type { ProjectCard } from "@/features/projects/api";
import type { Announcement } from "@/features/announcements/api";
import { apiClient } from "@/lib/api/client";

export interface DeadlineItem {
  kind: "opportunity" | "funding";
  item_id: string;
  title: string;
  deadline: string;
  applied: boolean;
}

export interface StudentDashboard {
  recommended_opportunities: OpportunityCard[];
  recommended_projects: ProjectCard[];
  recommended_researchers: ResearcherCard[];
  saved_count: number;
  applications_by_status: Record<string, number>;
  pending_collaboration_requests: number;
  upcoming_deadlines: DeadlineItem[];
}

export interface FacultyDashboard {
  my_projects: ProjectCard[];
  projects_by_status: Record<string, number>;
  open_opportunities: OpportunityCard[];
  pending_applications: number;
  team_members: number;
  accepted_collaborations: number;
  publications: number;
  pending_collaboration_requests: number;
}

export interface CoordinatorDashboard {
  pending_verifications: { user_id: string; full_name: string; designation: string }[];
  pending_reviews: ProjectCard[];
  open_reports: number;
  department_activity: Record<string, number>;
}

export interface DeanDashboard {
  departments: number;
  departments_needing_attention: number;
  projects_at_risk: number;
  pending_cross_department_reviews: number;
  verification_backlog: number;
  active_projects: number;
  researchers: number;
}

export interface CustodianDashboard {
  facilities_held: number;
  equipment: number;
  bookings_awaiting_decision: number;
}

export interface AdminDashboard {
  users_by_role: Record<string, number>;
  platform_counts: Record<string, number>;
  open_reports: number;
  recent_audit: { id: string; action: string; entity_type: string; created_at: string }[];
}

/**
 * The notice board as it appears on a dashboard.
 *
 * Not optional and not per-role: a notice is the one thing on this platform
 * addressed to everybody, so every dashboard carries this (ADR 0038). The
 * server degrades it to an empty panel rather than failing the dashboard, so
 * `latest: []` means "nothing announced lately" and nothing more.
 */
export interface AnnouncementsPanel {
  unread: number;
  latest: Announcement[];
}

export interface DashboardResponse {
  role: string;
  onboarding_complete: boolean;
  /**
   * Optional on purpose, and it must stay that way.
   *
   * Netlify serves a new bundle from the CDN in seconds while Render
   * rebuilds its image in minutes. Between the two, this code talks to an
   * API that has never heard of this field and gets `undefined` back --
   * and reading `.latest` off it inside render would throw and take the
   * WHOLE dashboard down for every role, not just this section. The same
   * failure the prior-art panel had, on a far more important page.
   */
  announcements?: AnnouncementsPanel;
  student: StudentDashboard | null;
  faculty: FacultyDashboard | null;
  coordinator: CoordinatorDashboard | null;
  dean: DeanDashboard | null;
  custodian: CustodianDashboard | null;
  admin: AdminDashboard | null;
}

export async function fetchDashboard(): Promise<DashboardResponse> {
  const response = await apiClient.get<DashboardResponse>("/api/v1/me/dashboard");
  return response.data;
}

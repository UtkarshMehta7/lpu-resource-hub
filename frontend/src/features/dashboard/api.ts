import type { ResearcherCard } from "@/features/directory/api";
import type { OpportunityCard } from "@/features/opportunities/api";
import type { ProjectCard } from "@/features/projects/api";
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

export interface AdminDashboard {
  users_by_role: Record<string, number>;
  platform_counts: Record<string, number>;
  open_reports: number;
  recent_audit: { id: string; action: string; entity_type: string; created_at: string }[];
}

export interface DashboardResponse {
  role: string;
  onboarding_complete: boolean;
  student: StudentDashboard | null;
  faculty: FacultyDashboard | null;
  coordinator: CoordinatorDashboard | null;
  admin: AdminDashboard | null;
}

export async function fetchDashboard(): Promise<DashboardResponse> {
  const response = await apiClient.get<DashboardResponse>("/api/v1/me/dashboard");
  return response.data;
}

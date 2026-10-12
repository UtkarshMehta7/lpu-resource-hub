import type { Page } from "@/features/directory/api";
import { apiClient } from "@/lib/api/client";

import type { ProjectStatus } from "./labels";

export { STATUS_LABEL, type ProjectStatus } from "./labels";

/** Matches the backend's ProjectCard / ProjectRead schemas. */
export interface ProjectCard {
  id: string;
  title: string;
  summary: string;
  status: ProjectStatus;
  owner_id: string;
  owner_name: string;
  owner_registration_number: string;
  department_id: string | null;
  /** A name, never a UUID. */
  department_name: string | null;
  /** The other departments this project's team reaches into. Empty for
   *  ordinary work; on a dean's queue it is why the project is theirs. */
  spans_departments: string[];
  start_date: string | null;
  end_date: string | null;
  research_areas: string[];
  skills: string[];
}

export interface ProjectMember {
  user_id: string;
  full_name: string;
  registration_number: string;
  member_role: string;
  department_id: string | null;
  /** A name, never a UUID. Null for someone who belongs to no department. */
  department_name: string | null;
}

export interface Project extends ProjectCard {
  description: string;
  objectives: string | null;
  review_comment: string | null;
  reviewed_at: string | null;
  members: ProjectMember[];
  created_at: string;
  updated_at: string;
}

export interface ProjectInput {
  title: string;
  summary: string;
  description: string;
  objectives?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  skill_ids?: string[];
  research_area_ids?: string[];
}

export interface ProjectFilters {
  q?: string;
  status?: ProjectStatus;
  mine?: boolean;
  owner_id?: string;
  page?: number;
}

function clean(filters: object): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(filters).filter(([, v]) => v !== undefined && v !== "" && v !== false),
  );
}

export async function fetchProjects(filters: ProjectFilters): Promise<Page<ProjectCard>> {
  const response = await apiClient.get<Page<ProjectCard>>("/api/v1/projects", {
    params: clean(filters),
  });
  return response.data;
}

export async function fetchProject(id: string): Promise<Project> {
  const response = await apiClient.get<Project>(`/api/v1/projects/${id}`);
  return response.data;
}

export async function createProject(input: ProjectInput): Promise<Project> {
  const response = await apiClient.post<Project>("/api/v1/projects", input);
  return response.data;
}

export async function updateProject(id: string, input: Partial<ProjectInput>): Promise<Project> {
  const response = await apiClient.patch<Project>(`/api/v1/projects/${id}`, input);
  return response.data;
}

export type ProjectAction = "submit" | "complete" | "archive";

export async function runProjectAction(id: string, action: ProjectAction): Promise<Project> {
  const response = await apiClient.post<Project>(`/api/v1/projects/${id}/${action}`);
  return response.data;
}

export async function deleteProject(id: string): Promise<void> {
  await apiClient.delete(`/api/v1/projects/${id}`);
}

export async function reviewProject(
  id: string,
  decision: "approve" | "reject",
  comment?: string,
): Promise<Project> {
  const response = await apiClient.post<Project>(`/api/v1/projects/${id}/review`, {
    decision,
    comment: comment ?? null,
  });
  return response.data;
}

export async function fetchReviewQueue(): Promise<ProjectCard[]> {
  const response = await apiClient.get<ProjectCard[]>("/api/v1/coordinator/review-queue");
  return response.data;
}

/**
 * Put somebody on the team directly, without an application.
 *
 * `POST /projects/{id}/members` has existed since projects were built and
 * nothing in the interface called it, so the only way onto a team was to
 * apply to an opening and be accepted -- no use at all for a colleague the
 * lead already works with. Enforcing a permission is not the same as making
 * it reachable; this is the `/admin/accounts/new` shape again.
 */
export async function addMember(
  projectId: string,
  userId: string,
  memberRole: string,
): Promise<void> {
  await apiClient.post(`/api/v1/projects/${projectId}/members`, {
    user_id: userId,
    member_role: memberRole,
  });
}

export async function removeMember(projectId: string, userId: string): Promise<void> {
  await apiClient.delete(`/api/v1/projects/${projectId}/members/${userId}`);
}

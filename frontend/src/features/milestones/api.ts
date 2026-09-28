import { apiClient } from "@/lib/api/client";

import type {
  AtRiskProject,
  Milestone,
  MilestoneCreate,
  MilestoneStatus,
  MilestoneUpdate,
  MyMilestone,
} from "./types";

/** The cache key for one project's plan, shared by every mutation here. */
export function milestoneQueryKey(projectId: string) {
  return ["milestones", projectId] as const;
}

export async function fetchMilestones(projectId: string): Promise<Milestone[]> {
  const response = await apiClient.get<Milestone[]>(`/api/v1/projects/${projectId}/milestones`);
  return response.data;
}

export async function createMilestone(
  projectId: string,
  data: MilestoneCreate,
): Promise<Milestone> {
  const response = await apiClient.post<Milestone>(
    `/api/v1/projects/${projectId}/milestones`,
    data,
  );
  return response.data;
}

export async function updateMilestone(id: string, data: MilestoneUpdate): Promise<Milestone> {
  const response = await apiClient.patch<Milestone>(`/api/v1/milestones/${id}`, data);
  return response.data;
}

export async function deleteMilestone(id: string): Promise<void> {
  await apiClient.delete(`/api/v1/milestones/${id}`);
}

export async function changeMilestoneStatus(
  id: string,
  status: MilestoneStatus,
): Promise<Milestone> {
  const response = await apiClient.post<Milestone>(`/api/v1/milestones/${id}/status`, { status });
  return response.data;
}

export async function addDependency(id: string, dependsOnId: string): Promise<Milestone> {
  const response = await apiClient.post<Milestone>(`/api/v1/milestones/${id}/dependencies`, {
    depends_on_id: dependsOnId,
  });
  return response.data;
}

export async function removeDependency(id: string, dependsOnId: string): Promise<Milestone> {
  const response = await apiClient.delete<Milestone>(
    `/api/v1/milestones/${id}/dependencies/${dependsOnId}`,
  );
  return response.data;
}

export async function fetchMyMilestones(): Promise<MyMilestone[]> {
  const response = await apiClient.get<MyMilestone[]>("/api/v1/me/milestones");
  return response.data;
}

export async function fetchAtRiskProjects(): Promise<AtRiskProject[]> {
  const response = await apiClient.get<AtRiskProject[]>("/api/v1/coordinator/at-risk-projects");
  return response.data;
}

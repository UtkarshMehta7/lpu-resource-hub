import { apiClient } from "@/lib/api/client";

import type {
  Profile,
  ResearchAreaEntry,
  ResearcherProfileUpdate,
  SkillEntry,
  StudentProfileUpdate,
} from "./types";

/**
 * GET /me/profile. A 404 is a meaningful answer (profile not created yet),
 * so it comes back as null instead of throwing -- same approach as
 * features/system-status/api.ts treats a 503.
 */
export async function fetchMyProfile(): Promise<Profile | null> {
  const response = await apiClient.get<Profile>("/api/v1/me/profile", {
    validateStatus: (status) => status === 200 || status === 404,
  });
  return response.status === 404 ? null : response.data;
}

export async function saveProfile(
  update: StudentProfileUpdate | ResearcherProfileUpdate,
): Promise<Profile> {
  const response = await apiClient.put<Profile>("/api/v1/me/profile", update);
  return response.data;
}

export async function saveSkills(entries: SkillEntry[]): Promise<SkillEntry[]> {
  const response = await apiClient.put<SkillEntry[]>("/api/v1/me/skills", entries);
  return response.data;
}

export async function saveResearchAreas(
  entries: ResearchAreaEntry[],
): Promise<ResearchAreaEntry[]> {
  const response = await apiClient.put<ResearchAreaEntry[]>("/api/v1/me/research-areas", entries);
  return response.data;
}

/** Who oversees the viewer's department. Null when they have no department. */
export interface DepartmentCoordinator {
  department_id: string;
  department_name: string;
  /** Null when the department has no coordinator yet. */
  user_id: string | null;
  full_name: string | null;
  registration_number: string | null;
  designation: string | null;
  email: string | null;
}

export async function fetchMyDepartment(): Promise<DepartmentCoordinator | null> {
  const response = await apiClient.get<DepartmentCoordinator | null>("/api/v1/me/department");
  return response.data;
}

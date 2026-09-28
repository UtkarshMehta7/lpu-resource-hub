import { apiClient } from "@/lib/api/client";

import type {
  AuthorCandidate,
  ImportHistoryEntry,
  ImportLookup,
  ImportPreview,
  ImportResult,
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

/* ---------------------------------------------------------------- import */

export async function searchImportCandidates(
  name: string,
  affiliation?: string | null,
): Promise<AuthorCandidate[]> {
  const response = await apiClient.post<AuthorCandidate[]>("/api/v1/me/profile/import/candidates", {
    name,
    affiliation: affiliation ?? null,
  });
  return response.data;
}

export async function fetchImportHistory(): Promise<ImportHistoryEntry[]> {
  const response = await apiClient.get<ImportHistoryEntry[]>("/api/v1/me/profile/import/history");
  return response.data;
}

export async function previewProfileImport(lookup: ImportLookup): Promise<ImportPreview> {
  const response = await apiClient.post<ImportPreview>("/api/v1/me/profile/import/preview", lookup);
  return response.data;
}

export async function applyProfileImport(
  lookup: ImportLookup & { fields: string[]; work_keys: string[] },
): Promise<ImportResult> {
  const response = await apiClient.post<ImportResult>("/api/v1/me/profile/import", lookup);
  return response.data;
}

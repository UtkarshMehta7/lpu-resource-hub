import type { Role } from "@/features/auth/types";
import type { Department, School } from "@/features/directory/api-org";
import { apiClient } from "@/lib/api/client";

import type {
  AdminUserRead,
  AdminUserUpdate,
  DeletionImpact,
  Page,
  TemporaryPasswordRead,
} from "./types";

export interface ListUsersParams {
  page?: number;
  page_size?: number;
  role?: Role;
  is_active?: boolean;
}

export async function fetchUsers(params: ListUsersParams = {}): Promise<Page<AdminUserRead>> {
  const response = await apiClient.get<Page<AdminUserRead>>("/api/v1/admin/users", { params });
  return response.data;
}

export async function updateUser(userId: string, data: AdminUserUpdate): Promise<AdminUserRead> {
  const response = await apiClient.patch<AdminUserRead>(`/api/v1/admin/users/${userId}`, data);
  return response.data;
}

export async function changeUserRole(userId: string, role: Role): Promise<AdminUserRead> {
  const response = await apiClient.post<AdminUserRead>(`/api/v1/admin/users/${userId}/role`, {
    role,
  });
  return response.data;
}

export async function resetTemporaryPassword(userId: string): Promise<TemporaryPasswordRead> {
  const response = await apiClient.post<TemporaryPasswordRead>(
    `/api/v1/admin/users/${userId}/temporary-password`,
  );
  return response.data;
}

export async function setUserActive(userId: string, isActive: boolean): Promise<AdminUserRead> {
  const path = isActive ? "activate" : "deactivate";
  const response = await apiClient.post<AdminUserRead>(`/api/v1/admin/users/${userId}/${path}`);
  return response.data;
}

/**
 * The people the caller is responsible for -- the ones they may remove.
 * Distinct from fetchUsers, which is every account and admin-only.
 */
export async function fetchManageableUsers(
  params: { page?: number; page_size?: number } = {},
): Promise<Page<AdminUserRead>> {
  const response = await apiClient.get<Page<AdminUserRead>>("/api/v1/users", { params });
  return response.data;
}

/**
 * What a deletion would destroy. Not under /admin: every role above student
 * may remove the people below them, so the hierarchy decides, not the path.
 */
export async function fetchDeletionImpact(userId: string): Promise<DeletionImpact> {
  const response = await apiClient.get<DeletionImpact>(`/api/v1/users/${userId}/deletion-impact`);
  return response.data;
}

export async function deleteUser(userId: string): Promise<void> {
  await apiClient.delete(`/api/v1/users/${userId}`);
}

/** Organisation structure. Admin-only writes; the reads are public lists. */
export async function createSchool(name: string): Promise<School> {
  const response = await apiClient.post<School>("/api/v1/admin/schools", { name });
  return response.data;
}

export async function createDepartment(schoolId: string, name: string): Promise<Department> {
  const response = await apiClient.post<Department>("/api/v1/admin/departments", {
    school_id: schoolId,
    name,
  });
  return response.data;
}

/** Admin-only: create an account of any role, outside the hierarchy. */
export async function createAccountAsAdmin(payload: {
  registration_number: string;
  full_name: string;
  role: Role;
  department_id: string | null;
  email: string | null;
}): Promise<{ user: AdminUserRead; temporary_password: string }> {
  const response = await apiClient.post<{ user: AdminUserRead; temporary_password: string }>(
    "/api/v1/admin/users",
    payload,
  );
  return response.data;
}

export interface PromotionChallenge {
  id: string;
  target_user_id: string;
  expires_at: string;
}

/** Sends a one-time code to the person being promoted. Never returns it. */
export async function requestAdminPromotion(userId: string): Promise<PromotionChallenge> {
  const response = await apiClient.post<PromotionChallenge>(
    `/api/v1/admin/users/${userId}/admin-promotion`,
  );
  return response.data;
}

export async function confirmAdminPromotion(userId: string, code: string): Promise<AdminUserRead> {
  const response = await apiClient.post<AdminUserRead>(
    `/api/v1/admin/users/${userId}/admin-promotion/confirm`,
    { code },
  );
  return response.data;
}

export async function stepDownAsAdmin(newRole: Role): Promise<AdminUserRead> {
  const response = await apiClient.post<AdminUserRead>("/api/v1/admin/me/step-down", {
    new_role: newRole,
  });
  return response.data;
}

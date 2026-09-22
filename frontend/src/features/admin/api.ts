import type { Role } from "@/features/auth/types";
import { apiClient } from "@/lib/api/client";

import type { AdminUserRead, AdminUserUpdate, Page } from "./types";

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

export async function setUserActive(userId: string, isActive: boolean): Promise<AdminUserRead> {
  const path = isActive ? "activate" : "deactivate";
  const response = await apiClient.post<AdminUserRead>(`/api/v1/admin/users/${userId}/${path}`);
  return response.data;
}

import { apiClient } from "@/lib/api/client";

export interface School {
  id: string;
  name: string;
}

export interface Department {
  id: string;
  school_id: string;
  name: string;
}

/** Read-only org lists, available to every signed-in user for filter menus. */
export async function fetchSchools(): Promise<School[]> {
  const response = await apiClient.get<School[]>("/api/v1/schools");
  return response.data;
}

export async function fetchDepartments(schoolId?: string): Promise<Department[]> {
  const response = await apiClient.get<Department[]>("/api/v1/departments", {
    params: schoolId ? { school_id: schoolId } : {},
  });
  return response.data;
}

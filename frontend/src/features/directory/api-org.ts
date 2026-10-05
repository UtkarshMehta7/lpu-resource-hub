import { apiClient } from "@/lib/api/client";

export interface School {
  id: string;
  name: string;
}

export interface Department {
  id: string;
  school_id: string;
  /** The school's name. Two schools may each run a department of the same
   *  name, so a picker that shows only `name` offers identical options. */
  school_name: string | null;
  name: string;
}

/**
 * How a department reads in a list.
 *
 * The school is appended only when another department shares the name —
 * every option carrying its school would be noise on the twenty that are
 * already unambiguous, and silence on the two that are not is how somebody
 * ends up under the wrong coordinator.
 */
export function departmentLabel(department: Department, all: Department[]): string {
  const ambiguous = all.some(
    (other) => other.id !== department.id && other.name === department.name,
  );
  return ambiguous && department.school_name
    ? `${department.name} · ${department.school_name}`
    : department.name;
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

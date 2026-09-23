import type { Availability, ProfileLink, VerificationStatus } from "@/features/profiles/types";
import { apiClient } from "@/lib/api/client";

/** Matches the backend's public directory schemas (no email, by design). */
export interface ResearcherCard {
  user_id: string;
  /** The LPU registration/employee number. Names collide; this does not. */
  registration_number: string;
  full_name: string;
  designation: string;
  department_id: string | null;
  availability: Availability;
  verification_status: VerificationStatus;
  research_areas: string[];
  skills: string[];
}

export interface ResearcherDetail extends ResearcherCard {
  bio: string | null;
  links: ProfileLink[] | null;
  created_at: string;
}

export interface StudentCard {
  user_id: string;
  registration_number: string;
  full_name: string;
  program: string;
  year: number;
  department_id: string | null;
  interests: string | null;
  research_areas: string[];
  skills: string[];
}

export interface Page<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
}

export interface DirectoryFilters {
  q?: string;
  school_id?: string;
  department_id?: string;
  research_area_id?: string;
  skill_id?: string;
  availability?: Availability;
  verified_only?: boolean;
  sort?: "name" | "-name" | "recent";
  page?: number;
  page_size?: number;
}

/** Drops empty values so they never reach the query string. */
function cleanParams(filters: object): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(filters).filter(
      ([, value]) => value !== undefined && value !== "" && value !== false,
    ),
  );
}

export async function fetchResearchers(filters: DirectoryFilters): Promise<Page<ResearcherCard>> {
  const response = await apiClient.get<Page<ResearcherCard>>("/api/v1/researchers", {
    params: cleanParams(filters),
  });
  return response.data;
}

export async function fetchResearcher(userId: string): Promise<ResearcherDetail> {
  const response = await apiClient.get<ResearcherDetail>(`/api/v1/researchers/${userId}`);
  return response.data;
}

export async function fetchDiscoverableStudents(filters: {
  q?: string;
  department_id?: string;
  page?: number;
}): Promise<Page<StudentCard>> {
  const response = await apiClient.get<Page<StudentCard>>("/api/v1/students", {
    params: cleanParams(filters),
  });
  return response.data;
}

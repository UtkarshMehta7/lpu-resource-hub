import type { Page } from "@/features/directory/api";
import { apiClient } from "@/lib/api/client";

import type { PublicationType } from "./labels";

export { PUB_TYPE_LABEL, type PublicationType } from "./labels";

/** Matches the backend's PublicationRead schema. */
export interface Publication {
  id: string;
  title: string;
  abstract: string | null;
  venue: string | null;
  year: number;
  doi: string | null;
  url: string | null;
  pub_type: PublicationType;
  created_by: string;
  authors: { user_id: string | null; name: string; author_order: number }[];
  projects: { id: string; title: string }[];
  created_at: string;
}

/** Exactly one of user_id / external_name. List position is the author order. */
export type AuthorInput = { user_id: string } | { external_name: string };

export interface PublicationInput {
  title: string;
  abstract: string | null;
  venue: string | null;
  year: number;
  doi: string | null;
  url: string | null;
  pub_type: PublicationType;
  authors: AuthorInput[];
  project_ids?: string[];
}

export interface PublicationFilters {
  q?: string;
  author_id?: string;
  year?: number;
  project_id?: string;
  research_area_id?: string;
  page?: number;
}

function clean(filters: object): Record<string, unknown> {
  return Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== undefined && v !== ""));
}

export async function fetchPublications(filters: PublicationFilters): Promise<Page<Publication>> {
  const response = await apiClient.get<Page<Publication>>("/api/v1/publications", {
    params: clean(filters),
  });
  return response.data;
}

export async function fetchPublication(id: string): Promise<Publication> {
  const response = await apiClient.get<Publication>(`/api/v1/publications/${id}`);
  return response.data;
}

export async function createPublication(input: PublicationInput): Promise<Publication> {
  const response = await apiClient.post<Publication>("/api/v1/publications", input);
  return response.data;
}

export async function updatePublication(
  id: string,
  input: Partial<PublicationInput>,
): Promise<Publication> {
  const response = await apiClient.patch<Publication>(`/api/v1/publications/${id}`, input);
  return response.data;
}

export async function deletePublication(id: string): Promise<void> {
  await apiClient.delete(`/api/v1/publications/${id}`);
}

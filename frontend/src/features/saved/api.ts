import type { ResearcherCard } from "@/features/directory/api";
import type { OpportunityCard } from "@/features/opportunities/api";
import type { ProjectCard } from "@/features/projects/api";
import { apiClient } from "@/lib/api/client";

export type SavedType = "project" | "opportunity" | "researcher";

export interface SavedEntry {
  id: string;
  saved_type: SavedType;
  created_at: string;
  item: ProjectCard | OpportunityCard | ResearcherCard;
}

export type SaveTarget =
  { project_id: string } | { opportunity_id: string } | { researcher_id: string };

export async function fetchSaved(type?: SavedType): Promise<SavedEntry[]> {
  const response = await apiClient.get<SavedEntry[]>("/api/v1/me/saved", {
    params: type ? { type } : undefined,
  });
  return response.data;
}

export async function saveItem(target: SaveTarget): Promise<SavedEntry> {
  const response = await apiClient.post<SavedEntry>("/api/v1/me/saved", target);
  return response.data;
}

export async function unsaveItem(savedId: string): Promise<void> {
  await apiClient.delete(`/api/v1/me/saved/${savedId}`);
}

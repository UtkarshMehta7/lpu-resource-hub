import { apiClient } from "@/lib/api/client";

/** Matches the backend's SkillRead / ResearchAreaRead schemas. */
export interface Skill {
  id: string;
  name: string;
  created_at: string;
}

export interface ResearchArea {
  id: string;
  name: string;
  parent_id: string | null;
  created_at: string;
}

/** Searches by name; an exact alias hit ("ML") also returns its canonical tag. */
export async function searchSkills(q?: string): Promise<Skill[]> {
  const response = await apiClient.get<Skill[]>("/api/v1/skills", { params: q ? { q } : {} });
  return response.data;
}

export async function searchResearchAreas(q?: string): Promise<ResearchArea[]> {
  const response = await apiClient.get<ResearchArea[]>("/api/v1/research-areas", {
    params: q ? { q } : {},
  });
  return response.data;
}

export type TagSuggestionType = "skill" | "research_area";

export async function suggestTag(
  suggestedName: string,
  suggestedType: TagSuggestionType,
): Promise<void> {
  await apiClient.post("/api/v1/tags/suggestions", {
    suggested_name: suggestedName,
    suggested_type: suggestedType,
  });
}

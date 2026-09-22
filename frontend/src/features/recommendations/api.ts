import type { ResearcherCard, StudentCard } from "@/features/directory/api";
import type { OpportunityCard } from "@/features/opportunities/api";
import type { ProjectCard } from "@/features/projects/api";
import { apiClient } from "@/lib/api/client";

export type RecommendationType = "opportunities" | "projects" | "researchers" | "collaborators";

export const RECOMMENDATION_TABS: { value: RecommendationType; label: string }[] = [
  { value: "opportunities", label: "Opportunities" },
  { value: "projects", label: "Projects" },
  { value: "researchers", label: "Researchers" },
  { value: "collaborators", label: "Collaborators" },
];

export type RecommendedItem = ResearcherCard | StudentCard | ProjectCard | OpportunityCard;

export interface Recommendation {
  item_id: string;
  score: number;
  /** Generated from the score components only — never free-form prose. */
  reasons: string[];
  item: RecommendedItem;
}

export interface RecommendationsResponse {
  type: RecommendationType;
  cold_start: boolean;
  items: Recommendation[];
}

export async function fetchRecommendations(
  type: RecommendationType,
  limit = 10,
): Promise<RecommendationsResponse> {
  const response = await apiClient.get<RecommendationsResponse>("/api/v1/recommendations", {
    params: { type, limit },
  });
  return response.data;
}

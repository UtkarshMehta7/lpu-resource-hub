import type { ResearcherCard } from "@/features/directory/api";
import type { OpportunityCard } from "@/features/opportunities/api";
import type { ProjectCard } from "@/features/projects/api";
import type { Publication } from "@/features/publications/api";
import { apiClient } from "@/lib/api/client";

export interface SearchResults {
  query: string;
  researchers: ResearcherCard[];
  projects: ProjectCard[];
  publications: Publication[];
  opportunities: OpportunityCard[];
  /** Only present on semantic responses: false means it answered lexically. */
  semantic_used?: boolean;
}

/** Keyword search: matches the words you typed. */
export async function searchLexical(q: string): Promise<SearchResults> {
  const response = await apiClient.get<SearchResults>("/api/v1/search", { params: { q } });
  return response.data;
}

/** Natural-language search: keyword hits fused with meaning-based matches. */
export async function searchSemantic(q: string, limit = 10): Promise<SearchResults> {
  const response = await apiClient.get<SearchResults>("/api/v1/search/semantic", {
    params: { q, limit },
  });
  return response.data;
}

export function totalResults(results: SearchResults | undefined): number {
  if (!results) return 0;
  return (
    results.researchers.length +
    results.projects.length +
    results.publications.length +
    results.opportunities.length
  );
}

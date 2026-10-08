import type { Page } from "@/features/directory/api";
import { apiClient } from "@/lib/api/client";

import type {
  Patent,
  PatentInput,
  PatentStatus,
  PatentTransition,
  PriorArtResult,
  VerificationStatus,
} from "./types";

const BASE = "/api/v1/patents";

export interface PatentFilters {
  q?: string;
  inventor_id?: string;
  status?: PatentStatus;
  verification_status?: VerificationStatus;
  jurisdiction?: string;
  page?: number;
}

function clean(filters: object): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(filters).filter(([, v]) => v !== undefined && v !== "" && v !== false),
  );
}

export async function fetchPatents(filters: PatentFilters): Promise<Page<Patent>> {
  const response = await apiClient.get<Page<Patent>>(BASE, { params: clean(filters) });
  return response.data;
}

export async function fetchPatent(id: string): Promise<Patent> {
  const response = await apiClient.get<Patent>(`${BASE}/${id}`);
  return response.data;
}

export async function createPatent(input: PatentInput): Promise<Patent> {
  const response = await apiClient.post<Patent>(BASE, input);
  return response.data;
}

export async function updatePatent(id: string, input: Partial<PatentInput>): Promise<Patent> {
  const response = await apiClient.patch<Patent>(`${BASE}/${id}`, input);
  return response.data;
}

export async function movePatentStatus(id: string, move: PatentTransition): Promise<Patent> {
  const response = await apiClient.post<Patent>(`${BASE}/${id}/status`, move);
  return response.data;
}

export async function decidePatent(id: string, decision: boolean, note?: string): Promise<Patent> {
  const response = await apiClient.post<Patent>(`${BASE}/${id}/decision`, {
    decision,
    note: note ?? null,
  });
  return response.data;
}

export async function deletePatent(id: string): Promise<void> {
  await apiClient.delete(`${BASE}/${id}`);
}

export async function fetchReviewQueue(): Promise<Patent[]> {
  const response = await apiClient.get<Patent[]>("/api/v1/patent-review-queue");
  return response.data;
}

/**
 * A POST because an abstract is far too long for a query string -- nothing is
 * stored, and running it again costs two requests to two open indexes.
 */
export async function searchPriorArt(
  title: string,
  abstract?: string | null,
  excludeId?: string,
): Promise<PriorArtResult> {
  const response = await apiClient.post<PriorArtResult>(
    `${BASE}/prior-art`,
    { title, abstract: abstract ?? null },
    {
      params: excludeId ? { exclude_id: excludeId } : undefined,
      // The shared client allows ten seconds, which is the whole budget the
      // backend gives its two outbound lookups. This one is a deliberate act
      // with a spinner on it, so it waits rather than racing them.
      timeout: 20_000,
    },
  );
  return response.data;
}

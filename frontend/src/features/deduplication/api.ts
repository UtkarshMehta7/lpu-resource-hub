import { apiClient } from "@/lib/api/client";
import type { Page } from "@/features/admin/types";

import type { DuplicateAction, DuplicateReview, ScanResult } from "./types";

/**
 * `/publication-duplicates`, not `/publications/duplicates`: the backend
 * registers `/publications/{id}` and would have matched "duplicates" as an id.
 */
const BASE = "/api/v1/publication-duplicates";

export async function scanForDuplicates(): Promise<ScanResult> {
  const response = await apiClient.post<ScanResult>(`${BASE}/scan`);
  return response.data;
}

export async function fetchDuplicates(params: {
  page?: number;
  page_size?: number;
  status?: string;
}): Promise<Page<DuplicateReview>> {
  const response = await apiClient.get<Page<DuplicateReview>>(BASE, { params });
  return response.data;
}

export async function decideDuplicate(
  id: string,
  action: DuplicateAction,
  options: { keep_id?: string; note?: string } = {},
): Promise<DuplicateReview> {
  const response = await apiClient.post<DuplicateReview>(`${BASE}/${id}/decision`, {
    action,
    keep_id: options.keep_id ?? null,
    note: options.note ?? null,
  });
  return response.data;
}

export async function undoDuplicateMerge(id: string): Promise<DuplicateReview> {
  const response = await apiClient.post<DuplicateReview>(`${BASE}/${id}/undo`);
  return response.data;
}

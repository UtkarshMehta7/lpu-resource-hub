import type { Page } from "@/features/directory/api";
import { apiClient } from "@/lib/api/client";

export type FundingStatus = "open" | "closed";

export interface FundingCall {
  id: string;
  organization: string;
  title: string;
  description: string;
  eligibility: string | null;
  amount_text: string | null;
  amount_min: number | null;
  amount_max: number | null;
  deadline: string;
  official_source_url: string | null;
  status: FundingStatus;
  is_demo: boolean;
  research_areas: string[];
  created_at: string;
}

export interface FundingInput {
  organization: string;
  title: string;
  description: string;
  eligibility: string | null;
  amount_text: string | null;
  deadline: string;
  official_source_url: string | null;
  research_area_ids?: string[];
}

function clean(params: object): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== "" && v !== false),
  );
}

export async function fetchFundingList(filters: {
  q?: string;
  status?: FundingStatus;
  research_area_id?: string;
  open_only?: boolean;
  page?: number;
}): Promise<Page<FundingCall>> {
  const response = await apiClient.get<Page<FundingCall>>("/api/v1/funding", {
    params: clean(filters),
  });
  return response.data;
}

export async function fetchFunding(id: string): Promise<FundingCall> {
  const response = await apiClient.get<FundingCall>(`/api/v1/funding/${id}`);
  return response.data;
}

export async function createFunding(input: FundingInput): Promise<FundingCall> {
  const response = await apiClient.post<FundingCall>("/api/v1/funding", input);
  return response.data;
}

/** Days until the deadline, from a caller-supplied "now" (never the clock at render). */
export function daysUntil(deadline: string, now: number): number | null {
  if (now === 0) return null;
  const target = new Date(`${deadline}T00:00:00`).getTime();
  return Math.ceil((target - now) / (24 * 60 * 60 * 1000));
}

export function amountLabel(call: FundingCall): string | null {
  if (call.amount_text) return call.amount_text;
  if (call.amount_min !== null && call.amount_max !== null) {
    return `${call.amount_min.toLocaleString()} – ${call.amount_max.toLocaleString()}`;
  }
  if (call.amount_max !== null) return `up to ${call.amount_max.toLocaleString()}`;
  if (call.amount_min !== null) return `from ${call.amount_min.toLocaleString()}`;
  return null;
}

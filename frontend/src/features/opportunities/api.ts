import type { Page } from "@/features/directory/api";
import { apiClient } from "@/lib/api/client";

import type { ApplicationStatus, OpportunityStatus, OpportunityType } from "./labels";

/** Matches the backend's OpportunityCard / OpportunityRead schemas. */
export interface OpportunityCard {
  id: string;
  title: string;
  opportunity_type: OpportunityType;
  status: OpportunityStatus;
  project_id: string | null;
  project_title: string | null;
  department_id: string | null;
  created_by: string;
  creator_name: string;
  creator_registration_number: string;
  positions: number;
  accepted_count: number;
  deadline: string;
  skills: { id: string; name: string; is_required: boolean }[];
}

export interface Opportunity extends OpportunityCard {
  description: string;
  eligibility: string | null;
  created_at: string;
  updated_at: string;
  my_application_id: string | null;
}

export interface OpportunityInput {
  title: string;
  description: string;
  opportunity_type: OpportunityType;
  project_id?: string | null;
  eligibility: string | null;
  positions: number;
  deadline: string;
  skills?: { skill_id: string; is_required: boolean }[];
}

export interface OpportunityFilters {
  q?: string;
  type?: OpportunityType;
  status?: OpportunityStatus;
  department_id?: string;
  skill_id?: string;
  deadline_before?: string;
  mine?: boolean;
  page?: number;
}

export interface Application {
  id: string;
  opportunity_id: string;
  opportunity_title: string;
  opportunity_type: OpportunityType;
  applicant_id: string;
  applicant_name: string;
  applicant_registration_number: string;
  statement: string;
  status: ApplicationStatus;
  note: string | null;
  decided_at: string | null;
  created_at: string;
  events: { status: ApplicationStatus; note: string | null; created_at: string }[];
}

function clean(filters: object): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(filters).filter(([, v]) => v !== undefined && v !== "" && v !== false),
  );
}

export async function fetchOpportunities(
  filters: OpportunityFilters,
): Promise<Page<OpportunityCard>> {
  const response = await apiClient.get<Page<OpportunityCard>>("/api/v1/opportunities", {
    params: clean(filters),
  });
  return response.data;
}

export async function fetchOpportunity(id: string): Promise<Opportunity> {
  const response = await apiClient.get<Opportunity>(`/api/v1/opportunities/${id}`);
  return response.data;
}

export async function createOpportunity(input: OpportunityInput): Promise<Opportunity> {
  const response = await apiClient.post<Opportunity>("/api/v1/opportunities", input);
  return response.data;
}

export async function updateOpportunity(
  id: string,
  input: Partial<OpportunityInput>,
): Promise<Opportunity> {
  const response = await apiClient.patch<Opportunity>(`/api/v1/opportunities/${id}`, input);
  return response.data;
}

export async function runOpportunityAction(
  id: string,
  action: "publish" | "close",
): Promise<Opportunity> {
  const response = await apiClient.post<Opportunity>(`/api/v1/opportunities/${id}/${action}`);
  return response.data;
}

export async function applyToOpportunity(id: string, statement: string): Promise<Application> {
  const response = await apiClient.post<Application>(`/api/v1/opportunities/${id}/applications`, {
    statement,
  });
  return response.data;
}

export async function fetchOpportunityApplications(id: string): Promise<Application[]> {
  const response = await apiClient.get<Application[]>(`/api/v1/opportunities/${id}/applications`);
  return response.data;
}

export async function fetchMyApplications(): Promise<Application[]> {
  const response = await apiClient.get<Application[]>("/api/v1/me/applications");
  return response.data;
}

export async function changeApplicationStatus(
  id: string,
  status: ApplicationStatus,
  note: string | null,
  addToProject: boolean,
): Promise<Application> {
  const response = await apiClient.post<Application>(`/api/v1/applications/${id}/status`, {
    status,
    note,
    add_to_project: addToProject,
  });
  return response.data;
}

export async function withdrawApplication(id: string): Promise<Application> {
  const response = await apiClient.post<Application>(`/api/v1/applications/${id}/withdraw`, {});
  return response.data;
}

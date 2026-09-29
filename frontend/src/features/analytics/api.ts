import { apiClient } from "@/lib/api/client";

export interface LabelledCount {
  label: string;
  count: number;
}

export interface EquipmentUsage {
  label: string;
  hours: number;
  bookings: number;
}

export interface TrendPoint {
  month: string;
  projects: number;
  applications: number;
  bookings: number;
}

export interface AnalyticsOverview {
  /** "department" for a coordinator, "platform" for an admin. */
  scope: "department" | "platform";
  department_id: string | null;
  projects_by_status: Record<string, number>;
  projects_by_area: LabelledCount[];
  opportunity_funnel: Record<string, number>;
  equipment_utilisation: EquipmentUsage[];
  funding_interest: LabelledCount[];
  verification_backlog: { pending: number; oldest_waiting_since: string | null };
  accepted_collaborations: number;
  open_reports: number;
  trends: TrendPoint[];
}

export interface NetworkNode {
  id: string;
  full_name: string;
  role: string;
  department_id: string | null;
  degree: number;
  connected: boolean;
}

export interface NetworkEdge {
  source: string;
  target: string;
  kinds: string[];
  weight: number;
}

export interface CollaborationNetwork {
  scope: "department" | "platform";
  nodes: NetworkNode[];
  edges: NetworkEdge[];
}

export interface PlatformSettings {
  environment: string;
  settings: Record<string, unknown>;
}

export async function fetchOverview(): Promise<AnalyticsOverview> {
  const response = await apiClient.get<AnalyticsOverview>("/api/v1/analytics/overview");
  return response.data;
}

export async function fetchNetwork(): Promise<CollaborationNetwork> {
  const response = await apiClient.get<CollaborationNetwork>("/api/v1/analytics/network");
  return response.data;
}

export async function fetchPlatformSettings(): Promise<PlatformSettings> {
  const response = await apiClient.get<PlatformSettings>("/api/v1/admin/settings");
  return response.data;
}

/** Turns the flat funnel map into the ordered stages people think in. */
export function applicationStages(funnel: Record<string, number>): LabelledCount[] {
  const stages: [string, string][] = [
    ["applications_submitted", "Submitted"],
    ["applications_under_review", "Under review"],
    ["applications_shortlisted", "Shortlisted"],
    ["applications_accepted", "Accepted"],
    ["applications_rejected", "Rejected"],
    ["applications_withdrawn", "Withdrawn"],
  ];
  return stages.map(([key, label]) => ({ label, count: funnel[key] ?? 0 }));
}

export function statusCounts(byStatus: Record<string, number>): LabelledCount[] {
  return Object.entries(byStatus)
    .filter(([, count]) => count > 0)
    .map(([key, count]) => ({ label: key.replace(/_/g, " "), count }));
}

/* ------------------------------------------- institutional research report */

export interface ReportTable {
  title: string;
  columns: string[];
  rows: string[][];
  /** The rule these figures were produced under. */
  definition: string | null;
}

export interface ReportSection {
  title: string;
  summary: [string, string][];
  tables: ReportTable[];
}

export interface InstitutionalReport {
  academic_year: string;
  period_start: string;
  period_end: string;
  generated_at: string;
  scope: string;
  sections: ReportSection[];
}

export interface AcademicYearOption {
  label: string;
  start: string;
  end: string;
  is_current: boolean;
}

export async function fetchAcademicYears(): Promise<AcademicYearOption[]> {
  const response = await apiClient.get<AcademicYearOption[]>("/api/v1/analytics/academic-years");
  return response.data;
}

export async function fetchInstitutionalReport(academicYear: string): Promise<InstitutionalReport> {
  const response = await apiClient.get<InstitutionalReport>(
    "/api/v1/analytics/institutional-report",
    { params: { academic_year: academicYear } },
  );
  return response.data;
}

/**
 * Downloads the report as a file.
 *
 * Fetched as a blob through the same authenticated client rather than opening
 * a bare URL: the API needs the Authorization header, which a plain anchor
 * cannot send.
 */
export async function downloadInstitutionalReport(
  academicYear: string,
  format: "csv" | "pdf",
): Promise<void> {
  const response = await apiClient.get<Blob>("/api/v1/analytics/institutional-report/export", {
    params: { academic_year: academicYear, format },
    responseType: "blob",
  });
  const url = URL.createObjectURL(response.data);
  try {
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `institutional-research-report-${academicYear}.${format}`;
    anchor.click();
  } finally {
    // Revoking immediately can cancel the download in some browsers; a tick
    // is enough for the click to have been handled.
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}

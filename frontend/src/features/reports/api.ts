import { apiClient } from "@/lib/api/client";

export type ReportTargetType =
  | "project"
  | "opportunity"
  | "publication"
  | "profile"
  // Hiding a message withholds its text but leaves it in the thread.
  | "message";
export type ReportStatus = "open" | "dismissed" | "actioned";

export interface ContentReport {
  id: string;
  reporter_id: string;
  reporter_name: string;
  target_type: ReportTargetType;
  target_id: string;
  target_title: string | null;
  reason: string;
  status: ReportStatus;
  reviewed_by: string | null;
  reviewed_at: string | null;
  resolution_note: string | null;
  created_at: string;
}

export async function reportContent(input: {
  target_type: ReportTargetType;
  target_id: string;
  reason: string;
}): Promise<ContentReport> {
  const response = await apiClient.post<ContentReport>("/api/v1/reports", input);
  return response.data;
}

export async function fetchReports(status: ReportStatus = "open"): Promise<ContentReport[]> {
  const response = await apiClient.get<ContentReport[]>("/api/v1/admin/reports", {
    params: { status },
  });
  return response.data;
}

export async function resolveReport(
  id: string,
  status: "dismissed" | "actioned",
  note: string | null,
): Promise<ContentReport> {
  const response = await apiClient.post<ContentReport>(`/api/v1/admin/reports/${id}/resolve`, {
    status,
    note,
  });
  return response.data;
}

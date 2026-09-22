import { apiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";

export interface ReadinessResponse {
  status: "ok" | "degraded";
  database: "ok" | "unavailable";
}

function isReadinessResponse(data: unknown): data is ReadinessResponse {
  if (typeof data !== "object" || data === null) return false;
  if (!("status" in data) || !("database" in data)) return false;
  return (
    (data.status === "ok" || data.status === "degraded") &&
    (data.database === "ok" || data.database === "unavailable")
  );
}

/**
 * GET /health/ready. A 503 is a meaningful answer here (API up, database
 * down), so it is returned as data instead of being thrown.
 */
export async function fetchReadiness(signal?: AbortSignal): Promise<ReadinessResponse> {
  const response = await apiClient.get<unknown>("/health/ready", {
    signal,
    validateStatus: (status) => status === 200 || status === 503,
  });
  if (!isReadinessResponse(response.data)) {
    throw new ApiError("Unexpected response from /health/ready.", "http", response.status);
  }
  return response.data;
}

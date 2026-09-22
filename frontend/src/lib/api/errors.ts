import axios from "axios";

export type ApiErrorKind = "network" | "timeout" | "http" | "cancelled" | "unknown";

/** Normalised error raised by every API call, whatever went wrong. */
export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | undefined;
  readonly code: string | undefined;

  constructor(message: string, kind: ApiErrorKind, status?: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.code = code;
  }
}

interface ErrorEnvelope {
  error: { code: string; message: string };
}

function isErrorEnvelope(data: unknown): data is ErrorEnvelope {
  if (typeof data !== "object" || data === null || !("error" in data)) return false;
  const { error } = data;
  return (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    "message" in error &&
    typeof error.code === "string" &&
    typeof error.message === "string"
  );
}

/** Convert anything thrown by Axios (or elsewhere) into an ApiError. */
export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;

  if (axios.isCancel(error)) {
    return new ApiError("Request was cancelled.", "cancelled");
  }

  if (axios.isAxiosError(error)) {
    if (error.code === "ECONNABORTED" || error.code === "ETIMEDOUT") {
      return new ApiError("The server took too long to respond.", "timeout");
    }
    if (!error.response) {
      return new ApiError("Could not reach the server.", "network");
    }
    const { status } = error.response;
    const data: unknown = error.response.data;
    if (isErrorEnvelope(data)) {
      return new ApiError(data.error.message, "http", status, data.error.code);
    }
    return new ApiError(`Request failed with status ${String(status)}.`, "http", status);
  }

  return new ApiError(error instanceof Error ? error.message : "Unknown error.", "unknown");
}

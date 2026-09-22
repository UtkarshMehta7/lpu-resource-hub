import { apiClient } from "@/lib/api/client";

import type {
  AccessTokenResponse,
  ChangePasswordPayload,
  LoginPayload,
  RegisterPayload,
  UserRead,
} from "./types";

export async function registerRequest(payload: RegisterPayload): Promise<AccessTokenResponse> {
  const response = await apiClient.post<AccessTokenResponse>("/api/v1/auth/register", payload);
  return response.data;
}

export async function loginRequest(payload: LoginPayload): Promise<AccessTokenResponse> {
  const response = await apiClient.post<AccessTokenResponse>("/api/v1/auth/login", payload);
  return response.data;
}

/**
 * Silent refresh: succeeds only if a valid refresh-token cookie is present.
 *
 * Callers should use `refreshAccessToken` from the API client instead, which
 * deduplicates concurrent attempts; this is the raw request it wraps.
 */
export async function refreshRequest(): Promise<AccessTokenResponse> {
  const response = await apiClient.post<AccessTokenResponse>("/api/v1/auth/refresh");
  return response.data;
}

export async function logoutRequest(): Promise<void> {
  await apiClient.post("/api/v1/auth/logout");
}

export async function fetchCurrentUser(): Promise<UserRead> {
  const response = await apiClient.get<UserRead>("/api/v1/me");
  return response.data;
}

/** Revokes every session (backend clears all refresh tokens); caller should sign out locally too. */
export async function changePasswordRequest(payload: ChangePasswordPayload): Promise<void> {
  await apiClient.post("/api/v1/auth/change-password", payload);
}

import axios, { type AxiosInstance, type InternalAxiosRequestConfig } from "axios";

import { clearAuthState, getAuthState, setAuthState } from "@/features/auth/tokenStore";
import type { AccessTokenResponse } from "@/features/auth/types";
import { config } from "@/lib/config";

import { toApiError } from "./errors";

/**
 * The single HTTP client for the whole app. Feature modules call typed
 * functions (see features/<name>/api.ts) and never use Axios directly.
 */
export const apiClient: AxiosInstance = axios.create({
  baseURL: config.apiBaseUrl,
  timeout: 10_000,
  // Sends/receives the httpOnly refresh-token cookie.
  withCredentials: true,
  headers: {
    Accept: "application/json",
    // CSRF defence for /auth/refresh and /auth/logout: a cross-site HTML
    // form can't set custom headers, but same-origin JS (us) can.
    "X-Requested-With": "XMLHttpRequest",
  },
});

apiClient.interceptors.request.use((requestConfig) => {
  const { accessToken } = getAuthState();
  if (accessToken) {
    requestConfig.headers.set("Authorization", `Bearer ${accessToken}`);
  }
  return requestConfig;
});

const AUTH_ENDPOINT_PATHS = ["/api/v1/auth/login", "/api/v1/auth/refresh", "/api/v1/auth/logout"];

interface RetryableConfig extends InternalAxiosRequestConfig {
  _retriedAfterRefresh?: boolean;
}

function isAuthEndpoint(url: string | undefined): boolean {
  return url !== undefined && AUTH_ENDPOINT_PATHS.some((path) => url.includes(path));
}

// Deduplicates concurrent refresh attempts: several requests failing with a
// 401 at once -- or React StrictMode invoking the bootstrap effect twice --
// must trigger exactly one POST /auth/refresh. Refresh tokens rotate and the
// backend treats a reused one as theft and revokes the whole family, so a
// second concurrent call would sign the user out.
let refreshPromise: Promise<string | null> | null = null;

export function refreshAccessToken(): Promise<string | null> {
  refreshPromise ??= (async () => {
    try {
      const response = await apiClient.post<AccessTokenResponse>("/api/v1/auth/refresh");
      setAuthState({ accessToken: response.data.access_token, user: response.data.user });
      return response.data.access_token;
    } catch {
      clearAuthState();
      return null;
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: unknown) => {
    if (axios.isAxiosError(error) && error.response?.status === 401) {
      const originalRequest = error.config as RetryableConfig | undefined;
      const eligibleForRetry =
        originalRequest &&
        !originalRequest._retriedAfterRefresh &&
        !isAuthEndpoint(originalRequest.url);

      if (eligibleForRetry) {
        originalRequest._retriedAfterRefresh = true;
        const newAccessToken = await refreshAccessToken();
        if (newAccessToken) {
          originalRequest.headers.set("Authorization", `Bearer ${newAccessToken}`);
          return apiClient(originalRequest);
        }
      }
    }
    return Promise.reject(toApiError(error));
  },
);

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

/** Per-origin, so every tab of the app contends for the same one. */
const REFRESH_LOCK = "lpu-research-hub:auth-refresh";

/**
 * Serialises the refresh across TABS as well as within one.
 *
 * `refreshPromise` above dedupes only inside a single tab, and the refresh
 * token lives in a cookie every tab shares. Two tabs waking together each
 * sent the same token; whichever arrived second presented one the first had
 * already rotated out, which the backend reads as replay and answers by
 * revoking the whole family -- signing both tabs out mid-use, with nothing on
 * screen to explain it. The lock makes the second tab wait and then refresh
 * with the cookie the first left behind, which is an ordinary rotation.
 *
 * Where the Web Locks API is absent (jsdom, older Safari) this runs
 * unserialised: that is the behaviour we already had, not a new regression.
 */
function withRefreshLock(run: () => Promise<string>): Promise<string> {
  const locks: LockManager | undefined = navigator.locks;
  if (!locks) {
    return run();
  }
  return locks.request(REFRESH_LOCK, run);
}

/** One POST, inside whatever serialisation the caller arranged. */
async function postRefresh(): Promise<string> {
  const response = await apiClient.post<AccessTokenResponse>("/api/v1/auth/refresh");
  setAuthState({ accessToken: response.data.access_token, user: response.data.user });
  return response.data.access_token;
}

export function refreshAccessToken(): Promise<string | null> {
  refreshPromise ??= (async () => {
    try {
      return await withRefreshLock(postRefresh);
    } catch {
      // Either the cookie is gone or the lock could not be taken. Both mean
      // we have no access token to offer, and the caller reads null as
      // "signed out" rather than having to handle a rejection.
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

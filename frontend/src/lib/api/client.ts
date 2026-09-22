import axios, { type AxiosInstance } from "axios";

import { config } from "@/lib/config";

import { toApiError } from "./errors";

/**
 * The single HTTP client for the whole app. Feature modules call typed
 * functions (see features/<name>/api.ts) and never use Axios directly.
 * Auth interceptors (access token, silent refresh) attach here in Step 1.
 */
export const apiClient: AxiosInstance = axios.create({
  baseURL: config.apiBaseUrl,
  timeout: 10_000,
  headers: { Accept: "application/json" },
});

apiClient.interceptors.response.use(
  (response) => response,
  (error: unknown) => Promise.reject(toApiError(error)),
);

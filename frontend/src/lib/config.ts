/**
 * Runtime configuration read from Vite environment variables.
 * Fails loudly at startup when a required value is missing or malformed.
 */

function readApiBaseUrl(): string {
  const raw = import.meta.env.VITE_API_BASE_URL?.trim();
  if (!raw) {
    throw new Error(
      "VITE_API_BASE_URL is not set. Copy frontend/.env.example to frontend/.env and set it.",
    );
  }
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new Error(`VITE_API_BASE_URL is not a valid absolute URL: "${raw}"`);
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error(`VITE_API_BASE_URL must use http or https: "${raw}"`);
  }
  return raw.replace(/\/+$/, "");
}

export const config = {
  apiBaseUrl: readApiBaseUrl(),
} as const;

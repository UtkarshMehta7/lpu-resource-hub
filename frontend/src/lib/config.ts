/**
 * Runtime configuration read from Vite environment variables.
 * Fails loudly at startup when a required value is missing or malformed.
 */

export function resolveApiBaseUrl(value: string | undefined): string {
  const raw = value?.trim();
  if (!raw) {
    throw new Error(
      "VITE_API_BASE_URL is not set. Copy frontend/.env.example to frontend/.env and set it.",
    );
  }
  // A path prefix means "same origin as this page", which is how the
  // deployed build is served: a rewrite in front of the static site proxies
  // /api to the API, so the browser only ever talks to one origin and the
  // refresh cookie is a first-party cookie. Still explicit -- an empty or
  // misspelled value fails as loudly as before.
  if (raw.startsWith("/")) {
    return raw === "/" ? "" : raw.replace(/\/+$/, "");
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
  apiBaseUrl: resolveApiBaseUrl(import.meta.env.VITE_API_BASE_URL),
} as const;

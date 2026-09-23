import { describe, expect, it } from "vitest";

import { resolveApiBaseUrl } from "./config";

/**
 * The deployed build is served with a Netlify proxy that forwards /api to
 * the API, so the browser sees one origin. That only works if a path prefix is a
 * legal value -- while a missing or malformed one still fails loudly, which
 * is what stops a bad build reaching people.
 */
describe("resolveApiBaseUrl", () => {
  it("accepts an absolute URL, as used locally", () => {
    expect(resolveApiBaseUrl("http://localhost:8000")).toBe("http://localhost:8000");
    expect(resolveApiBaseUrl("https://api.example.com/")).toBe("https://api.example.com");
  });

  it("treats a bare slash as same-origin", () => {
    expect(resolveApiBaseUrl("/")).toBe("");
  });

  it("keeps a path prefix, for a rewrite mounted under a sub-path", () => {
    expect(resolveApiBaseUrl("/backend/")).toBe("/backend");
  });

  it("still refuses a missing value", () => {
    expect(() => resolveApiBaseUrl(undefined)).toThrow(/not set/i);
    expect(() => resolveApiBaseUrl("   ")).toThrow(/not set/i);
  });

  it("still refuses something that is neither", () => {
    expect(() => resolveApiBaseUrl("not a url")).toThrow(/absolute URL/i);
    expect(() => resolveApiBaseUrl("ftp://example.com")).toThrow(/http or https/i);
  });
});

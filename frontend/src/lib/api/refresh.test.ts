import { beforeEach, describe, expect, it, vi } from "vitest";

import { clearAuthState } from "@/features/auth/tokenStore";

import { apiClient, refreshAccessToken } from "./client";

const TOKEN_RESPONSE = {
  data: {
    access_token: "new-token",
    token_type: "bearer",
    expires_in: 900,
    user: { id: "u1", email: "a@b.c", full_name: "A", role: "student", is_active: true },
  },
};

describe("refreshAccessToken", () => {
  beforeEach(() => {
    clearAuthState();
    vi.restoreAllMocks();
  });

  it("makes one request when called concurrently", async () => {
    // Refresh tokens rotate: a second concurrent POST would reuse the same
    // cookie, which the backend treats as theft and revokes the session.
    const post = vi.spyOn(apiClient, "post").mockResolvedValue(TOKEN_RESPONSE);

    const [first, second] = await Promise.all([refreshAccessToken(), refreshAccessToken()]);

    expect(post).toHaveBeenCalledTimes(1);
    expect(first).toBe("new-token");
    expect(second).toBe("new-token");
  });

  it("allows a later refresh once the first has settled", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue(TOKEN_RESPONSE);

    await refreshAccessToken();
    await refreshAccessToken();

    expect(post).toHaveBeenCalledTimes(2);
  });

  it("signs the user out when there is no valid cookie", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue(new Error("401"));

    expect(await refreshAccessToken()).toBeNull();
  });
});

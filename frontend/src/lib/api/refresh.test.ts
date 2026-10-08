import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

  afterEach(() => {
    vi.unstubAllGlobals();
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

  it("waits for another tab's refresh before sending its own", async () => {
    // Two tabs share one rotating cookie. Whichever POSTs second with a token
    // the first already rotated out is read as replay, and the backend revokes
    // the whole family -- both tabs are signed out mid-use. The Web Lock makes
    // the second tab wait, so its refresh is an ordinary rotation instead.
    let release = (): void => {};
    const heldByAnotherTab = new Promise<void>((resolve) => {
      release = resolve;
    });
    const request = vi.fn(async (_name: string, run: () => Promise<string>) => {
      await heldByAnotherTab;
      return run();
    });
    vi.stubGlobal("navigator", { locks: { request } });
    const post = vi.spyOn(apiClient, "post").mockResolvedValue(TOKEN_RESPONSE);

    const pending = refreshAccessToken();
    await Promise.resolve();
    expect(post).not.toHaveBeenCalled();

    release();

    expect(await pending).toBe("new-token");
    expect(request).toHaveBeenCalledWith("lpu-research-hub:auth-refresh", expect.any(Function));
  });

  it("still refreshes where the Web Locks API is absent", async () => {
    vi.stubGlobal("navigator", {});
    const post = vi.spyOn(apiClient, "post").mockResolvedValue(TOKEN_RESPONSE);

    expect(await refreshAccessToken()).toBe("new-token");
    expect(post).toHaveBeenCalledTimes(1);
  });
});

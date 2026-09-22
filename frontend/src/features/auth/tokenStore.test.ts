import { beforeEach, describe, expect, it, vi } from "vitest";

import { clearAuthState, getAuthState, setAuthState, subscribeAuthState } from "./tokenStore";
import type { UserRead } from "./types";

const USER: UserRead = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "jane@example.com",
  full_name: "Jane Doe",
  role: "student",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
};

beforeEach(() => {
  clearAuthState();
});

describe("tokenStore", () => {
  it("starts empty", () => {
    expect(getAuthState()).toEqual({ accessToken: null, user: null });
  });

  it("updates state and notifies subscribers", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeAuthState(listener);

    setAuthState({ accessToken: "token-1", user: USER });

    expect(getAuthState()).toEqual({ accessToken: "token-1", user: USER });
    expect(listener).toHaveBeenCalledTimes(1);

    unsubscribe();
  });

  it("stops notifying after unsubscribe", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeAuthState(listener);
    unsubscribe();

    setAuthState({ accessToken: "token-1", user: USER });

    expect(listener).not.toHaveBeenCalled();
  });

  it("clearAuthState resets to empty", () => {
    setAuthState({ accessToken: "token-1", user: USER });

    clearAuthState();

    expect(getAuthState()).toEqual({ accessToken: null, user: null });
  });
});

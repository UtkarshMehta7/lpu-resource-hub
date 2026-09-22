import { useEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from "react";

import { loginRequest, logoutRequest, refreshRequest, registerRequest } from "./api";
import { AuthContext, type AuthContextValue } from "./authContext";
import { clearAuthState, getAuthState, setAuthState, subscribeAuthState } from "./tokenStore";

export function AuthProvider({ children }: { children: ReactNode }) {
  const state = useSyncExternalStore(subscribeAuthState, getAuthState);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    refreshRequest()
      .then((result) => {
        if (cancelled) return;
        setAuthState({ accessToken: result.access_token, user: result.user });
      })
      .catch(() => {
        if (cancelled) return;
        clearAuthState();
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user: state.user,
      isAuthenticated: state.accessToken !== null && state.user !== null,
      isLoading,
      login: async (payload) => {
        const result = await loginRequest(payload);
        setAuthState({ accessToken: result.access_token, user: result.user });
      },
      register: async (payload) => {
        const result = await registerRequest(payload);
        setAuthState({ accessToken: result.access_token, user: result.user });
      },
      logout: async () => {
        await logoutRequest().catch(() => undefined);
        clearAuthState();
      },
    }),
    [state.accessToken, state.user, isLoading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

import { createContext, useContext } from "react";

import type { LoginPayload, RegisterPayload, UserRead } from "./types";

export interface AuthContextValue {
  user: UserRead | null;
  isAuthenticated: boolean;
  /** True until the initial silent-refresh attempt (on mount) settles. */
  isLoading: boolean;
  login: (payload: LoginPayload) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

import type { UserRead } from "./types";

/**
 * Module-level session state (access token + user), outside React.
 * The axios interceptor in lib/api/client.ts reads/writes this directly,
 * since it isn't a component; AuthProvider mirrors it into React via
 * useSyncExternalStore. The access token lives only in memory by design
 * (never localStorage), so it is lost on reload -- AuthProvider restores it
 * with a silent refresh on mount.
 */
export interface AuthState {
  accessToken: string | null;
  user: UserRead | null;
}

type Listener = () => void;

const EMPTY_STATE: AuthState = { accessToken: null, user: null };

let state: AuthState = EMPTY_STATE;
const listeners = new Set<Listener>();

export function getAuthState(): AuthState {
  return state;
}

export function setAuthState(next: AuthState): void {
  state = next;
  listeners.forEach((listener) => {
    listener();
  });
}

export function clearAuthState(): void {
  setAuthState(EMPTY_STATE);
}

export function subscribeAuthState(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

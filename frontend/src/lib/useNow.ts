import { useSyncExternalStore } from "react";

/**
 * The current time as an external store, so components never read the clock
 * while rendering (two renders of the same state must agree).
 *
 * The snapshot is rounded down to the minute: that keeps it stable within a
 * render pass, which `useSyncExternalStore` requires, and a minute's
 * resolution is all any "has this started yet?" check here needs.
 */
const TICK_MS = 60_000;

const listeners = new Set<() => void>();
let timer: ReturnType<typeof setInterval> | null = null;

function subscribe(onStoreChange: () => void): () => void {
  listeners.add(onStoreChange);
  timer ??= setInterval(() => {
    for (const listener of listeners) listener();
  }, TICK_MS);
  return () => {
    listeners.delete(onStoreChange);
    if (listeners.size === 0 && timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  };
}

function getSnapshot(): number {
  return Math.floor(Date.now() / TICK_MS) * TICK_MS;
}

/** Server-side/prerender has no clock to read, so it reports 0. */
function getServerSnapshot(): number {
  return 0;
}

export function useNow(): number {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

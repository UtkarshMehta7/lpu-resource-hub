import { useCallback, useEffect, useState } from "react";

import { type ApiError, toApiError } from "@/lib/api/errors";

import { fetchReadiness } from "./api";

export type BackendHealth =
  | { state: "loading" }
  | { state: "connected"; checkedAt: Date }
  | { state: "degraded"; checkedAt: Date }
  | { state: "unreachable"; error: ApiError; checkedAt: Date };

/** Checks backend readiness on mount and whenever `retry` is called. */
export function useBackendHealth(): { health: BackendHealth; retry: () => void } {
  const [attempt, setAttempt] = useState(0);
  const [health, setHealth] = useState<BackendHealth>({ state: "loading" });

  useEffect(() => {
    const controller = new AbortController();

    void fetchReadiness(controller.signal)
      .then((result) => {
        const healthy = result.status === "ok" && result.database === "ok";
        setHealth({ state: healthy ? "connected" : "degraded", checkedAt: new Date() });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setHealth({ state: "unreachable", error: toApiError(error), checkedAt: new Date() });
      });

    return () => {
      controller.abort();
    };
  }, [attempt]);

  const retry = useCallback(() => {
    setHealth({ state: "loading" });
    setAttempt((value) => value + 1);
  }, []);

  return { health, retry };
}

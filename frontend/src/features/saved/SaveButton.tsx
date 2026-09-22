import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { toApiError } from "@/lib/api/errors";

import { fetchSaved, saveItem, unsaveItem, type SaveTarget, type SavedType } from "./api";

/** Bookmark toggle. Reads the saved list so the state survives a reload. */
export function SaveButton({ type, targetId }: { type: SavedType; targetId: string }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const { data: saved } = useQuery({ queryKey: ["saved", type], queryFn: () => fetchSaved(type) });
  const existing = saved?.find((entry) => idOf(entry.item) === targetId);

  const toggle = useMutation({
    mutationFn: async () => {
      if (existing) {
        await unsaveItem(existing.id);
        return;
      }
      const targets: Record<SavedType, SaveTarget> = {
        project: { project_id: targetId },
        opportunity: { opportunity_id: targetId },
        researcher: { researcher_id: targetId },
        funding: { funding_id: targetId },
      };
      const target = targets[type];
      await saveItem(target);
    },
    onSuccess: async () => {
      setError(null);
      await queryClient.invalidateQueries({ queryKey: ["saved"] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (caught) => setError(toApiError(caught).message),
  });

  return (
    <>
      <button
        type="button"
        aria-pressed={Boolean(existing)}
        disabled={toggle.isPending}
        onClick={() => toggle.mutate()}
        className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm font-medium disabled:opacity-60"
      >
        {existing ? "★ Saved" : "☆ Save"}
      </button>
      {error ? (
        <p role="alert" className="mt-1 text-xs text-red-700">
          {error}
        </p>
      ) : null}
    </>
  );
}

function idOf(item: SavedEntryItem): string {
  return "user_id" in item ? item.user_id : item.id;
}

type SavedEntryItem = { user_id: string } | { id: string };

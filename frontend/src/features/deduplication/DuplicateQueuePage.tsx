import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { SkeletonList } from "@/components/ui/Skeleton";
import { toApiError } from "@/lib/api/errors";

import { decideDuplicate, fetchDuplicates, scanForDuplicates, undoDuplicateMerge } from "./api";
import { DuplicateCard } from "./DuplicateCard";
import type { DuplicateStatus, ScanResult } from "./types";
import { STATUS_LABELS } from "./types";

const FILTERS: { value: DuplicateStatus | "all"; label: string }[] = [
  { value: "suspected", label: STATUS_LABELS.suspected },
  { value: "merged", label: STATUS_LABELS.merged },
  { value: "separate", label: STATUS_LABELS.separate },
  { value: "ignored", label: STATUS_LABELS.ignored },
  { value: "all", label: "Everything" },
];

/**
 * The publication de-duplication review queue.
 *
 * Duplicates get into the database in ways the importer cannot prevent: two
 * researchers each add the same paper, or a hand-typed record is later matched
 * by an import carrying a DOI. A machine merges only what it is certain about
 * (title similarity 92 and above, on the way in); this is the band below that,
 * where a person decides.
 *
 * Scanning is a button rather than something that runs on its own, because a
 * reviewer wants a stable list to work down rather than one shifting under
 * them.
 */
export function DuplicateQueuePage() {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<DuplicateStatus | "all">("suspected");
  const [error, setError] = useState<string | null>(null);
  const [lastScan, setLastScan] = useState<ScanResult | null>(null);

  const { data, isPending, isError } = useQuery({
    queryKey: ["duplicates", filter],
    queryFn: () => fetchDuplicates(filter === "all" ? {} : { status: filter }),
  });

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["duplicates"] });
    await queryClient.invalidateQueries({ queryKey: ["publications"] });
  };

  const scan = useMutation({
    mutationFn: () => scanForDuplicates(),
    onSuccess: async (result) => {
      setError(null);
      setLastScan(result);
      await refresh();
    },
    onError: (caught) => setError(toApiError(caught).message),
  });

  const decide = useMutation({
    mutationFn: ({
      id,
      action,
      keepId,
    }: {
      id: string;
      action: "merge" | "separate" | "ignore";
      keepId?: string;
    }) => decideDuplicate(id, action, keepId ? { keep_id: keepId } : {}),
    onSuccess: async () => {
      setError(null);
      await refresh();
    },
    onError: (caught) => setError(toApiError(caught).message),
  });

  const undo = useMutation({
    // Wrapped rather than passed by reference: the mutation calls its
    // function with more than one argument, and a bare reference would
    // forward all of them.
    mutationFn: (id: string) => undoDuplicateMerge(id),
    onSuccess: async () => {
      setError(null);
      await refresh();
    },
    onError: (caught) => setError(toApiError(caught).message),
  });

  const busy = scan.isPending || decide.isPending || undo.isPending;

  return (
    <div>
      <PageHeader
        title="Duplicate publications"
        description="Pairs of records that may describe the same work. Merging keeps one record, carries the other's authors and project links across, and removes it — so read both before deciding. Every merge can be undone."
        actions={
          <button
            type="button"
            disabled={busy}
            onClick={() => scan.mutate()}
            className="rounded-md bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-800 disabled:opacity-50"
          >
            {scan.isPending ? "Scanning…" : "Scan for duplicates"}
          </button>
        }
      />

      {lastScan ? (
        <p className="mb-4 rounded-card border border-brand-200 bg-brand-50 p-3 text-sm">
          Examined {lastScan.examined} publications and found {lastScan.pairs_found}{" "}
          {lastScan.pairs_found === 1 ? "pair" : "pairs"}: {lastScan.pairs_new} new,{" "}
          {lastScan.pairs_already_decided} already decided.
        </p>
      ) : null}

      {error ? (
        <p role="alert" className="mb-4 text-sm text-red-700">
          {error}
        </p>
      ) : null}

      <div className="mb-4 flex flex-wrap gap-2">
        {FILTERS.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => setFilter(option.value)}
            aria-pressed={filter === option.value}
            className={`rounded-full border px-3 py-1 text-sm ${
              filter === option.value
                ? "border-brand-300 bg-brand-50 font-medium text-brand-800"
                : "border-line bg-surface text-ink-muted hover:bg-canvas"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>

      {isPending ? <SkeletonList /> : null}
      {isError ? (
        <p role="alert" className="text-sm text-red-700">
          Could not load the queue.
        </p>
      ) : null}

      {data && data.items.length === 0 ? (
        <EmptyState
          title={filter === "suspected" ? "Nothing waiting" : "Nothing here"}
          description={
            filter === "suspected"
              ? "No suspected duplicates. Run a scan after an import or a batch of new records."
              : "No reviews in this state yet."
          }
        />
      ) : null}

      <ul className="space-y-4">
        {data?.items.map((review) => (
          <DuplicateCard
            key={review.id}
            review={review}
            busy={busy}
            onMerge={(keepId) => decide.mutate({ id: review.id, action: "merge", keepId })}
            onSeparate={() => decide.mutate({ id: review.id, action: "separate" })}
            onIgnore={() => decide.mutate({ id: review.id, action: "ignore" })}
            onUndo={() => undo.mutate(review.id)}
          />
        ))}
      </ul>
    </div>
  );
}

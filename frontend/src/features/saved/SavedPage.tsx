import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonList } from "@/components/ui/Skeleton";

import { fetchSaved, type SavedEntry, type SavedType } from "./api";

const TABS: { value: SavedType | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "project", label: "Projects" },
  { value: "opportunity", label: "Opportunities" },
  { value: "researcher", label: "Researchers" },
];

const TAB =
  "rounded-md border border-line px-3 py-1.5 text-sm font-medium aria-selected:bg-brand-700 aria-selected:text-white";

export function SavedPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const raw = searchParams.get("type");
  const active = TABS.find((tab) => tab.value === raw)?.value ?? "all";
  const type = active === "all" ? undefined : active;

  const { data, isPending, isError } = useQuery({
    queryKey: ["saved", type ?? "all"],
    queryFn: () => fetchSaved(type),
  });

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Saved</h1>
      <div className="mt-4 flex flex-wrap gap-2" role="tablist">
        {TABS.map((tab) => (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={active === tab.value}
            onClick={() => setSearchParams(tab.value === "all" ? {} : { type: tab.value })}
            className={TAB}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {isPending ? (
        <div className="mt-6">
          <SkeletonList />
        </div>
      ) : null}
      {isError ? (
        <p role="alert" className="mt-6 text-sm text-red-700">
          Could not load your saved items.
        </p>
      ) : null}
      {data && data.length === 0 ? (
        <div className="mt-6">
          <EmptyState
            title="Nothing saved yet"
            description="Save a project, opportunity or researcher to find it again quickly."
            actionLabel="Browse opportunities"
            actionTo="/opportunities"
          />
        </div>
      ) : null}

      <ul className="mt-6 space-y-3">
        {data?.map((entry) => (
          <li key={entry.id} className="rounded-card border border-line bg-surface p-4">
            <Link to={linkFor(entry)} className="text-sm font-semibold hover:underline">
              {titleFor(entry)}
            </Link>
            <p className="mt-1 text-xs text-ink-muted">
              Saved {new Date(entry.created_at).toLocaleDateString()}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}

function titleFor(entry: SavedEntry): string {
  return "full_name" in entry.item ? entry.item.full_name : entry.item.title;
}

function linkFor(entry: SavedEntry): string {
  if (entry.saved_type === "researcher" && "user_id" in entry.item) {
    return `/researchers/${entry.item.user_id}`;
  }
  const base = entry.saved_type === "project" ? "/projects" : "/opportunities";
  return "id" in entry.item ? `${base}/${entry.item.id}` : base;
}

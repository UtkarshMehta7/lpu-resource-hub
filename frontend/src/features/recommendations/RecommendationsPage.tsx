import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { fetchRecommendations, RECOMMENDATION_TABS, type RecommendationType } from "./api";
import { describe } from "./describe";

const TAB =
  "rounded-md border border-line px-3 py-1.5 text-sm font-medium aria-selected:bg-brand-700 aria-selected:text-white";

/** "Recommended for you", with the reasons behind every suggestion. */
export function RecommendationsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const raw = searchParams.get("type");
  const type: RecommendationType =
    RECOMMENDATION_TABS.find((tab) => tab.value === raw)?.value ?? "opportunities";

  const { data, isPending, isError } = useQuery({
    queryKey: ["recommendations", type],
    queryFn: () => fetchRecommendations(type),
  });

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Recommended for you</h1>
      <p className="mt-1 text-sm text-ink-muted">
        Matched on your skills, research areas and what you&apos;ve written about your work. Every
        suggestion says why.
      </p>

      <div className="mt-4 flex flex-wrap gap-2" role="tablist">
        {RECOMMENDATION_TABS.map((tab) => (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={type === tab.value}
            onClick={() => setSearchParams({ type: tab.value })}
            className={TAB}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {isPending ? <p className="mt-6 text-sm text-ink-muted">Finding matches…</p> : null}
      {isError ? (
        <p role="alert" className="mt-6 text-sm text-red-700">
          Could not load recommendations.
        </p>
      ) : null}

      {data?.cold_start ? (
        <p className="mt-6 rounded-card border border-line bg-surface px-4 py-3 text-sm">
          Your profile is still sparse, so these are simply the newest items.{" "}
          <Link to="/profile" className="text-brand-700 hover:underline">
            Add your skills and research areas
          </Link>{" "}
          to get real matches.
        </p>
      ) : null}

      {data && data.items.length === 0 ? (
        <p className="mt-6 rounded-card border border-line bg-surface px-4 py-6 text-sm text-ink-muted">
          Nothing to suggest here yet.
        </p>
      ) : null}

      <ul className="mt-6 space-y-3">
        {data?.items.map((recommendation) => {
          const summary = describe(recommendation.item);
          return (
            <li
              key={recommendation.item_id}
              className="rounded-card border border-line bg-surface p-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <Link to={summary.to} className="text-sm font-semibold hover:underline">
                  {summary.title}
                </Link>
                {!data.cold_start ? (
                  <span
                    className="rounded-md border border-line px-2 py-1 text-xs text-ink-muted"
                    title="Match score between 0 and 1"
                  >
                    Match {recommendation.score.toFixed(2)}
                  </span>
                ) : null}
              </div>
              <p className="mt-1 text-xs text-ink-muted">{summary.subtitle}</p>
              <details className="mt-2">
                <summary className="cursor-pointer text-xs font-medium text-brand-700">
                  Why this?
                </summary>
                <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-ink-muted">
                  {recommendation.reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              </details>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

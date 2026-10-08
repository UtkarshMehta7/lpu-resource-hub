import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { SkeletonList } from "@/components/ui/Skeleton";
import { StatusPill } from "@/components/ui/StatusPill";
import { Uid } from "@/components/ui/Uid";

import { fetchReviewQueue } from "./api";
import { officeLabel, STATUS_LABEL, STATUS_TONE } from "./labels";

/**
 * Patent records waiting on this reviewer.
 *
 * The backend filters this through the same scope rule the decision
 * enforces, so a row here is always one this reader could actually decide --
 * the dead-button mistake the project review queue exists to avoid.
 */
export function PatentReviewQueuePage() {
  const { data, isPending, isError } = useQuery({
    queryKey: ["patent-review-queue"],
    queryFn: fetchReviewQueue,
  });

  return (
    <div>
      <PageHeader
        title="Patents to check"
        description="Records entered by people in your department. You are checking the numbers, dates and inventors — not whether the invention deserves a patent."
      />

      {isPending ? <SkeletonList rows={3} /> : null}
      {isError ? <p className="text-sm text-red-700">The queue could not be loaded.</p> : null}

      {data && data.length === 0 ? (
        <EmptyState
          title="Nothing waiting"
          description="Every patent recorded in your department has been checked."
        />
      ) : null}

      <ul className="space-y-3">
        {data?.map((patent) => (
          <li key={patent.id} className="rounded-card border border-line bg-surface p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <Link
                to={`/patents/${patent.id}`}
                className="text-base font-semibold text-brand-800 hover:underline"
              >
                {patent.title}
              </Link>
              <StatusPill tone={STATUS_TONE[patent.status]}>
                {STATUS_LABEL[patent.status]}
              </StatusPill>
            </div>
            <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-ink-muted">
              Recorded by {patent.creator_name}
              {patent.inventors[0]?.registration_number ? (
                <Uid value={patent.inventors[0].registration_number} />
              ) : null}
            </p>
            <p className="mt-1 text-xs text-ink-muted">
              {officeLabel(patent.jurisdiction)} · filed {patent.filing_date}
              {patent.application_number ? ` · application ${patent.application_number}` : ""}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}

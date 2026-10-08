import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { SkeletonList } from "@/components/ui/Skeleton";
import { StatusPill } from "@/components/ui/StatusPill";
import { Uid } from "@/components/ui/Uid";

import { fetchReviewQueue } from "./api";
import {
  BEFORE_THE_OFFICE,
  officeLabel,
  STATUS_LABEL,
  STATUS_TONE,
  VERIFICATION_LABEL,
  VERIFICATION_TONE,
} from "./labels";

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
        title="Patents and disclosures"
        description="Two kinds of waiting, in one place: inventions put to the university for assessment, and records whose numbers nobody has checked yet. Both are from your department."
      />

      {isPending ? <SkeletonList rows={3} /> : null}
      {isError ? <p className="text-sm text-red-700">The queue could not be loaded.</p> : null}

      {data && data.length === 0 ? (
        <EmptyState
          title="Nothing waiting"
          description="Every disclosure has been assessed and every record checked."
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
              <div className="flex shrink-0 gap-2">
                <StatusPill tone={STATUS_TONE[patent.status]}>
                  {STATUS_LABEL[patent.status]}
                </StatusPill>
                {patent.verification_status === "pending" ? (
                  <StatusPill tone={VERIFICATION_TONE.pending}>
                    {VERIFICATION_LABEL.pending}
                  </StatusPill>
                ) : null}
              </div>
            </div>
            <p className="mt-1 text-sm font-medium text-brand-700">
              {BEFORE_THE_OFFICE.has(patent.status)
                ? "Decide whether the university files this"
                : "Check the numbers, dates and inventors"}
            </p>
            {patent.public_disclosure_date ? (
              <p className="mt-1 text-sm text-amber-800">
                Already public on {patent.public_disclosure_date} — may affect novelty.
              </p>
            ) : null}
            <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-ink-muted">
              {BEFORE_THE_OFFICE.has(patent.status) ? "Disclosed" : "Recorded"} by{" "}
              {patent.creator_name}
              {patent.inventors[0]?.registration_number ? (
                <Uid value={patent.inventors[0].registration_number} />
              ) : null}
            </p>
            <p className="mt-1 text-xs text-ink-muted">
              {officeLabel(patent.jurisdiction)}
              {patent.reference ? ` · ${patent.reference}` : ""}
              {patent.filing_date ? ` · filed ${patent.filing_date}` : ""}
              {patent.application_number ? ` · application ${patent.application_number}` : ""}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}

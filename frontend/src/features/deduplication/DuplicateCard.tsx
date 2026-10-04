import { StatusPill } from "@/components/ui/StatusPill";

import type { DuplicateEvidence, DuplicateReview, PublicationSide } from "./types";
import { STATUS_LABELS, STATUS_TONES } from "./types";

/**
 * One suspected pair, side by side.
 *
 * The two records are shown in full with their DOIs as links, because the
 * whole decision rests on reading them: a merge deletes one of them. Every
 * reason the pair was suggested is listed, so a reviewer is not asked to
 * trust a similarity score on its own.
 */
function Side({
  side,
  label,
  onKeep,
  busy,
}: {
  side: PublicationSide | null;
  label: string;
  onKeep?: () => void;
  busy: boolean;
}) {
  if (!side) {
    return (
      <div className="rounded-card border border-dashed border-line p-4 text-sm text-ink-muted">
        {label}: this record no longer exists.
      </div>
    );
  }
  return (
    <div className="flex flex-col rounded-card border border-line bg-surface p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">{label}</p>
      <h3 className="mt-1 text-sm font-semibold">{side.title}</h3>
      <dl className="mt-2 space-y-1 text-xs text-ink-muted">
        <div>
          <dt className="sr-only">Year and venue</dt>
          <dd>{[side.year, side.venue].filter(Boolean).join(" · ") || "No year or venue"}</dd>
        </div>
        <div>
          <dt className="sr-only">Authors</dt>
          <dd>{side.authors.length ? side.authors.join(", ") : "No authors recorded"}</dd>
        </div>
        <div>
          <dt className="sr-only">DOI</dt>
          <dd>
            {side.doi ? (
              <a
                href={`https://doi.org/${side.doi}`}
                target="_blank"
                rel="noreferrer noopener"
                className="font-medium text-brand-700 hover:underline"
              >
                {side.doi}
              </a>
            ) : (
              "No DOI"
            )}
          </dd>
        </div>
        <div>
          <dt className="sr-only">Linked projects</dt>
          <dd>
            {side.project_count === 1
              ? "Linked to 1 project"
              : `Linked to ${side.project_count} projects`}
          </dd>
        </div>
      </dl>
      {onKeep ? (
        <button
          type="button"
          disabled={busy}
          onClick={onKeep}
          className="mt-3 rounded-md bg-brand-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-800 disabled:opacity-50"
        >
          Keep this one
        </button>
      ) : null}
    </div>
  );
}

/** Every reason the pair was offered, in words rather than as a score. */
function Evidence({ evidence, score }: { evidence: DuplicateEvidence; score: number }) {
  const reasons: string[] = [`Titles ${Math.round(score)}% alike`];
  if (evidence.identical_normalised_title) reasons.push("identical once punctuation is ignored");
  if (evidence.same_year) reasons.push("same year");
  else if (evidence.years?.some(Boolean)) reasons.push(`years ${evidence.years.join(" and ")}`);
  if (evidence.shared_doi) reasons.push("same DOI");
  if (evidence.doi_on_one_side_only) reasons.push("only one side has a DOI");
  if (evidence.same_venue) reasons.push("same venue");
  if (evidence.shared_author_count) {
    reasons.push(
      evidence.shared_author_count === 1
        ? "1 author in common"
        : `${evidence.shared_author_count} authors in common`,
    );
  }
  return <p className="mt-3 text-xs text-ink-muted">Suggested because: {reasons.join(", ")}.</p>;
}

export function DuplicateCard({
  review,
  busy,
  onMerge,
  onSeparate,
  onIgnore,
  onUndo,
}: {
  review: DuplicateReview;
  busy: boolean;
  onMerge: (keepId: string) => void;
  onSeparate: () => void;
  onIgnore: () => void;
  onUndo: () => void;
}) {
  const open = review.status === "suspected";
  return (
    <li className="rounded-card border border-line bg-canvas p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <StatusPill tone={STATUS_TONES[review.status]}>{STATUS_LABELS[review.status]}</StatusPill>
        {review.decided_by_name ? (
          <p className="text-xs text-ink-muted">Decided by {review.decided_by_name}</p>
        ) : null}
      </div>

      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <Side
          side={review.publication_a}
          label="Record A"
          busy={busy}
          onKeep={
            open && review.publication_a ? () => onMerge(review.publication_a?.id ?? "") : undefined
          }
        />
        <Side
          side={review.publication_b}
          label="Record B"
          busy={busy}
          onKeep={
            open && review.publication_b ? () => onMerge(review.publication_b?.id ?? "") : undefined
          }
        />
      </div>

      <Evidence evidence={review.evidence} score={review.score} />

      {review.decision_note ? (
        <p className="mt-2 text-xs text-ink-muted">Note: {review.decision_note}</p>
      ) : null}

      <div className="mt-3 flex flex-wrap gap-2">
        {open ? (
          <>
            <button
              type="button"
              disabled={busy}
              onClick={onSeparate}
              className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm font-medium hover:bg-canvas disabled:opacity-50"
            >
              Mark as different
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={onIgnore}
              className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm text-ink-muted hover:bg-canvas disabled:opacity-50"
            >
              Decide later
            </button>
          </>
        ) : null}
        {review.can_undo ? (
          <button
            type="button"
            disabled={busy}
            onClick={onUndo}
            className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm font-medium hover:bg-canvas disabled:opacity-50"
          >
            Undo merge
          </button>
        ) : null}
      </div>

      {review.status === "merged" && !review.can_undo ? (
        <p className="mt-2 text-xs text-ink-muted">
          This merge can no longer be undone, because the record it removed is no longer held.
        </p>
      ) : null}
    </li>
  );
}

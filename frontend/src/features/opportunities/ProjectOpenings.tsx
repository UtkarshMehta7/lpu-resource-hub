import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { ButtonLink } from "@/components/ui/Button";
import { StatusPill } from "@/components/ui/StatusPill";
import { useAuth } from "@/features/auth/authContext";
import { useNow } from "@/lib/useNow";

import { fetchOpportunities, type OpportunityCard } from "./api";
import { canApplyAs, TYPE_LABEL } from "./labels";

/** Roles that may post an opening. Mirrors Permission.OPPORTUNITY_CREATE. */
const CAN_POST = new Set(["faculty", "research_coordinator"]);

function daysLeft(deadline: string, now: number): number | null {
  if (now === 0) return null;
  const target = new Date(`${deadline}T00:00:00`).getTime();
  return Math.ceil((target - now) / (24 * 60 * 60 * 1000));
}

function deadlineLabel(deadline: string, now: number): string {
  const left = daysLeft(deadline, now);
  const date = new Date(`${deadline}T00:00:00`).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
  if (left === null) return `Closes ${date}`;
  if (left < 0) return `Closed ${date}`;
  if (left === 0) return `Closes today, ${date}`;
  if (left === 1) return `Closes tomorrow, ${date}`;
  return `Closes in ${left} days, ${date}`;
}

function Opening({ opening, now }: { opening: OpportunityCard; now: number }) {
  const left = daysLeft(opening.deadline, now);
  const remaining = opening.positions - opening.accepted_count;
  const closingSoon = left !== null && left >= 0 && left <= 7;

  return (
    <li className="rounded-card border border-line bg-surface">
      <Link
        to={`/opportunities/${opening.id}`}
        className="block px-4 py-3 hover:bg-canvas focus-visible:bg-canvas"
      >
        <div className="flex flex-wrap items-start justify-between gap-2">
          <p className="min-w-0 text-sm font-medium">{opening.title}</p>
          <span className="flex shrink-0 items-center gap-2">
            <StatusPill tone="neutral">{TYPE_LABEL[opening.opportunity_type]}</StatusPill>
            {/* A deadline inside a week is the thing a reader is deciding
                on, so it is coloured rather than left to be worked out from
                a date. */}
            {closingSoon ? <StatusPill tone="warning">Closing soon</StatusPill> : null}
          </span>
        </div>
        <p className="mt-1 text-xs text-ink-muted">
          {remaining > 0
            ? `${remaining} of ${opening.positions} place${opening.positions === 1 ? "" : "s"} left`
            : "All places taken"}{" "}
          · {deadlineLabel(opening.deadline, now)}
        </p>
      </Link>
    </li>
  );
}

/**
 * The openings on a project, and the way in.
 *
 * A project page used to say nothing about its openings, so somebody who had
 * just read about a project and wanted to join it had nowhere to go: you
 * apply to an OPPORTUNITY, and the only link between the two ran the other
 * way (`Opportunity.project_id`). Finding the right opening meant going back
 * to the board and recognising it by name.
 *
 * Only OPEN openings are listed. A draft belongs to its author and a closed
 * one is not a way in, so showing either here would be offering a door that
 * does not open.
 */
export function ProjectOpenings({ projectId, isOwner }: { projectId: string; isOwner: boolean }) {
  const { user } = useAuth();
  const now = useNow();
  const { data, isError } = useQuery({
    queryKey: ["opportunities", { project_id: projectId, status: "open" }],
    queryFn: () => fetchOpportunities({ project_id: projectId, status: "open" }),
  });

  const openings = data?.items ?? [];
  const canPost = user ? CAN_POST.has(user.role) : false;
  // Whether this reader could apply to ANY of them. The opening's own page
  // runs the real check; this only decides whether to explain the way in.
  const couldApply = Boolean(
    user && openings.some((opening) => canApplyAs(user.role, opening.opportunity_type)),
  );

  // A project with no openings and a reader who cannot post one has nothing
  // to act on, so the section stays off the page rather than adding an empty
  // heading to every project anybody reads.
  //
  // An ERROR is not that case, and is shown to everyone. If the lookup
  // failed we do not know whether this project has openings, and silence
  // would be read as "none" -- somebody who would have applied moves on
  // instead of retrying. The same reason the prior-art panel names the
  // source it could not reach rather than quietly returning a short list.
  if (!isError && openings.length === 0 && !(isOwner && canPost)) return null;

  return (
    <section className="mt-8">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold">Open positions</h2>
        {isOwner && canPost ? (
          <ButtonLink to="/opportunities/new" variant="secondary" size="sm">
            Post an opening
          </ButtonLink>
        ) : null}
      </div>

      {isError ? (
        <p className="mt-2 text-sm text-ink-muted">Open positions could not be loaded.</p>
      ) : openings.length === 0 ? (
        <p className="mt-2 text-sm text-ink-muted">
          No open positions on this project. Post one and it appears on the opportunities board.
        </p>
      ) : (
        <>
          {couldApply ? (
            <p className="mt-1 text-sm text-ink-muted">
              Open the position you want and apply from there.
            </p>
          ) : null}
          <ul className="mt-2 space-y-2">
            {openings.map((opening) => (
              <Opening key={opening.id} opening={opening} now={now} />
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

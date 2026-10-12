import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { ButtonLink } from "@/components/ui/Button";
import { StatusPill, type PillTone } from "@/components/ui/StatusPill";
import { useAuth } from "@/features/auth/authContext";
import { useNow } from "@/lib/useNow";

import { fetchOpportunities, type OpportunityCard } from "./api";
import { canApplyAs, OPPORTUNITY_STATUS_LABEL, TYPE_LABEL, type OpportunityStatus } from "./labels";

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

const STATUS_TONE: Record<OpportunityStatus, PillTone> = {
  draft: "warning",
  open: "positive",
  closed: "neutral",
  filled: "info",
};

function Opening({
  opening,
  now,
  isLead,
}: {
  opening: OpportunityCard;
  now: number;
  isLead: boolean;
}) {
  const left = daysLeft(opening.deadline, now);
  const remaining = opening.positions - opening.accepted_count;
  const closingSoon = left !== null && left >= 0 && left <= 7;
  // Absent on an older API, which the deploy window makes a real state rather
  // than a theoretical one, so every use defaults.
  const applications = opening.application_count ?? 0;
  const waiting = opening.pending_application_count ?? 0;

  return (
    <li className="rounded-card border border-line bg-surface">
      <Link
        to={`/opportunities/${opening.id}`}
        className="block px-4 py-3 hover:bg-canvas focus-visible:bg-canvas"
      >
        <div className="flex flex-wrap items-start justify-between gap-2">
          <p className="min-w-0 text-sm font-medium">{opening.title}</p>
          <span className="flex shrink-0 flex-wrap items-center gap-2">
            <StatusPill tone="neutral">{TYPE_LABEL[opening.opportunity_type]}</StatusPill>
            {/* The lead is looking at their own openings, so the state of each
                one is the first thing they need: a DRAFT is why an opening
                they just posted is not being applied for. */}
            {isLead ? (
              <StatusPill tone={STATUS_TONE[opening.status]}>
                {OPPORTUNITY_STATUS_LABEL[opening.status]}
              </StatusPill>
            ) : null}
            {/* A deadline inside a week is the thing a reader is deciding
                on, so it is coloured rather than left to be worked out from
                a date. */}
            {closingSoon && opening.status === "open" ? (
              <StatusPill tone="warning">Closing soon</StatusPill>
            ) : null}
          </span>
        </div>
        <p className="mt-1 text-xs text-ink-muted">
          {remaining > 0
            ? `${remaining} of ${opening.positions} place${opening.positions === 1 ? "" : "s"} left`
            : "All places taken"}{" "}
          · {deadlineLabel(opening.deadline, now)}
        </p>
      </Link>

      {/* Only the person who posted it is told how many applied, and it is the
          whole point of putting hiring on the project page: a lead could not
          see that anybody was waiting without opening each opening in turn. */}
      {isLead ? (
        <p className="border-t border-line px-4 py-2 text-xs text-ink-muted">
          {applications === 0 ? (
            "No applications yet."
          ) : (
            <>
              {applications} application{applications === 1 ? "" : "s"}
              {waiting > 0 ? (
                <>
                  {" · "}
                  <span className="font-medium text-brand-700">{waiting} waiting on you</span>
                </>
              ) : null}{" "}
              ·{" "}
              <Link
                to={`/opportunities/${opening.id}/applicants`}
                className="font-medium text-brand-700 hover:underline"
              >
                Review applicants
              </Link>
            </>
          )}
        </p>
      ) : null}
    </li>
  );
}

/**
 * Hiring on a project: the openings under it, and the way in.
 *
 * A project page used to say nothing about its openings, so somebody who had
 * just read about a project and wanted to join it had nowhere to go: you
 * apply to an OPPORTUNITY, and the only link between the two runs the other
 * way (`Opportunity.project_id`). Finding the right opening meant going back
 * to the board and recognising it by name.
 *
 * The two readers want opposite things, so they are served differently from
 * one payload:
 *
 * - The **lead** sees every opening on their project, DRAFTS included, with
 *   its state and how many people are waiting on them. Filtering this to
 *   `open` meant posting an opening from here and watching the section go on
 *   saying there were none -- an opening is created as a draft, and the draft
 *   stage is load-bearing, not decoration.
 * - **Everybody else** sees only the OPEN ones. A draft belongs to its author
 *   and a closed one is not a way in, so showing either here would be
 *   offering a door that does not open.
 */
export function ProjectOpenings({ projectId, isOwner }: { projectId: string; isOwner: boolean }) {
  const { user } = useAuth();
  const now = useNow();
  const canPost = user ? CAN_POST.has(user.role) : false;
  const isLead = isOwner && canPost;

  const { data, isError } = useQuery({
    queryKey: ["opportunities", { project_id: projectId, status: isLead ? "all" : "open" }],
    queryFn: () =>
      fetchOpportunities(
        isLead ? { project_id: projectId } : { project_id: projectId, status: "open" },
      ),
  });

  const openings = data?.items ?? [];
  // Whether this reader could apply to ANY of them. The opening's own page
  // runs the real check; this only decides whether to explain the way in.
  const couldApply = Boolean(
    user &&
    openings.some(
      (opening) => opening.status === "open" && canApplyAs(user.role, opening.opportunity_type),
    ),
  );
  const waitingOnMe = isLead
    ? openings.reduce((total, opening) => total + (opening.pending_application_count ?? 0), 0)
    : 0;

  // A project with no openings and a reader who cannot post one has nothing
  // to act on, so the section stays off the page rather than adding an empty
  // heading to every project anybody reads.
  //
  // An ERROR is not that case, and is shown to everyone. If the lookup
  // failed we do not know whether this project has openings, and silence
  // would be read as "none" -- somebody who would have applied moves on
  // instead of retrying. The same reason the prior-art panel names the
  // source it could not reach rather than quietly returning a short list.
  if (!isError && openings.length === 0 && !isLead) return null;

  return (
    <section className="mt-8">
      <div className="flex flex-wrap items-center justify-between gap-2">
        {/* Two names for two views, deliberately. The lead's list contains
            drafts and closed openings, and calling that "Open positions"
            would be false on the face of it; a reader's list is only ever
            what is open. */}
        <h2 className="text-base font-semibold">{isLead ? "Hiring" : "Open positions"}</h2>
        {isLead ? (
          // Carries the project, so the form arrives knowing which project it
          // is hiring for. Without it a lead who came from here had to find
          // their own project again in a dropdown.
          <ButtonLink
            to={`/opportunities/new?project_id=${projectId}`}
            variant="secondary"
            size="sm"
          >
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
          {isLead && waitingOnMe > 0 ? (
            <p className="mt-1 text-sm font-medium text-brand-700">
              {waitingOnMe} application{waitingOnMe === 1 ? "" : "s"} waiting on a decision.
            </p>
          ) : null}
          {couldApply ? (
            <p className="mt-1 text-sm text-ink-muted">
              Open the position you want and apply from there.
            </p>
          ) : null}
          <ul className="mt-2 space-y-2">
            {openings.map((opening) => (
              <Opening key={opening.id} opening={opening} now={now} isLead={isLead} />
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

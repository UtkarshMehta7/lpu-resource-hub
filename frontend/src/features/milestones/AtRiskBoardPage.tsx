import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { SkeletonList } from "@/components/ui/Skeleton";
import { StatusPill } from "@/components/ui/StatusPill";
import { Uid } from "@/components/ui/Uid";

import { fetchAtRiskProjects } from "./api";
import { RISK_LABELS, RISK_TONES, describeDue, formatDate } from "./labels";
import type { AtRiskProject } from "./types";

/**
 * Projects whose plans are slipping, worst first.
 *
 * Ordered by how much is already overdue rather than by date, because the
 * question this page answers is "where should I spend my attention first",
 * and one project three weeks late matters more than five due on Friday.
 */
export function AtRiskBoardPage() {
  const { data: projects, isPending } = useQuery({
    queryKey: ["at-risk-projects"],
    queryFn: fetchAtRiskProjects,
  });

  return (
    <div>
      <PageHeader
        title="At-risk projects"
        description="Projects with milestones that are overdue, blocked, or due soon. Ordered by how much has already slipped."
      />

      {isPending ? (
        <SkeletonList rows={3} />
      ) : !projects || projects.length === 0 ? (
        <EmptyState
          title="Nothing is slipping"
          description="Every milestone in your scope is either finished or comfortably ahead of its date."
        />
      ) : (
        <ul className="space-y-4">
          {projects.map((project) => (
            <ProjectCard key={project.project_id} project={project} />
          ))}
        </ul>
      )}
    </div>
  );
}

function ProjectCard({ project }: { project: AtRiskProject }) {
  return (
    <li className="rounded-card border border-line bg-surface p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold">
          <Link to={`/projects/${project.project_id}`} className="hover:underline">
            {project.title}
          </Link>
        </h2>
        <span className="flex flex-wrap gap-1.5">
          {project.overdue_count > 0 ? (
            <StatusPill tone="negative">{project.overdue_count} overdue</StatusPill>
          ) : null}
          {project.blocked_count > 0 ? (
            <StatusPill tone="warning">{project.blocked_count} blocked</StatusPill>
          ) : null}
          {project.at_risk_count > 0 ? (
            <StatusPill tone="warning">{project.at_risk_count} due soon</StatusPill>
          ) : null}
        </span>
      </div>

      <p className="mt-1 text-xs text-ink-muted">
        {project.owner_name} · <Uid value={project.owner_registration_number} />
      </p>

      <ul className="mt-3 space-y-1.5">
        {project.milestones.map((milestone) => (
          <li
            key={milestone.id}
            className="flex flex-wrap items-baseline justify-between gap-2 border-t border-line pt-1.5 text-sm"
          >
            <span className="flex flex-wrap items-baseline gap-2">
              <span>{milestone.title}</span>
              <StatusPill tone={RISK_TONES[milestone.risk]}>
                {RISK_LABELS[milestone.risk]}
              </StatusPill>
            </span>
            <span className="text-xs text-ink-muted">
              {formatDate(milestone.due_date)} · {describeDue(milestone.days_until_due)}
            </span>
          </li>
        ))}
      </ul>
    </li>
  );
}

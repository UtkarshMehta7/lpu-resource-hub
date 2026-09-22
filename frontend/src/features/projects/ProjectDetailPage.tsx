import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useAuth } from "@/features/auth/authContext";
import { RequestCollaborationButton } from "@/features/collaborations/RequestCollaborationButton";
import { ReportButton } from "@/features/reports/ReportButton";
import { SaveButton } from "@/features/saved/SaveButton";
import { PublicationsSection } from "@/features/publications/PublicationList";
import { toApiError } from "@/lib/api/errors";

import {
  deleteProject,
  fetchProject,
  removeMember,
  runProjectAction,
  STATUS_LABEL,
  type ProjectAction,
} from "./api";

type PendingAction = ProjectAction | "delete";

const ACTION_COPY: Record<PendingAction, { title: string; body: string; label: string }> = {
  submit: {
    title: "Submit for review?",
    body: "Your department's research coordinator will review it. You can't edit it while it's under review.",
    label: "Submit",
  },
  complete: {
    title: "Mark as completed?",
    body: "The project stays visible as a completed project.",
    label: "Complete",
  },
  archive: {
    title: "Archive this project?",
    body: "Archived projects are hidden from students and other researchers.",
    label: "Archive",
  },
  delete: {
    title: "Delete this draft?",
    body: "Drafts are deleted. Anything already approved is archived instead.",
    label: "Delete",
  },
};

const BUTTON_CLASS =
  "rounded-md border border-line bg-surface px-3 py-1.5 text-sm font-medium hover:bg-canvas disabled:opacity-50";

export function ProjectDetailPage() {
  const { projectId = "" } = useParams<{ projectId: string }>();
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [error, setError] = useState<string | null>(null);

  const {
    data: project,
    isPending,
    isError,
  } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => fetchProject(projectId),
    enabled: Boolean(projectId),
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["project", projectId] });

  const action = useMutation({
    mutationFn: async (which: PendingAction) => {
      if (which === "delete") {
        await deleteProject(projectId);
        return null;
      }
      return runProjectAction(projectId, which);
    },
    onSuccess: async (result) => {
      setPending(null);
      setError(null);
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
      if (result === null) {
        void navigate("/projects/mine", { replace: true });
      } else {
        await refresh();
      }
    },
    onError: (caught: unknown) => {
      setPending(null);
      setError(toApiError(caught).message);
    },
  });

  if (isPending) return <p className="text-sm text-ink-muted">Loading project…</p>;
  if (isError || !project) {
    return (
      <p role="alert" className="text-sm text-red-700">
        This project doesn&apos;t exist or isn&apos;t visible to you.
      </p>
    );
  }

  const isOwner = user?.id === project.owner_id;
  const actions: PendingAction[] = [];
  if (isOwner && project.status === "draft") actions.push("submit", "delete");
  if (isOwner && project.status === "active") actions.push("complete", "archive");
  if (!isOwner && user?.role === "admin" && project.status !== "archived") actions.push("archive");
  const canEdit = isOwner && (project.status === "draft" || project.status === "active");

  return (
    <div className="mx-auto max-w-3xl">
      <Link to="/projects" className="text-sm text-brand-700 hover:underline">
        ← Projects
      </Link>

      <div className="mt-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{project.title}</h1>
          <p className="mt-1 text-sm text-ink-muted">
            Led by{" "}
            <Link to={`/researchers/${project.owner_id}`} className="hover:underline">
              {project.owner_name}
            </Link>
          </p>
          {!isOwner ? (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <SaveButton type="project" targetId={project.id} />
              <ReportButton targetType="project" targetId={project.id} />
              <RequestCollaborationButton
                recipientId={project.owner_id}
                recipientName={project.owner_name}
                projectId={project.id}
              />
            </div>
          ) : null}
        </div>
        <span className="rounded-md border border-line px-2 py-1 text-xs font-medium">
          {STATUS_LABEL[project.status]}
        </span>
      </div>

      {project.review_comment && project.status === "draft" ? (
        <div className="mt-4 rounded-card border border-amber-300 bg-amber-50 px-4 py-3 text-sm">
          <p className="font-medium text-amber-800">Changes requested by the reviewer</p>
          <p className="mt-1 text-amber-800">{project.review_comment}</p>
        </div>
      ) : null}

      {error ? (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {error}
        </p>
      ) : null}

      {canEdit || actions.length > 0 ? (
        <div className="mt-6 flex flex-wrap gap-2">
          {canEdit ? (
            <Link to={`/projects/${project.id}/edit`} className={BUTTON_CLASS}>
              Edit
            </Link>
          ) : null}
          {actions.map((which) => (
            <button
              key={which}
              type="button"
              disabled={action.isPending}
              onClick={() => setPending(which)}
              className={BUTTON_CLASS}
            >
              {ACTION_COPY[which].label}
            </button>
          ))}
        </div>
      ) : null}

      <p className="mt-6 text-sm font-medium">{project.summary}</p>
      <p className="mt-3 whitespace-pre-line text-sm">{project.description}</p>

      {project.objectives ? (
        <section className="mt-8">
          <h2 className="text-base font-semibold">Objectives</h2>
          <p className="mt-2 whitespace-pre-line text-sm">{project.objectives}</p>
        </section>
      ) : null}

      {project.start_date || project.end_date ? (
        <p className="mt-6 text-sm text-ink-muted">
          {project.start_date ?? "?"} → {project.end_date ?? "ongoing"}
        </p>
      ) : null}

      {[...project.research_areas, ...project.skills].length > 0 ? (
        <ul className="mt-6 flex flex-wrap gap-2">
          {[...project.research_areas, ...project.skills].map((tag) => (
            <li
              key={tag}
              className="rounded-md border border-line px-2 py-1 text-xs text-ink-muted"
            >
              {tag}
            </li>
          ))}
        </ul>
      ) : null}

      <section className="mt-8">
        <h2 className="text-base font-semibold">Team</h2>
        {project.members.length === 0 ? (
          <p className="mt-2 text-sm text-ink-muted">No team members yet.</p>
        ) : (
          <ul className="mt-2 divide-y divide-line rounded-card border border-line bg-surface">
            {project.members.map((member) => (
              <li key={member.user_id} className="flex items-center justify-between px-4 py-2">
                <span className="text-sm">
                  {member.full_name} <span className="text-ink-muted">· {member.member_role}</span>
                </span>
                {isOwner ? (
                  <button
                    type="button"
                    className="text-xs text-red-700 hover:underline"
                    onClick={() => {
                      void removeMember(project.id, member.user_id).then(refresh);
                    }}
                  >
                    Remove
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <PublicationsSection filters={{ project_id: project.id }} />

      <ConfirmDialog
        open={pending !== null}
        title={pending ? ACTION_COPY[pending].title : ""}
        description={pending ? ACTION_COPY[pending].body : ""}
        confirmLabel={pending ? ACTION_COPY[pending].label : "Confirm"}
        isConfirming={action.isPending}
        onConfirm={() => {
          if (pending) action.mutate(pending);
        }}
        onCancel={() => setPending(null)}
      />
    </div>
  );
}

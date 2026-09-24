import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useAuth } from "@/features/auth/authContext";
import { toApiError } from "@/lib/api/errors";
import { Uid } from "@/components/ui/Uid";
import { SkeletonList } from "@/components/ui/Skeleton";

import {
  changeApplicationStatus,
  fetchOpportunity,
  fetchOpportunityApplications,
  type Application,
} from "./api";
import { APPLICATION_STATUS_LABEL, REVIEWER_NEXT, type ApplicationStatus } from "./labels";
import { StatusTimeline } from "./StatusTimeline";

/** Applicant review table + detail drawer. Coordinators/admins see it read-only. */
export function ApplicantsPage() {
  const { opportunityId = "" } = useParams<{ opportunityId: string }>();
  const { user } = useAuth();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data: opportunity } = useQuery({
    queryKey: ["opportunity", opportunityId],
    queryFn: () => fetchOpportunity(opportunityId),
  });
  const {
    data: applications,
    isPending,
    isError,
  } = useQuery({
    queryKey: ["opportunity-applications", opportunityId],
    queryFn: () => fetchOpportunityApplications(opportunityId),
  });

  const selected = applications?.find((a) => a.id === selectedId) ?? null;
  const canDecide = !!opportunity && opportunity.created_by === user?.id;

  return (
    <div>
      <Link
        to={`/opportunities/${opportunityId}`}
        className="text-sm text-brand-700 hover:underline"
      >
        ← Back to opportunity
      </Link>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">
        Applicants{opportunity ? ` · ${opportunity.title}` : ""}
      </h1>
      {!canDecide && opportunity ? (
        <p className="mt-1 text-sm text-ink-muted">Read-only: only the poster decides.</p>
      ) : null}

      {isPending ? (
        <div className="mt-6">
          <SkeletonList rows={3} />
        </div>
      ) : null}
      {isError ? (
        <p role="alert" className="mt-6 text-sm text-red-700">
          You can&apos;t view applications for this opportunity.
        </p>
      ) : null}
      {applications && applications.length === 0 ? (
        <p className="mt-6 text-sm text-ink-muted">No applications yet.</p>
      ) : null}

      {applications && applications.length > 0 ? (
        <div className="mt-6 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-ink-muted">
              <tr>
                <th className="py-2 pr-4 font-medium">Applicant</th>
                <th className="py-2 pr-4 font-medium">Status</th>
                <th className="py-2 pr-4 font-medium">Applied</th>
                <th className="py-2 font-medium">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {applications.map((a) => (
                <tr key={a.id}>
                  <td className="py-2 pr-4">
                    {a.applicant_name}
                    <Uid value={a.applicant_registration_number} className="ml-2" />
                  </td>
                  <td className="py-2 pr-4">{APPLICATION_STATUS_LABEL[a.status]}</td>
                  <td className="py-2 pr-4">{new Date(a.created_at).toLocaleDateString()}</td>
                  <td className="py-2">
                    <button
                      type="button"
                      onClick={() => setSelectedId(a.id)}
                      className="text-brand-700 hover:underline"
                    >
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {selected ? (
        <ApplicationDrawer
          key={selected.id}
          application={selected}
          canDecide={canDecide}
          hasProject={!!opportunity?.project_id}
          onClose={() => setSelectedId(null)}
        />
      ) : null}
    </div>
  );
}

function ApplicationDrawer({
  application,
  canDecide,
  hasProject,
  onClose,
}: {
  application: Application;
  canDecide: boolean;
  hasProject: boolean;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [note, setNote] = useState("");
  const [addToProject, setAddToProject] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const decide = useMutation({
    mutationFn: (status: ApplicationStatus) =>
      changeApplicationStatus(
        application.id,
        status,
        note || null,
        status === "accepted" && hasProject && addToProject,
      ),
    onSuccess: async () => {
      setNote("");
      setError(null);
      await queryClient.invalidateQueries({
        queryKey: ["opportunity-applications", application.opportunity_id],
      });
      await queryClient.invalidateQueries({
        queryKey: ["opportunity", application.opportunity_id],
      });
    },
    onError: (caught) => setError(toApiError(caught).message),
  });

  const next = REVIEWER_NEXT[application.status];

  return (
    <aside
      aria-label="Application details"
      className="fixed inset-y-0 right-0 z-20 w-full max-w-md overflow-y-auto border-l border-line bg-surface p-6 shadow-xl"
    >
      <div className="flex items-start justify-between gap-2">
        <h2 className="text-lg font-semibold">
          {application.applicant_name}
          <Uid value={application.applicant_registration_number} className="ml-2" />
        </h2>
        <button type="button" onClick={onClose} className="text-sm text-ink-muted hover:underline">
          Close
        </button>
      </div>
      <p className="text-xs text-ink-muted">{APPLICATION_STATUS_LABEL[application.status]}</p>

      <h3 className="mt-4 text-sm font-semibold">Statement</h3>
      <p className="mt-1 whitespace-pre-line text-sm">{application.statement}</p>

      <h3 className="mt-4 text-sm font-semibold">Timeline</h3>
      <StatusTimeline events={application.events} />

      {error ? (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {error}
        </p>
      ) : null}

      {canDecide && next.length > 0 ? (
        <div className="mt-6 space-y-3">
          <div>
            <label htmlFor="decision-note" className="block text-sm font-medium">
              Note to applicant (optional)
            </label>
            <textarea
              id="decision-note"
              rows={3}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm"
            />
          </div>
          {next.includes("accepted") && hasProject ? (
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={addToProject}
                onChange={(event) => setAddToProject(event.target.checked)}
              />
              Add to the project team when accepted
            </label>
          ) : null}
          <div className="flex flex-wrap gap-2">
            {next.map((status) => (
              <button
                key={status}
                type="button"
                disabled={decide.isPending}
                onClick={() => decide.mutate(status)}
                className={
                  status === "rejected"
                    ? "rounded-md border border-red-300 px-3 py-1.5 text-sm text-red-700"
                    : "rounded-md border border-line bg-surface px-3 py-1.5 text-sm"
                }
              >
                {status === "accepted"
                  ? "Accept"
                  : status === "rejected"
                    ? "Reject"
                    : `Mark ${APPLICATION_STATUS_LABEL[status].toLowerCase()}`}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </aside>
  );
}

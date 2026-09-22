import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useAuth } from "@/features/auth/authContext";
import { ReportButton } from "@/features/reports/ReportButton";
import { toApiError } from "@/lib/api/errors";

import { deletePublication, fetchPublication, PUB_TYPE_LABEL } from "./api";

export function PublicationDetailPage() {
  const { publicationId = "" } = useParams<{ publicationId: string }>();
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const {
    data: publication,
    isPending,
    isError,
  } = useQuery({
    queryKey: ["publication", publicationId],
    queryFn: () => fetchPublication(publicationId),
  });

  const remove = useMutation({
    mutationFn: () => deletePublication(publicationId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["publications"] });
      void navigate("/publications/mine", { replace: true });
    },
    onError: (caught) => {
      setConfirming(false);
      setError(toApiError(caught).message);
    },
  });

  if (isPending) return <p className="text-sm text-ink-muted">Loading…</p>;
  if (isError) {
    return (
      <p role="alert" className="text-sm text-red-700">
        Publication not found.
      </p>
    );
  }

  const isCreator = user?.id === publication.created_by;
  const canDelete = isCreator || user?.role === "admin";

  return (
    <div className="mx-auto max-w-3xl">
      <p className="text-xs text-ink-muted">
        {PUB_TYPE_LABEL[publication.pub_type]} · {publication.year}
      </p>
      <h1 className="mt-1 text-2xl font-semibold tracking-tight">{publication.title}</h1>
      <p className="mt-2 text-sm">
        {publication.authors.map((author, index) => (
          <span key={author.author_order}>
            {index > 0 ? ", " : null}
            {author.user_id ? (
              <Link
                to={`/researchers/${author.user_id}`}
                className="text-brand-700 hover:underline"
              >
                {author.name}
              </Link>
            ) : (
              author.name
            )}
          </span>
        ))}
      </p>
      {publication.venue ? (
        <p className="mt-1 text-sm text-ink-muted">{publication.venue}</p>
      ) : null}

      {error ? (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {error}
        </p>
      ) : null}

      {isCreator || canDelete ? (
        <div className="mt-4 flex gap-2">
          {isCreator ? (
            <Link
              to={`/publications/${publication.id}/edit`}
              className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm"
            >
              Edit
            </Link>
          ) : null}
          <ReportButton targetType="publication" targetId={publication.id} />
          {canDelete ? (
            <button
              type="button"
              onClick={() => setConfirming(true)}
              className="rounded-md border border-red-300 px-3 py-1.5 text-sm text-red-700"
            >
              Delete
            </button>
          ) : null}
        </div>
      ) : null}

      {publication.abstract ? (
        <section className="mt-8">
          <h2 className="text-base font-semibold">Abstract</h2>
          <p className="mt-2 whitespace-pre-line text-sm">{publication.abstract}</p>
        </section>
      ) : null}

      {publication.doi || publication.url ? (
        <section className="mt-8">
          <h2 className="text-base font-semibold">Links</h2>
          <ul className="mt-2 space-y-1 text-sm">
            {publication.doi ? (
              <li>
                DOI:{" "}
                <a
                  href={`https://doi.org/${publication.doi}`}
                  target="_blank"
                  rel="noreferrer"
                  className="text-brand-700 hover:underline"
                >
                  {publication.doi}
                </a>
              </li>
            ) : null}
            {publication.url ? (
              <li>
                <a
                  href={publication.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-brand-700 hover:underline"
                >
                  {publication.url}
                </a>
              </li>
            ) : null}
          </ul>
        </section>
      ) : null}

      {publication.projects.length > 0 ? (
        <section className="mt-8">
          <h2 className="text-base font-semibold">Related projects</h2>
          <ul className="mt-2 space-y-1">
            {publication.projects.map((project) => (
              <li key={project.id}>
                <Link
                  to={`/projects/${project.id}`}
                  className="text-sm text-brand-700 hover:underline"
                >
                  {project.title}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <ConfirmDialog
        open={confirming}
        title="Delete publication?"
        description="This permanently removes the publication and its author list."
        confirmLabel="Delete"
        isConfirming={remove.isPending}
        onConfirm={() => remove.mutate()}
        onCancel={() => setConfirming(false)}
      />
    </div>
  );
}

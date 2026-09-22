import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, useParams } from "react-router-dom";
import { z } from "zod";

import { useAuth } from "@/features/auth/authContext";
import { fetchProjects } from "@/features/projects/api";
import { toApiError } from "@/lib/api/errors";

import {
  createPublication,
  fetchPublication,
  updatePublication,
  type Publication,
  type PublicationInput,
} from "./api";
import { PUB_TYPE_LABEL, type PublicationType } from "./labels";
import { AuthorListEditor } from "./AuthorListEditor";
import { newAuthorRow, toAuthorInputs, type AuthorRow } from "./authors";

const schema = z.object({
  title: z.string().trim().min(1, "Title is required").max(500, "Title is too long"),
  abstract: z.string().max(20000),
  venue: z.string().max(300),
  year: z.coerce
    .number({ message: "Year is required" })
    .int()
    .min(1900, "Year must be between 1900 and 2100")
    .max(2100, "Year must be between 1900 and 2100"),
  pub_type: z.enum(Object.keys(PUB_TYPE_LABEL) as [PublicationType, ...PublicationType[]]),
  doi: z.string().max(255),
  url: z
    .string()
    .max(2000)
    .refine((v) => !v || /^https?:\/\//.test(v), "URL must start with http:// or https://"),
});

type FormInput = z.input<typeof schema>;
type FormValues = z.output<typeof schema>;

const FIELD = "mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm";

/** Create (no :publicationId) or edit an existing publication. */
export function PublicationFormPage() {
  const { publicationId } = useParams<{ publicationId: string }>();
  const { data: existing, isPending } = useQuery({
    queryKey: ["publication", publicationId],
    queryFn: () => fetchPublication(publicationId ?? ""),
    enabled: Boolean(publicationId),
  });

  if (publicationId && isPending) return <p className="text-sm text-ink-muted">Loading…</p>;
  return <PublicationForm key={existing?.id ?? "new"} existing={existing ?? null} />;
}

function PublicationForm({ existing }: { existing: Publication | null }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [authors, setAuthors] = useState<AuthorRow[]>(() =>
    existing
      ? existing.authors.map((a) =>
          a.user_id
            ? newAuthorRow("user", a.user_id, a.name)
            : newAuthorRow("external", null, a.name),
        )
      : user
        ? [newAuthorRow("user", user.id, user.full_name)]
        : [],
  );
  const [projectIds, setProjectIds] = useState<string[]>(
    () => existing?.projects.map((p) => p.id) ?? [],
  );

  const { data: myProjects } = useQuery({
    queryKey: ["projects", { mine: true, page: 1 }],
    queryFn: () => fetchProjects({ mine: true }),
  });

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormInput, unknown, FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      title: existing?.title ?? "",
      abstract: existing?.abstract ?? "",
      venue: existing?.venue ?? "",
      year: existing?.year ?? new Date().getFullYear(),
      pub_type: existing?.pub_type ?? "journal_article",
      doi: existing?.doi ?? "",
      url: existing?.url ?? "",
    },
  });

  const submit = handleSubmit(async (values) => {
    setError(null);
    const authorInputs = toAuthorInputs(authors);
    if (typeof authorInputs === "string") {
      setError(authorInputs);
      return;
    }
    const input: PublicationInput = {
      title: values.title,
      abstract: values.abstract || null,
      venue: values.venue || null,
      year: values.year,
      pub_type: values.pub_type,
      doi: values.doi || null,
      url: values.url || null,
      authors: authorInputs,
      project_ids: projectIds,
    };
    try {
      const saved = existing
        ? await updatePublication(existing.id, input)
        : await createPublication(input);
      await queryClient.invalidateQueries({ queryKey: ["publications"] });
      await queryClient.invalidateQueries({ queryKey: ["publication", saved.id] });
      void navigate(`/publications/${saved.id}`, { replace: true });
    } catch (caught) {
      setError(toApiError(caught).message);
    }
  });

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-2xl font-semibold tracking-tight">
        {existing ? "Edit publication" : "New publication"}
      </h1>

      {error ? (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {error}
        </p>
      ) : null}

      <form onSubmit={(event) => void submit(event)} className="mt-6 space-y-4" noValidate>
        <div>
          <label htmlFor="title" className="block text-sm font-medium">
            Title
          </label>
          <input id="title" className={FIELD} {...register("title")} />
          {errors.title ? (
            <p className="mt-1 text-xs text-red-700">{errors.title.message}</p>
          ) : null}
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <div>
            <label htmlFor="pub_type" className="block text-sm font-medium">
              Type
            </label>
            <select id="pub_type" className={FIELD} {...register("pub_type")}>
              {Object.entries(PUB_TYPE_LABEL).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="year" className="block text-sm font-medium">
              Year
            </label>
            <input id="year" inputMode="numeric" className={FIELD} {...register("year")} />
            {errors.year ? (
              <p className="mt-1 text-xs text-red-700">{errors.year.message}</p>
            ) : null}
          </div>
          <div>
            <label htmlFor="venue" className="block text-sm font-medium">
              Venue
            </label>
            <input id="venue" className={FIELD} {...register("venue")} />
          </div>
        </div>
        <div>
          <label htmlFor="abstract" className="block text-sm font-medium">
            Abstract (optional)
          </label>
          <textarea id="abstract" rows={5} className={FIELD} {...register("abstract")} />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="doi" className="block text-sm font-medium">
              DOI (optional)
            </label>
            <input id="doi" placeholder="10.1000/xyz123" className={FIELD} {...register("doi")} />
          </div>
          <div>
            <label htmlFor="url" className="block text-sm font-medium">
              URL (optional)
            </label>
            <input id="url" className={FIELD} {...register("url")} />
            {errors.url ? <p className="mt-1 text-xs text-red-700">{errors.url.message}</p> : null}
          </div>
        </div>

        <AuthorListEditor rows={authors} onChange={setAuthors} />

        {myProjects && myProjects.items.length > 0 ? (
          <fieldset>
            <legend className="block text-sm font-medium">Related projects</legend>
            <ul className="mt-2 space-y-1">
              {myProjects.items.map((project) => (
                <li key={project.id}>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={projectIds.includes(project.id)}
                      onChange={(event) =>
                        setProjectIds((prev) =>
                          event.target.checked
                            ? [...prev, project.id]
                            : prev.filter((id) => id !== project.id),
                        )
                      }
                    />
                    {project.title}
                  </label>
                </li>
              ))}
            </ul>
          </fieldset>
        ) : null}

        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-md bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-800 disabled:opacity-50"
        >
          {isSubmitting ? "Saving…" : existing ? "Save changes" : "Add publication"}
        </button>
      </form>
    </div>
  );
}

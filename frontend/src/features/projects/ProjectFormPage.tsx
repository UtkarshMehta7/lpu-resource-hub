import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, useParams } from "react-router-dom";
import { z } from "zod";

import { TagPicker, type TagOption } from "@/components/ui/TagPicker";
import { searchResearchAreas, searchSkills } from "@/features/taxonomy/api";
import { toApiError } from "@/lib/api/errors";

import { createProject, fetchProject, updateProject, type Project, type ProjectInput } from "./api";

const schema = z
  .object({
    title: z.string().min(1, "Title is required").max(200, "Title is too long"),
    summary: z.string().min(1, "Summary is required").max(500, "Summary is too long"),
    description: z.string().min(1, "Description is required").max(20000),
    objectives: z.string().max(10000),
    start_date: z.string(),
    end_date: z.string(),
  })
  .refine((v) => !v.start_date || !v.end_date || v.start_date <= v.end_date, {
    message: "End date must be on or after the start date",
    path: ["end_date"],
  });

type FormValues = z.infer<typeof schema>;

const FIELD = "mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm";

/** Create (no :projectId) or edit an existing project. */
export function ProjectFormPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { data: existing, isPending } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => fetchProject(projectId ?? ""),
    enabled: Boolean(projectId),
  });

  if (projectId && isPending) return <p className="text-sm text-ink-muted">Loading…</p>;
  return <ProjectForm key={existing?.id ?? "new"} existing={existing ?? null} />;
}

function ProjectForm({ existing }: { existing: Project | null }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [skills, setSkills] = useState<TagOption[]>([]);
  const [areas, setAreas] = useState<TagOption[]>([]);
  const [error, setError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      title: existing?.title ?? "",
      summary: existing?.summary ?? "",
      description: existing?.description ?? "",
      objectives: existing?.objectives ?? "",
      start_date: existing?.start_date ?? "",
      end_date: existing?.end_date ?? "",
    },
  });

  const findSkills = useCallback(
    async (q: string) => (await searchSkills(q || undefined)).map(({ id, name }) => ({ id, name })),
    [],
  );
  const findAreas = useCallback(
    async (q: string) =>
      (await searchResearchAreas(q || undefined)).map(({ id, name }) => ({ id, name })),
    [],
  );

  const submit = handleSubmit(async (values) => {
    setError(null);
    const input: ProjectInput = {
      title: values.title,
      summary: values.summary,
      description: values.description,
      objectives: values.objectives || null,
      start_date: values.start_date || null,
      end_date: values.end_date || null,
    };
    // When editing, tags are only replaced if the user picked new ones.
    if (!existing || skills.length > 0) input.skill_ids = skills.map((s) => s.id);
    if (!existing || areas.length > 0) input.research_area_ids = areas.map((a) => a.id);

    try {
      const saved = existing ? await updateProject(existing.id, input) : await createProject(input);
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
      await queryClient.invalidateQueries({ queryKey: ["project", saved.id] });
      void navigate(`/projects/${saved.id}`, { replace: true });
    } catch (caught) {
      setError(toApiError(caught).message);
    }
  });

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-2xl font-semibold tracking-tight">
        {existing ? "Edit project" : "New project"}
      </h1>
      <p className="mt-1 text-sm text-ink-muted">
        New projects start as drafts. Submit it for review when it&apos;s ready.
      </p>

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
        <div>
          <label htmlFor="summary" className="block text-sm font-medium">
            Summary
          </label>
          <input id="summary" className={FIELD} {...register("summary")} />
          {errors.summary ? (
            <p className="mt-1 text-xs text-red-700">{errors.summary.message}</p>
          ) : null}
        </div>
        <div>
          <label htmlFor="description" className="block text-sm font-medium">
            Description
          </label>
          <textarea id="description" rows={5} className={FIELD} {...register("description")} />
          {errors.description ? (
            <p className="mt-1 text-xs text-red-700">{errors.description.message}</p>
          ) : null}
        </div>
        <div>
          <label htmlFor="objectives" className="block text-sm font-medium">
            Objectives (optional)
          </label>
          <textarea id="objectives" rows={3} className={FIELD} {...register("objectives")} />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="start_date" className="block text-sm font-medium">
              Start date
            </label>
            <input id="start_date" type="date" className={FIELD} {...register("start_date")} />
          </div>
          <div>
            <label htmlFor="end_date" className="block text-sm font-medium">
              End date
            </label>
            <input id="end_date" type="date" className={FIELD} {...register("end_date")} />
            {errors.end_date ? (
              <p className="mt-1 text-xs text-red-700">{errors.end_date.message}</p>
            ) : null}
          </div>
        </div>

        {existing && [...existing.research_areas, ...existing.skills].length > 0 ? (
          <p className="text-xs text-ink-muted">
            Current tags: {[...existing.research_areas, ...existing.skills].join(", ")}. Pick below
            only to replace them.
          </p>
        ) : null}
        <TagPicker
          label="Research areas"
          search={findAreas}
          selected={areas}
          onAdd={(option) => setAreas((prev) => [...prev, option])}
          onRemove={(id) => setAreas((prev) => prev.filter((a) => a.id !== id))}
        />
        <TagPicker
          label="Skills needed"
          search={findSkills}
          selected={skills}
          onAdd={(option) => setSkills((prev) => [...prev, option])}
          onRemove={(id) => setSkills((prev) => prev.filter((s) => s.id !== id))}
        />

        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-md bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-800 disabled:opacity-50"
        >
          {isSubmitting ? "Saving…" : existing ? "Save changes" : "Create draft"}
        </button>
      </form>
    </div>
  );
}

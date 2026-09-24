import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, useParams } from "react-router-dom";
import { z } from "zod";

import { TagPicker, type TagOption } from "@/components/ui/TagPicker";
import { SkeletonList } from "@/components/ui/Skeleton";
import { useAuth } from "@/features/auth/authContext";
import { fetchProjects } from "@/features/projects/api";
import { searchSkills } from "@/features/taxonomy/api";
import { toApiError } from "@/lib/api/errors";

import {
  createOpportunity,
  fetchOpportunity,
  updateOpportunity,
  type Opportunity,
  type OpportunityInput,
} from "./api";
import { TYPE_LABEL, type OpportunityType } from "./labels";

const today = () => new Date().toISOString().slice(0, 10);

const schema = z.object({
  title: z.string().trim().min(1, "Title is required").max(200, "Title is too long"),
  description: z.string().trim().min(1, "Description is required").max(20000),
  opportunity_type: z.enum(Object.keys(TYPE_LABEL) as [OpportunityType, ...OpportunityType[]]),
  project_id: z.string(),
  eligibility: z.string().max(5000),
  positions: z.coerce
    .number({ message: "Positions is required" })
    .int()
    .min(1, "At least 1 position")
    .max(100, "At most 100 positions"),
  deadline: z
    .string()
    .min(1, "Deadline is required")
    .refine((v) => v >= today(), "The deadline can't be in the past"),
});

type FormInput = z.input<typeof schema>;
type FormValues = z.output<typeof schema>;

const FIELD = "mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm";

/** Create (no :opportunityId) or edit an opportunity. New ones start as drafts. */
export function OpportunityFormPage() {
  const { opportunityId } = useParams<{ opportunityId: string }>();
  const { data: existing, isPending } = useQuery({
    queryKey: ["opportunity", opportunityId],
    queryFn: () => fetchOpportunity(opportunityId ?? ""),
    enabled: Boolean(opportunityId),
  });

  if (opportunityId && isPending) return <SkeletonList rows={3} />;
  return <OpportunityForm key={existing?.id ?? "new"} existing={existing ?? null} />;
}

function OpportunityForm({ existing }: { existing: Opportunity | null }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [skills, setSkills] = useState<TagOption[]>(
    () => existing?.skills.map(({ id, name }) => ({ id, name })) ?? [],
  );
  const isCoordinator = user?.role === "research_coordinator";

  const { data: projects } = useQuery({
    queryKey: ["projects", { mine: true, status: "active" }],
    queryFn: () => fetchProjects({ mine: true, status: "active" }),
    enabled: !existing,
  });

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormInput, unknown, FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      title: existing?.title ?? "",
      description: existing?.description ?? "",
      opportunity_type: existing?.opportunity_type ?? "research_assistant",
      project_id: existing?.project_id ?? "",
      eligibility: existing?.eligibility ?? "",
      positions: existing?.positions ?? 1,
      deadline: existing?.deadline ?? "",
    },
  });

  const findSkills = useCallback(
    async (q: string) => (await searchSkills(q || undefined)).map(({ id, name }) => ({ id, name })),
    [],
  );

  const submit = handleSubmit(async (values) => {
    setError(null);
    if (!existing && !values.project_id && !isCoordinator) {
      setError("Choose one of your active projects.");
      return;
    }
    const input: OpportunityInput = {
      title: values.title,
      description: values.description,
      opportunity_type: values.opportunity_type,
      eligibility: values.eligibility || null,
      positions: values.positions,
      deadline: values.deadline,
      skills: skills.map((s) => ({ skill_id: s.id, is_required: true })),
    };
    try {
      const saved = existing
        ? await updateOpportunity(existing.id, input)
        : await createOpportunity({ ...input, project_id: values.project_id || null });
      await queryClient.invalidateQueries({ queryKey: ["opportunities"] });
      await queryClient.invalidateQueries({ queryKey: ["opportunity", saved.id] });
      void navigate(`/opportunities/${saved.id}`, { replace: true });
    } catch (caught) {
      setError(toApiError(caught).message);
    }
  });

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-2xl font-semibold tracking-tight">
        {existing ? "Edit opportunity" : "New opportunity"}
      </h1>
      <p className="mt-1 text-sm text-ink-muted">
        New opportunities start as drafts. Publish when you&apos;re ready to take applications.
      </p>

      {error ? (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {error}
        </p>
      ) : null}

      <form onSubmit={(event) => void submit(event)} className="mt-6 space-y-4" noValidate>
        {!existing ? (
          <div>
            <label htmlFor="project_id" className="block text-sm font-medium">
              Project
            </label>
            <select id="project_id" className={FIELD} {...register("project_id")}>
              <option value="">
                {isCoordinator ? "Department-wide (no project)" : "Choose an active project"}
              </option>
              {projects?.items.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title}
                </option>
              ))}
            </select>
          </div>
        ) : null}
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
            <label htmlFor="opportunity_type" className="block text-sm font-medium">
              Type
            </label>
            <select id="opportunity_type" className={FIELD} {...register("opportunity_type")}>
              {Object.entries(TYPE_LABEL).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="positions" className="block text-sm font-medium">
              Positions
            </label>
            <input
              id="positions"
              inputMode="numeric"
              className={FIELD}
              {...register("positions")}
            />
            {errors.positions ? (
              <p className="mt-1 text-xs text-red-700">{errors.positions.message}</p>
            ) : null}
          </div>
          <div>
            <label htmlFor="deadline" className="block text-sm font-medium">
              Deadline
            </label>
            <input id="deadline" type="date" className={FIELD} {...register("deadline")} />
            {errors.deadline ? (
              <p className="mt-1 text-xs text-red-700">{errors.deadline.message}</p>
            ) : null}
          </div>
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
          <label htmlFor="eligibility" className="block text-sm font-medium">
            Eligibility (optional)
          </label>
          <textarea id="eligibility" rows={3} className={FIELD} {...register("eligibility")} />
        </div>
        <TagPicker
          label="Skills"
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

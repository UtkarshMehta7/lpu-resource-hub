import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, useParams } from "react-router-dom";
import { z } from "zod";

import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/PageHeader";
import { SkeletonList } from "@/components/ui/Skeleton";
import { AuthorListEditor } from "@/features/publications/AuthorListEditor";
import { newAuthorRow, toAuthorInputs, type AuthorRow } from "@/features/publications/authors";
import { toApiError } from "@/lib/api/errors";

import { createPatent, fetchPatent, updatePatent } from "./api";
import { OFFICE_OPTIONS } from "./labels";
import { PriorArtPanel } from "./PriorArtPanel";

const schema = z.object({
  title: z.string().trim().min(1, "Title is required").max(500, "Title is too long"),
  abstract: z.string().max(20000),
  jurisdiction: z
    .string()
    .trim()
    .regex(/^[A-Za-z]{2}$/, "Use the office's two-letter code, e.g. IN"),
  application_number: z.string().max(64),
  filing_date: z.string().min(1, "A filing date is required"),
  assignee: z.string().max(300),
  url: z
    .string()
    .max(2000)
    .refine((v) => !v || /^https?:\/\//.test(v), "URL must start with http:// or https://"),
});

type FormValues = z.output<typeof schema>;

const FIELD = "mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm";

/**
 * Record a patent, or edit one.
 *
 * The prior-art check sits in the form rather than behind a separate page:
 * the moment to find out somebody has already done this is while you are
 * describing it, not after you have filed.
 *
 * Status is absent on purpose. A record always starts at `filed` and moves
 * through its own endpoint, so the transition table is the only thing that
 * can change it -- a dropdown here would let a record claim a grant that
 * never happened.
 */
export function PatentFormPage() {
  const { patentId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [inventors, setInventors] = useState<AuthorRow[]>([newAuthorRow("user")]);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const existing = useQuery({
    queryKey: ["patent", patentId],
    queryFn: () => fetchPatent(patentId as string),
    enabled: Boolean(patentId),
  });

  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      title: "",
      abstract: "",
      jurisdiction: "IN",
      application_number: "",
      filing_date: "",
      assignee: "Lovely Professional University",
      url: "",
    },
  });

  if (patentId && existing.data && !loaded) {
    const patent = existing.data;
    reset({
      title: patent.title,
      abstract: patent.abstract ?? "",
      jurisdiction: patent.jurisdiction,
      application_number: patent.application_number ?? "",
      filing_date: patent.filing_date,
      assignee: patent.assignee ?? "",
      url: patent.url ?? "",
    });
    setInventors(
      patent.inventors.map((inventor) =>
        inventor.user_id
          ? newAuthorRow("user", inventor.user_id)
          : newAuthorRow("external", null, inventor.name),
      ),
    );
    setLoaded(true);
  }

  if (patentId && existing.isPending) return <SkeletonList rows={4} />;

  const onSubmit = handleSubmit(async (values) => {
    setError(null);
    const inventorInputs = toAuthorInputs(inventors);
    if (typeof inventorInputs === "string") {
      setError(inventorInputs.replace(/author/gi, (m) => (m[0] === "A" ? "Inventor" : "inventor")));
      return;
    }
    const payload = {
      title: values.title,
      abstract: values.abstract || null,
      jurisdiction: values.jurisdiction.toUpperCase(),
      application_number: values.application_number || null,
      filing_date: values.filing_date,
      assignee: values.assignee || null,
      url: values.url || null,
      inventors: inventorInputs,
    };
    try {
      const saved = patentId ? await updatePatent(patentId, payload) : await createPatent(payload);
      await queryClient.invalidateQueries({ queryKey: ["patents"] });
      void navigate(`/patents/${saved.id}`);
    } catch (caught) {
      setError(toApiError(caught).message);
    }
  });

  return (
    <div className="space-y-8">
      <PageHeader
        title={patentId ? "Edit patent" : "Record a patent"}
        description={
          patentId
            ? "Changing the substance sends the record back to your coordinator, because their tick was about the content you are editing."
            : "Anyone can record one. A coordinator checks the numbers, dates and inventors before it counts."
        }
      />

      <form onSubmit={(event) => void onSubmit(event)} className="space-y-5" noValidate>
        <div>
          <label htmlFor="title" className="block text-sm font-medium">
            Title
          </label>
          <input id="title" className={FIELD} {...register("title")} />
          {errors.title ? (
            <p className="mt-1 text-sm text-red-700">{errors.title.message}</p>
          ) : null}
        </div>

        <div>
          <label htmlFor="abstract" className="block text-sm font-medium">
            Abstract
          </label>
          <textarea id="abstract" rows={5} className={FIELD} {...register("abstract")} />
          <p className="mt-1 text-xs text-ink-muted">
            Used for the prior-art check below as well as for search.
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="jurisdiction" className="block text-sm font-medium">
              Patent office
            </label>
            <input
              id="jurisdiction"
              list="patent-offices"
              maxLength={2}
              className={`${FIELD} uppercase`}
              {...register("jurisdiction")}
            />
            <datalist id="patent-offices">
              {OFFICE_OPTIONS.map((office) => (
                <option key={office.code} value={office.code}>
                  {office.name}
                </option>
              ))}
            </datalist>
            <p className="mt-1 text-xs text-ink-muted">
              Two-letter code: IN for India, EP for the European office, WO for a PCT filing.
            </p>
            {errors.jurisdiction ? (
              <p className="mt-1 text-sm text-red-700">{errors.jurisdiction.message}</p>
            ) : null}
          </div>
          <div>
            <label htmlFor="filing_date" className="block text-sm font-medium">
              Filing date
            </label>
            <input id="filing_date" type="date" className={FIELD} {...register("filing_date")} />
            <p className="mt-1 text-xs text-ink-muted">This is what establishes priority.</p>
            {errors.filing_date ? (
              <p className="mt-1 text-sm text-red-700">{errors.filing_date.message}</p>
            ) : null}
          </div>
          <div>
            <label htmlFor="application_number" className="block text-sm font-medium">
              Application number
            </label>
            <input id="application_number" className={FIELD} {...register("application_number")} />
            <p className="mt-1 text-xs text-ink-muted">
              Optional now, unique within the office once you have it.
            </p>
          </div>
          <div>
            <label htmlFor="assignee" className="block text-sm font-medium">
              Assignee
            </label>
            <input id="assignee" className={FIELD} {...register("assignee")} />
            <p className="mt-1 text-xs text-ink-muted">Who holds the right, not who invented it.</p>
          </div>
        </div>

        <div>
          <label htmlFor="url" className="block text-sm font-medium">
            Link
          </label>
          <input id="url" className={FIELD} {...register("url")} />
          {errors.url ? <p className="mt-1 text-sm text-red-700">{errors.url.message}</p> : null}
        </div>

        <AuthorListEditor rows={inventors} onChange={setInventors} noun="Inventor" />

        {error ? <p className="text-sm text-red-700">{error}</p> : null}

        <div className="flex gap-2">
          <Button type="submit" disabled={isSubmitting}>
            {patentId ? "Save changes" : "Record patent"}
          </Button>
          <Button variant="secondary" onClick={() => void navigate(-1)}>
            Cancel
          </Button>
        </div>
      </form>

      <PriorArtPanel title={watch("title")} abstract={watch("abstract")} excludeId={patentId} />
    </div>
  );
}

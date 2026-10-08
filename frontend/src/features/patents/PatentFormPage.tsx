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
import { DISCLOSURE_WARNING, OFFICE_OPTIONS } from "./labels";
import { PriorArtPanel } from "./PriorArtPanel";

const schema = z
  .object({
    title: z.string().trim().min(1, "Title is required").max(500, "Title is too long"),
    abstract: z.string().max(20000),
    jurisdiction: z
      .string()
      .trim()
      .regex(/^[A-Za-z]{2}$/, "Use the office's two-letter code, e.g. IN"),
    application_number: z.string().max(64),
    already_filed: z.boolean(),
    filing_date: z.string(),
    assignee: z.string().max(300),
    url: z
      .string()
      .max(2000)
      .refine((v) => !v || /^https?:\/\//.test(v), "URL must start with http:// or https://"),
    problem_statement: z.string().max(20000),
    novelty: z.string().max(20000),
    known_prior_art: z.string().max(20000),
    public_disclosure_date: z.string(),
    public_disclosure_note: z.string().max(2000),
    funding_source: z.string().max(300),
    commercial_potential: z.string().max(20000),
  })
  // The backend refuses a filing date on something not yet filed, and refuses
  // a filed record without one. Saying so here means the person is told while
  // they are still typing rather than on submit.
  .refine((v) => !v.already_filed || v.filing_date !== "", {
    path: ["filing_date"],
    message: "A patent already filed needs its filing date",
  });

type FormValues = z.output<typeof schema>;

const FIELD = "mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm";
const HINT = "mt-1 text-xs text-ink-muted";

/**
 * Record a patent, or put an invention to the university.
 *
 * Two ways in, one record. An invention nobody has filed yet starts as a
 * DISCLOSURE: the university's IP cell assesses it and decides whether to
 * file, and the fields it asks for are the ones an assessor actually reads.
 * A patent already filed somewhere is recorded as filed and needs its date.
 *
 * Status is absent on purpose. Every move after the entry point goes through
 * the transition table, so a record cannot claim a stage that never happened.
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
      already_filed: false,
      filing_date: "",
      assignee: "Lovely Professional University",
      url: "",
      problem_statement: "",
      novelty: "",
      known_prior_art: "",
      public_disclosure_date: "",
      public_disclosure_note: "",
      funding_source: "",
      commercial_potential: "",
    },
  });

  if (patentId && existing.data && !loaded) {
    const patent = existing.data;
    reset({
      title: patent.title,
      abstract: patent.abstract ?? "",
      jurisdiction: patent.jurisdiction,
      application_number: patent.application_number ?? "",
      already_filed: patent.filing_date !== null,
      filing_date: patent.filing_date ?? "",
      assignee: patent.assignee ?? "",
      url: patent.url ?? "",
      problem_statement: patent.problem_statement ?? "",
      novelty: patent.novelty ?? "",
      known_prior_art: patent.known_prior_art ?? "",
      public_disclosure_date: patent.public_disclosure_date ?? "",
      public_disclosure_note: patent.public_disclosure_note ?? "",
      funding_source: patent.funding_source ?? "",
      commercial_potential: patent.commercial_potential ?? "",
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

  const alreadyFiled = watch("already_filed");
  const disclosedPublicly = watch("public_disclosure_date") !== "";

  const onSubmit = handleSubmit(async (values) => {
    setError(null);
    const inventorInputs = toAuthorInputs(inventors);
    if (typeof inventorInputs === "string") {
      setError(inventorInputs.replace(/author/gi, (m) => (m[0] === "A" ? "Inventor" : "inventor")));
      return;
    }
    const blank = (v: string) => v || null;
    const payload = {
      title: values.title,
      abstract: blank(values.abstract),
      jurisdiction: values.jurisdiction.toUpperCase(),
      application_number: blank(values.application_number),
      assignee: blank(values.assignee),
      url: blank(values.url),
      problem_statement: blank(values.problem_statement),
      novelty: blank(values.novelty),
      known_prior_art: blank(values.known_prior_art),
      public_disclosure_date: blank(values.public_disclosure_date),
      public_disclosure_note: blank(values.public_disclosure_note),
      funding_source: blank(values.funding_source),
      commercial_potential: blank(values.commercial_potential),
      inventors: inventorInputs,
    };
    try {
      const saved = patentId
        ? await updatePatent(patentId, payload)
        : await createPatent({
            ...payload,
            already_filed: values.already_filed,
            // Nothing inside the university has a filing date: the office
            // sets it, through the transition that records the filing.
            filing_date: values.already_filed ? values.filing_date : null,
          });
      await queryClient.invalidateQueries({ queryKey: ["patents"] });
      void navigate(`/patents/${saved.id}`);
    } catch (caught) {
      setError(toApiError(caught).message);
    }
  });

  return (
    <div className="space-y-8">
      <PageHeader
        title={patentId ? "Edit this record" : "File or record a patent"}
        description={
          patentId
            ? "Changing the substance sends the record back to your coordinator, because their tick was about the content you are editing."
            : "Put an invention to the university, or record one that has already been filed. Either way a coordinator checks it before it counts."
        }
      />

      <form onSubmit={(event) => void onSubmit(event)} className="space-y-6" noValidate>
        {!patentId ? (
          <fieldset className="rounded-card border border-line bg-surface p-5">
            <legend className="px-1 text-sm font-semibold">Which is this?</legend>
            <div className="mt-2 space-y-3">
              <label className="flex gap-3">
                <input
                  type="radio"
                  value="false"
                  className="mt-1"
                  {...register("already_filed", { setValueAs: (v) => v === true || v === "true" })}
                  defaultChecked
                />
                <span>
                  <span className="block text-sm font-medium">
                    I want the university to file this
                  </span>
                  <span className={HINT}>
                    An invention disclosure. The IP cell assesses it, and you get a reference to
                    quote while they do.
                  </span>
                </span>
              </label>
              <label className="flex gap-3">
                <input
                  type="radio"
                  value="true"
                  className="mt-1"
                  {...register("already_filed", { setValueAs: (v) => v === true || v === "true" })}
                />
                <span>
                  <span className="block text-sm font-medium">It has already been filed</span>
                  <span className={HINT}>
                    Recording a patent lodged with an office, so it appears in the register.
                  </span>
                </span>
              </label>
            </div>
          </fieldset>
        ) : null}

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
          <textarea id="abstract" rows={4} className={FIELD} {...register("abstract")} />
          <p className={HINT}>Used for the prior-art check below as well as for search.</p>
        </div>

        <fieldset className="rounded-card border border-line bg-surface p-5">
          <legend className="px-1 text-sm font-semibold">What the assessor needs</legend>
          <p className={HINT}>
            Three questions rather than one box: an assessor reads for the problem, the inventive
            step and the art you already know of. Declaring prior art you know about is a duty in
            most jurisdictions, and concealing it can invalidate a granted patent.
          </p>

          <div className="mt-4 space-y-4">
            <div>
              <label htmlFor="problem_statement" className="block text-sm font-medium">
                What problem does it solve?
              </label>
              <textarea
                id="problem_statement"
                rows={3}
                className={FIELD}
                {...register("problem_statement")}
              />
            </div>
            <div>
              <label htmlFor="novelty" className="block text-sm font-medium">
                What is new about how it solves it?
              </label>
              <textarea id="novelty" rows={3} className={FIELD} {...register("novelty")} />
            </div>
            <div>
              <label htmlFor="known_prior_art" className="block text-sm font-medium">
                Prior art you already know of
              </label>
              <textarea
                id="known_prior_art"
                rows={3}
                className={FIELD}
                {...register("known_prior_art")}
              />
            </div>
          </div>
        </fieldset>

        <fieldset className="rounded-card border border-line bg-surface p-5">
          <legend className="px-1 text-sm font-semibold">Has it been made public?</legend>
          <p className={HINT}>
            A paper, poster, thesis, demonstration or public talk counts. This is the single thing
            most likely to decide whether a patent is possible at all, so say so even if you are
            unsure.
          </p>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="public_disclosure_date" className="block text-sm font-medium">
                Date it became public
              </label>
              <input
                id="public_disclosure_date"
                type="date"
                className={FIELD}
                {...register("public_disclosure_date")}
              />
              <p className={HINT}>Leave blank if it has never been public.</p>
            </div>
            <div>
              <label htmlFor="public_disclosure_note" className="block text-sm font-medium">
                Where
              </label>
              <input
                id="public_disclosure_note"
                className={FIELD}
                placeholder="Conference poster, journal paper, demo day…"
                {...register("public_disclosure_note")}
              />
            </div>
          </div>
          {disclosedPublicly ? (
            <p
              role="alert"
              className="mt-4 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900"
            >
              {DISCLOSURE_WARNING}
            </p>
          ) : null}
        </fieldset>

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
            <p className={HINT}>IN for India, EP for the European office, WO for a PCT filing.</p>
            {errors.jurisdiction ? (
              <p className="mt-1 text-sm text-red-700">{errors.jurisdiction.message}</p>
            ) : null}
          </div>

          {alreadyFiled && !patentId ? (
            <>
              <div>
                <label htmlFor="filing_date" className="block text-sm font-medium">
                  Filing date
                </label>
                <input
                  id="filing_date"
                  type="date"
                  className={FIELD}
                  {...register("filing_date")}
                />
                <p className={HINT}>This is what establishes priority.</p>
                {errors.filing_date ? (
                  <p className="mt-1 text-sm text-red-700">{errors.filing_date.message}</p>
                ) : null}
              </div>
              <div>
                <label htmlFor="application_number" className="block text-sm font-medium">
                  Application number
                </label>
                <input
                  id="application_number"
                  className={FIELD}
                  {...register("application_number")}
                />
                <p className={HINT}>Unique within the office that issued it.</p>
              </div>
            </>
          ) : null}

          <div>
            <label htmlFor="funding_source" className="block text-sm font-medium">
              Funding source
            </label>
            <input
              id="funding_source"
              className={FIELD}
              placeholder="Grant or sponsor, if any"
              {...register("funding_source")}
            />
            <p className={HINT}>
              Public funding usually carries ownership and reporting obligations.
            </p>
          </div>
          <div>
            <label htmlFor="assignee" className="block text-sm font-medium">
              Assignee
            </label>
            <input id="assignee" className={FIELD} {...register("assignee")} />
            <p className={HINT}>Who holds the right, not who invented it.</p>
          </div>
        </div>

        <div>
          <label htmlFor="commercial_potential" className="block text-sm font-medium">
            Who would use it?
          </label>
          <textarea
            id="commercial_potential"
            rows={2}
            className={FIELD}
            {...register("commercial_potential")}
          />
          <p className={HINT}>
            Industries, products or partners you can picture. A sentence is enough.
          </p>
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
            {patentId ? "Save changes" : alreadyFiled ? "Record patent" : "Submit disclosure"}
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

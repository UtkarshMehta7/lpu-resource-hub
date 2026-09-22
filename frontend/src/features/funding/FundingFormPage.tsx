import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { z } from "zod";

import { toApiError } from "@/lib/api/errors";

import { createFunding } from "./api";

const schema = z.object({
  organization: z.string().trim().min(1, "Organisation is required").max(200),
  title: z.string().trim().min(1, "Title is required").max(300),
  description: z.string().trim().min(1, "Description is required").max(20000),
  eligibility: z.string().max(10000),
  amount_text: z.string().max(200),
  deadline: z.string().min(1, "Deadline is required"),
  official_source_url: z
    .string()
    .max(2000)
    .refine((v) => !v || /^https?:\/\//.test(v), "URL must start with http:// or https://"),
});

type FormValues = z.infer<typeof schema>;

const FIELD = "mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm";

/** Coordinators and admins list a funding call. */
export function FundingFormPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      organization: "",
      title: "",
      description: "",
      eligibility: "",
      amount_text: "",
      deadline: "",
      official_source_url: "",
    },
  });

  const submit = handleSubmit(async (values) => {
    setError(null);
    try {
      const saved = await createFunding({
        organization: values.organization,
        title: values.title,
        description: values.description,
        eligibility: values.eligibility || null,
        amount_text: values.amount_text || null,
        deadline: values.deadline,
        official_source_url: values.official_source_url || null,
      });
      await queryClient.invalidateQueries({ queryKey: ["funding"] });
      void navigate(`/funding/${saved.id}`, { replace: true });
    } catch (caught) {
      setError(toApiError(caught).message);
    }
  });

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-2xl font-semibold tracking-tight">Add a funding call</h1>
      <p className="mt-1 text-sm text-ink-muted">
        Link the official source so people can check the details themselves.
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
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="organization" className="block text-sm font-medium">
              Organisation
            </label>
            <input id="organization" className={FIELD} {...register("organization")} />
            {errors.organization ? (
              <p className="mt-1 text-xs text-red-700">{errors.organization.message}</p>
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
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="amount_text" className="block text-sm font-medium">
              Amount (optional)
            </label>
            <input id="amount_text" className={FIELD} {...register("amount_text")} />
          </div>
          <div>
            <label htmlFor="official_source_url" className="block text-sm font-medium">
              Official source URL (optional)
            </label>
            <input
              id="official_source_url"
              className={FIELD}
              {...register("official_source_url")}
            />
            {errors.official_source_url ? (
              <p className="mt-1 text-xs text-red-700">{errors.official_source_url.message}</p>
            ) : null}
          </div>
        </div>
        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-md bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-800 disabled:opacity-50"
        >
          {isSubmitting ? "Saving…" : "Add call"}
        </button>
      </form>
    </div>
  );
}

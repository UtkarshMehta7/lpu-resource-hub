import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { toApiError } from "@/lib/api/errors";

import { applyToOpportunity } from "./api";

const schema = z.object({
  statement: z
    .string()
    .trim()
    .min(20, "Tell the team a little more (at least 20 characters)")
    .max(5000, "Keep it under 5000 characters"),
});

type FormValues = z.infer<typeof schema>;

export function ApplyForm({ opportunityId }: { opportunityId: string }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { statement: "" } });

  const submit = handleSubmit(async ({ statement }) => {
    setError(null);
    try {
      await applyToOpportunity(opportunityId, statement);
      await queryClient.invalidateQueries({ queryKey: ["opportunity", opportunityId] });
      await queryClient.invalidateQueries({ queryKey: ["my-applications"] });
    } catch (caught) {
      setError(toApiError(caught).message);
    }
  });

  return (
    <form onSubmit={(event) => void submit(event)} className="mt-4 space-y-3" noValidate>
      {error ? (
        <p role="alert" className="text-sm text-red-700">
          {error}
        </p>
      ) : null}
      <div>
        <label htmlFor="statement" className="block text-sm font-medium">
          Why are you a good fit?
        </label>
        <textarea
          id="statement"
          rows={5}
          className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm"
          {...register("statement")}
        />
        {errors.statement ? (
          <p className="mt-1 text-xs text-red-700">{errors.statement.message}</p>
        ) : null}
      </div>
      <button
        type="submit"
        disabled={isSubmitting}
        className="rounded-md bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-800 disabled:opacity-50"
      >
        {isSubmitting ? "Submitting…" : "Submit application"}
      </button>
    </form>
  );
}

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, useParams } from "react-router-dom";
import { z } from "zod";

import { toApiError } from "@/lib/api/errors";

import { createEquipment } from "./api";

const schema = z.object({
  name: z.string().trim().min(1, "Name is required").max(200),
  category: z.string().max(150),
  description: z.string().max(5000),
  students_allowed: z.boolean(),
  requires_approval: z.boolean(),
  max_hours: z.coerce.number().int().min(1, "At least 1 hour").max(336),
  min_lead_hours: z.coerce.number().int().min(0).max(720),
});

type FormInput = z.input<typeof schema>;
type FormValues = z.output<typeof schema>;

const FIELD = "mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm";

/** Coordinators and admins add bookable equipment to a facility. */
export function EquipmentFormPage() {
  const { facilityId = "" } = useParams<{ facilityId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormInput, unknown, FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: "",
      category: "",
      description: "",
      students_allowed: true,
      requires_approval: true,
      max_hours: 8,
      min_lead_hours: 0,
    },
  });

  const submit = handleSubmit(async (values) => {
    setError(null);
    try {
      const saved = await createEquipment({
        facility_id: facilityId,
        name: values.name,
        category: values.category || null,
        description: values.description || null,
        students_allowed: values.students_allowed,
        requires_approval: values.requires_approval,
        max_hours: values.max_hours,
        min_lead_hours: values.min_lead_hours,
      });
      await queryClient.invalidateQueries({ queryKey: ["equipment"] });
      await queryClient.invalidateQueries({ queryKey: ["facility", facilityId] });
      void navigate(`/equipment/${saved.id}`, { replace: true });
    } catch (caught) {
      setError(toApiError(caught).message);
    }
  });

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-2xl font-semibold tracking-tight">Add equipment</h1>
      <p className="mt-1 text-sm text-ink-muted">
        The booking rules below are enforced by the API for every request.
      </p>

      {error ? (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {error}
        </p>
      ) : null}

      <form onSubmit={(event) => void submit(event)} className="mt-6 space-y-4" noValidate>
        <div>
          <label htmlFor="name" className="block text-sm font-medium">
            Name
          </label>
          <input id="name" className={FIELD} {...register("name")} />
          {errors.name ? <p className="mt-1 text-xs text-red-700">{errors.name.message}</p> : null}
        </div>
        <div>
          <label htmlFor="category" className="block text-sm font-medium">
            Category (optional)
          </label>
          <input id="category" className={FIELD} {...register("category")} />
        </div>
        <div>
          <label htmlFor="description" className="block text-sm font-medium">
            Description (optional)
          </label>
          <textarea id="description" rows={3} className={FIELD} {...register("description")} />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="max_hours" className="block text-sm font-medium">
              Longest booking (hours)
            </label>
            <input
              id="max_hours"
              inputMode="numeric"
              className={FIELD}
              {...register("max_hours")}
            />
            {errors.max_hours ? (
              <p className="mt-1 text-xs text-red-700">{errors.max_hours.message}</p>
            ) : null}
          </div>
          <div>
            <label htmlFor="min_lead_hours" className="block text-sm font-medium">
              Minimum notice (hours)
            </label>
            <input
              id="min_lead_hours"
              inputMode="numeric"
              className={FIELD}
              {...register("min_lead_hours")}
            />
          </div>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" {...register("students_allowed")} />
          Students may book this
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" {...register("requires_approval")} />
          Bookings need approval
        </label>
        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-md bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-800 disabled:opacity-50"
        >
          {isSubmitting ? "Saving…" : "Add equipment"}
        </button>
      </form>
    </div>
  );
}

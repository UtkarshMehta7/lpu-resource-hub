import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { z } from "zod";

import { useAuth } from "@/features/auth/authContext";
import { apiClient } from "@/lib/api/client";
import { toApiError } from "@/lib/api/errors";

import type { Facility } from "./api";

const schema = z.object({
  name: z.string().trim().min(1, "Name is required").max(200),
  description: z.string().max(5000),
  location: z.string().max(300),
  contact: z.string().max(300),
});

type FormValues = z.infer<typeof schema>;

const FIELD = "mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm";

/** Coordinators create facilities in their own department; admins anywhere. */
export function FacilityFormPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", description: "", location: "", contact: "" },
  });

  const submit = handleSubmit(async (values) => {
    setError(null);
    try {
      const response = await apiClient.post<Facility>("/api/v1/facilities", {
        name: values.name,
        description: values.description || null,
        location: values.location || null,
        contact: values.contact || null,
        // Admins may pass a department explicitly; a coordinator's own scope
        // is applied by the API either way.
        department_id: user?.role === "admin" ? (user.department_id ?? null) : null,
      });
      await queryClient.invalidateQueries({ queryKey: ["facilities"] });
      void navigate(`/facilities/${response.data.id}`, { replace: true });
    } catch (caught) {
      setError(toApiError(caught).message);
    }
  });

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-2xl font-semibold tracking-tight">New facility</h1>
      <p className="mt-1 text-sm text-ink-muted">
        A lab or workshop in your Lovely Professional University department.
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
          <label htmlFor="description" className="block text-sm font-medium">
            Description (optional)
          </label>
          <textarea id="description" rows={3} className={FIELD} {...register("description")} />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="location" className="block text-sm font-medium">
              Location (optional)
            </label>
            <input id="location" className={FIELD} {...register("location")} />
          </div>
          <div>
            <label htmlFor="contact" className="block text-sm font-medium">
              Contact (optional)
            </label>
            <input id="contact" className={FIELD} {...register("contact")} />
          </div>
        </div>
        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-md bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-800 disabled:opacity-50"
        >
          {isSubmitting ? "Saving…" : "Create facility"}
        </button>
      </form>
    </div>
  );
}

import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { z } from "zod";

import { PageHeader } from "@/components/ui/PageHeader";
import { useAuth } from "@/features/auth/authContext";
import { fetchDepartments } from "@/features/directory/api-org";
import { toApiError } from "@/lib/api/errors";

import { createFacility } from "./api";

/**
 * `""` means university-wide. It is a deliberate choice in the dropdown
 * rather than the default, because a facility with no department can be
 * managed by administrators alone -- no coordinator can reach it, and it
 * counts towards no department's figures.
 */
const UNIVERSITY_WIDE = "";
/**
 * The initial value, and rejected on submit. Neither a department nor
 * university-wide may be arrived at by not choosing: this form used to
 * default an administrator to their own department_id, which is null, so
 * every facility an admin created came out university-wide by accident.
 */
const UNSET = "unset";

const schema = z.object({
  name: z.string().trim().min(1, "Name is required").max(200),
  description: z.string().max(5000),
  department_id: z
    .string()
    .refine((value) => value !== UNSET, "Choose which department runs this facility"),
  location: z.string().max(300),
  contact: z.string().max(300),
});

type FormValues = z.infer<typeof schema>;

const FIELD = "mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm";

/**
 * Create a facility.
 *
 * An administrator chooses the department; a coordinator's is fixed to the one
 * they oversee and shown read-only, so they can see where it will live without
 * being offered a choice the API would refuse.
 *
 * Before this the form sent `user.department_id` for an administrator -- which
 * is null, because an administrator belongs to no department -- so every
 * facility an admin created came out departmentless and unreachable by any
 * coordinator.
 */
export function FacilityFormPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const isAdmin = user?.role === "admin";
  const { data: departments } = useQuery({
    queryKey: ["departments"],
    queryFn: () => fetchDepartments(),
  });
  const ownDepartment = departments?.find((d) => d.id === user?.department_id);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: "",
      description: "",
      // A coordinator's is fixed and never sent; an admin must choose.
      department_id: user?.department_id ?? UNSET,
      location: "",
      contact: "",
    },
  });

  const submit = handleSubmit(async (values) => {
    setError(null);
    try {
      const facility = await createFacility({
        name: values.name,
        description: values.description || null,
        location: values.location || null,
        contact: values.contact || null,
        // A coordinator may not name a department other than their own, and
        // the API applies their scope regardless, so only an admin's choice
        // is sent. Empty string means university-wide.
        department_id: isAdmin ? values.department_id || null : null,
      });
      await queryClient.invalidateQueries({ queryKey: ["facilities"] });
      void navigate(`/facilities/${facility.id}`, { replace: true });
    } catch (caught) {
      setError(toApiError(caught).message);
    }
  });

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader
        title="New facility"
        description="A lab, workshop or instrumentation centre at Lovely Professional University (LPU). The department you choose decides who can manage it afterwards."
      />

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
          <label htmlFor="department_id" className="block text-sm font-medium">
            Department
          </label>
          {isAdmin ? (
            <>
              <select id="department_id" className={FIELD} {...register("department_id")}>
                <option value={UNSET} disabled>
                  Choose a department…
                </option>
                {departments?.map((department) => (
                  <option key={department.id} value={department.id}>
                    {department.name}
                  </option>
                ))}
                <option value={UNIVERSITY_WIDE}>University-wide — administrators only</option>
              </select>
              {errors.department_id ? (
                <p className="mt-1 text-xs text-red-700">{errors.department_id.message}</p>
              ) : null}
              <p className="mt-1 text-xs text-ink-muted">
                The department&apos;s research coordinator will be able to manage this facility,
                approve its bookings and assign a custodian. Choose university-wide only if it
                should belong to no department — nobody but an administrator will be able to manage
                it.
              </p>
            </>
          ) : (
            <>
              <input
                id="department_id"
                className={`${FIELD} bg-canvas text-ink-muted`}
                value={ownDepartment?.name ?? "Your department"}
                readOnly
                disabled
              />
              <p className="mt-1 text-xs text-ink-muted">
                Facilities you create belong to the department you oversee.
              </p>
            </>
          )}
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

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { z } from "zod";

import { PageHeader } from "@/components/ui/PageHeader";
import { useAuth } from "@/features/auth/authContext";
import { fetchDepartments } from "@/features/directory/api-org";
import { toApiError } from "@/lib/api/errors";

import { appointFacilityCustodian } from "./api";

const schema = z.object({
  registration_number: z
    .string()
    .trim()
    .min(4, "Registration number is required")
    .max(50, "That's too long for a registration number"),
  full_name: z.string().trim().min(1, "Full name is required").max(200),
  department_id: z.string(),
  email: z
    .string()
    .trim()
    .refine((value) => !value || /.+@.+\..+/.test(value), "Enter a valid email address"),
});

type FormValues = z.infer<typeof schema>;

const FIELD = "mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm";

/**
 * Appoint a facility custodian.
 *
 * There is no role to choose: the endpoint only ever makes a custodian, which
 * is how a coordinator gained this without a `role` field reappearing in the
 * request (ADR 0030). A coordinator's department is fixed to the one they
 * oversee; an administrator picks.
 */
export function AppointCustodianPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<{ name: string; password: string } | null>(null);
  const [copied, setCopied] = useState(false);

  const isAdmin = user?.role === "admin";
  const { data: departments } = useQuery({
    queryKey: ["departments"],
    queryFn: () => fetchDepartments(),
  });
  const ownDepartment = departments?.find((d) => d.id === user?.department_id);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { registration_number: "", full_name: "", department_id: "", email: "" },
  });

  const mutation = useMutation({
    mutationFn: (values: FormValues) =>
      appointFacilityCustodian({
        registration_number: values.registration_number,
        full_name: values.full_name,
        // A coordinator may not name a department; the API applies their own.
        department_id: isAdmin ? values.department_id || null : null,
        email: values.email || null,
      }),
    onSuccess: async (result) => {
      setError(null);
      setCopied(false);
      setCreated({ name: result.user.full_name, password: result.temporary_password });
      reset({ registration_number: "", full_name: "", department_id: "", email: "" });
      await queryClient.invalidateQueries({ queryKey: ["custodian-candidates"] });
      await queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
    onError: (caught: unknown) => setError(toApiError(caught).message),
  });

  const submit = handleSubmit((values) => {
    setError(null);
    mutation.mutate(values);
  });

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader
        title="Appoint a facility custodian"
        description="Somebody who looks after the facilities assigned to them and approves bookings for those, and nothing else. Assign them rooms afterwards from the facility's own page."
      />

      {created ? (
        <div className="mt-2 mb-4 rounded-card border border-brand-200 bg-brand-50 p-4">
          <h2 className="text-sm font-semibold">Appointed {created.name}</h2>
          <p className="mt-1 text-sm">
            Give them this temporary password. They&apos;ll choose their own at first sign-in.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <code className="rounded-md border border-line bg-surface px-3 py-2 font-mono text-sm">
              {created.password}
            </code>
            <button
              type="button"
              onClick={() => {
                void navigator.clipboard?.writeText(created.password);
                setCopied(true);
              }}
              className="rounded-md border border-line bg-surface px-3 py-2 text-sm font-medium"
            >
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <p className="mt-2 text-xs text-ink-muted">
            This is shown once. Next:{" "}
            <Link to="/facilities" className="font-medium text-brand-700 hover:underline">
              give them a facility
            </Link>
            .
          </p>
        </div>
      ) : null}

      {error ? (
        <p role="alert" className="mb-4 text-sm text-red-700">
          {error}
        </p>
      ) : null}

      <form onSubmit={(event) => void submit(event)} className="space-y-4" noValidate>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="registration_number" className="block text-sm font-medium">
              Registration number
            </label>
            <input
              id="registration_number"
              autoCapitalize="characters"
              spellCheck={false}
              className={FIELD}
              {...register("registration_number")}
            />
            {errors.registration_number ? (
              <p className="mt-1 text-xs text-red-700">{errors.registration_number.message}</p>
            ) : null}
          </div>
          <div>
            <label htmlFor="full_name" className="block text-sm font-medium">
              Full name
            </label>
            <input id="full_name" className={FIELD} {...register("full_name")} />
            {errors.full_name ? (
              <p className="mt-1 text-xs text-red-700">{errors.full_name.message}</p>
            ) : null}
          </div>
        </div>

        <div>
          <label htmlFor="department_id" className="block text-sm font-medium">
            Department
          </label>
          {isAdmin ? (
            <select id="department_id" className={FIELD} {...register("department_id")}>
              <option value="">Choose a department…</option>
              {departments?.map((department) => (
                <option key={department.id} value={department.id}>
                  {department.name}
                </option>
              ))}
            </select>
          ) : (
            <input
              id="department_id"
              className={`${FIELD} bg-canvas text-ink-muted`}
              value={ownDepartment?.name ?? "Your department"}
              readOnly
              disabled
            />
          )}
          <p className="mt-1 text-xs text-ink-muted">
            A custodian must belong to the department that runs the facilities they look after.
          </p>
        </div>

        <div>
          <label htmlFor="email" className="block text-sm font-medium">
            Email <span className="font-normal text-ink-muted">(optional)</span>
          </label>
          <input id="email" type="email" className={FIELD} {...register("email")} />
          {errors.email ? (
            <p className="mt-1 text-xs text-red-700">{errors.email.message}</p>
          ) : null}
        </div>

        <button
          type="submit"
          disabled={isSubmitting || mutation.isPending}
          className="rounded-md bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-800 disabled:opacity-50"
        >
          {mutation.isPending ? "Appointing…" : "Appoint custodian"}
        </button>
      </form>
    </div>
  );
}

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { z } from "zod";

import type { Role } from "@/features/auth/types";
import { fetchDepartments } from "@/features/directory/api-org";
import { toApiError } from "@/lib/api/errors";

import { createAccountAsAdmin } from "./api";

/**
 * The admin override: create an account of any role directly.
 *
 * The ordinary path (Add coordinator → they add faculty → faculty add
 * students) is how the platform is meant to grow, and it stays the default.
 * This is the escape hatch for the cases it cannot serve — a department with
 * no coordinator yet, a correction, a second administrator — and it is
 * audited as `user.created_by_admin` so it never reads as an ordinary
 * appointment.
 */
const schema = z.object({
  registration_number: z
    .string()
    .trim()
    .min(4, "Registration number is required")
    .max(50, "That's too long for a registration number"),
  full_name: z.string().trim().min(1, "Full name is required").max(200),
  role: z.enum(["student", "faculty", "research_coordinator", "admin"]),
  department_id: z.string(),
  email: z
    .string()
    .trim()
    .refine((value) => !value || /.+@.+\..+/.test(value), "Enter a valid email address"),
});

type FormValues = z.infer<typeof schema>;

const ROLE_LABELS: Record<Role, string> = {
  student: "Student",
  faculty: "Faculty / researcher",
  research_coordinator: "Research coordinator",
  admin: "Administrator",
};

const FIELD = "mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm";

export function AdminCreateAccountPage() {
  const queryClient = useQueryClient();
  const [created, setCreated] = useState<{ name: string; password: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const { data: departments } = useQuery({
    queryKey: ["departments"],
    queryFn: () => fetchDepartments(),
  });

  // The role drives the copy and whether a department is required. Tracked in
  // state rather than through `watch`, which the React Compiler cannot see
  // into and therefore skips optimising the whole component over.
  const [role, setRole] = useState<Role>("faculty");
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      role: "faculty",
      department_id: "",
      email: "",
      registration_number: "",
      full_name: "",
    },
  });

  // Only another admin is scoped to everything; everyone else lives in a
  // department, and the API says so too.
  const departmentRequired = role !== "admin";
  const roleField = register("role");

  const mutation = useMutation({
    mutationFn: (values: FormValues) =>
      createAccountAsAdmin({
        registration_number: values.registration_number,
        full_name: values.full_name,
        role: values.role,
        department_id: values.department_id || null,
        email: values.email || null,
      }),
    onSuccess: async (result) => {
      setCreated({ name: result.user.full_name, password: result.temporary_password });
      setCopied(false);
      setRole(result.user.role);
      reset({
        role: result.user.role,
        department_id: "",
        registration_number: "",
        full_name: "",
        email: "",
      });
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
      <h1 className="text-2xl font-semibold tracking-tight">Create any account</h1>
      <p className="mt-1 text-sm text-ink-muted">
        The override. Normally a coordinator appoints faculty and faculty enrol students — use{" "}
        <Link to="/people/new" className="font-medium text-brand-700 hover:underline">
          Add coordinator
        </Link>{" "}
        for that. This page bypasses the chain, and every account it makes is recorded in the audit
        log as an admin override.
      </p>

      {created ? (
        <div className="mt-6 rounded-card border border-brand-200 bg-brand-50 p-4">
          <h2 className="text-sm font-semibold">Account created for {created.name}</h2>
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
          <p className="mt-2 text-xs text-ink-muted">This is shown once.</p>
        </div>
      ) : null}

      {error ? (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {error}
        </p>
      ) : null}

      <form onSubmit={(event) => void submit(event)} className="mt-6 space-y-4" noValidate>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="registration_number" className="block text-sm font-medium">
              Registration number
            </label>
            <input
              id="registration_number"
              autoCapitalize="characters"
              spellCheck={false}
              placeholder="e.g. 12345678"
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

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="role" className="block text-sm font-medium">
              Role
            </label>
            <select
              id="role"
              className={FIELD}
              {...roleField}
              onChange={(event) => {
                setRole(event.target.value as Role);
                void roleField.onChange(event);
              }}
            >
              {(Object.keys(ROLE_LABELS) as Role[]).map((value) => (
                <option key={value} value={value}>
                  {ROLE_LABELS[value]}
                </option>
              ))}
            </select>
            {role === "admin" ? (
              <p className="mt-1 text-xs text-brand-700">
                A second administrator can do everything you can, immediately.
              </p>
            ) : null}
          </div>
          <div>
            <label htmlFor="department_id" className="block text-sm font-medium">
              Department{" "}
              {departmentRequired ? null : (
                <span className="font-normal text-ink-muted">(optional for an admin)</span>
              )}
            </label>
            <select id="department_id" className={FIELD} {...register("department_id")}>
              <option value="">{departmentRequired ? "Choose a department" : "None"}</option>
              {departments?.map((department) => (
                <option key={department.id} value={department.id}>
                  {department.name}
                </option>
              ))}
            </select>
            {role === "research_coordinator" ? (
              <p className="mt-1 text-xs text-ink-muted">
                This becomes the department they oversee.
              </p>
            ) : null}
          </div>
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
          {mutation.isPending ? "Creating…" : `Create ${ROLE_LABELS[role].toLowerCase()}`}
        </button>
      </form>
    </div>
  );
}

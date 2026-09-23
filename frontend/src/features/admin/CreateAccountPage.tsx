import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { z } from "zod";

import { useAuth } from "@/features/auth/authContext";
import { fetchDepartments } from "@/features/directory/api-org";
import { apiClient } from "@/lib/api/client";
import { toApiError } from "@/lib/api/errors";

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

interface CreatedAccount {
  user: { id: string; registration_number: string; full_name: string; role: string };
  temporary_password: string;
}

const FIELD = "mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm";

/**
 * Create an account for someone else.
 *
 * Students don't sign up themselves, so their department does it here. The
 * temporary password is shown once, right after creation — it is never
 * retrievable again.
 */
export function CreateAccountPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [created, setCreated] = useState<CreatedAccount | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const isAdmin = user?.role === "admin";
  const { data: departments } = useQuery({
    queryKey: ["departments"],
    queryFn: () => fetchDepartments(),
    enabled: isAdmin,
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      role: "student",
      department_id: "",
      email: "",
      registration_number: "",
      full_name: "",
    },
  });

  const submit = handleSubmit(async (values) => {
    setError(null);
    setCopied(false);
    try {
      const response = await apiClient.post<CreatedAccount>("/api/v1/users", {
        registration_number: values.registration_number,
        full_name: values.full_name,
        role: values.role,
        // Faculty and coordinators can only add to their own department, and
        // the API applies that itself.
        department_id: isAdmin && values.department_id ? values.department_id : null,
        email: values.email || null,
      });
      setCreated(response.data);
      await queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      reset({
        role: values.role,
        department_id: values.department_id,
        registration_number: "",
        full_name: "",
        email: "",
      });
    } catch (caught) {
      setError(toApiError(caught).message);
    }
  });

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-2xl font-semibold tracking-tight">Add a person</h1>
      <p className="mt-1 text-sm text-ink-muted">
        {isAdmin
          ? "Create an account for anyone. They sign in with their registration number."
          : "Create a student account in your department. They sign in with their registration number."}
      </p>

      {created ? (
        <div className="mt-6 rounded-card border border-brand-200 bg-brand-50 p-4">
          <h2 className="text-sm font-semibold">
            Account created for {created.user.full_name} ({created.user.registration_number})
          </h2>
          <p className="mt-1 text-sm">
            Give them this temporary password. They&apos;ll be asked to choose their own the first
            time they sign in.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <code className="rounded-md border border-line bg-surface px-3 py-2 font-mono text-sm">
              {created.temporary_password}
            </code>
            <button
              type="button"
              onClick={() => {
                void navigator.clipboard?.writeText(created.temporary_password);
                setCopied(true);
              }}
              className="rounded-md border border-line bg-surface px-3 py-2 text-sm font-medium"
            >
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <p className="mt-2 text-xs text-ink-muted">
            This is shown once. If it&apos;s lost, an admin can issue a new one from the{" "}
            <strong>Users</strong> page.
          </p>
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

        {isAdmin ? (
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="role" className="block text-sm font-medium">
                Role
              </label>
              <select id="role" className={FIELD} {...register("role")}>
                <option value="student">Student</option>
                <option value="faculty">Faculty / researcher</option>
                <option value="research_coordinator">Research coordinator</option>
                <option value="admin">Admin</option>
              </select>
            </div>
            <div>
              <label htmlFor="department_id" className="block text-sm font-medium">
                Department
              </label>
              <select id="department_id" className={FIELD} {...register("department_id")}>
                <option value="">No department</option>
                {departments?.map((department) => (
                  <option key={department.id} value={department.id}>
                    {department.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
        ) : (
          <p className="text-xs text-ink-muted">
            The account is created as a student in your own department. If you don&apos;t have one
            yet, set it on your{" "}
            <Link to="/profile" className="font-medium text-brand-700 hover:underline">
              profile
            </Link>
            .
          </p>
        )}

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
          disabled={isSubmitting}
          className="rounded-md bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-800 disabled:opacity-50"
        >
          {isSubmitting ? "Creating…" : "Create account"}
        </button>
      </form>
    </div>
  );
}

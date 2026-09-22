import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { z } from "zod";

import { toApiError } from "@/lib/api/errors";

import { useAuth } from "./authContext";

const registerSchema = z.object({
  fullName: z.string().min(1, "Full name is required").max(200, "Full name is too long"),
  email: z.string().min(1, "Email is required").email("Enter a valid email address"),
  password: z.string().min(10, "Password must be at least 10 characters"),
  role: z.enum(["student", "faculty"], { message: "Choose a role" }),
});

type RegisterFormValues = z.infer<typeof registerSchema>;

export function RegisterPage() {
  const { register: registerUser } = useAuth();
  const navigate = useNavigate();
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { role: "student" },
  });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await registerUser({
        email: values.email,
        password: values.password,
        full_name: values.fullName,
        role: values.role,
      });
      void navigate("/account", { replace: true });
    } catch (error) {
      setFormError(toApiError(error).message);
    }
  });

  return (
    <div className="mx-auto max-w-sm">
      <h1 className="text-2xl font-semibold tracking-tight">Create an account</h1>
      <p className="mt-1 text-sm text-ink-muted">For students and faculty.</p>

      <form onSubmit={(event) => void onSubmit(event)} className="mt-6 space-y-4" noValidate>
        <div>
          <label htmlFor="fullName" className="block text-sm font-medium">
            Full name
          </label>
          <input
            id="fullName"
            type="text"
            autoComplete="name"
            className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm"
            {...register("fullName")}
          />
          {errors.fullName ? (
            <p className="mt-1 text-xs text-red-700">{errors.fullName.message}</p>
          ) : null}
        </div>

        <div>
          <label htmlFor="email" className="block text-sm font-medium">
            Email
          </label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm"
            {...register("email")}
          />
          {errors.email ? (
            <p className="mt-1 text-xs text-red-700">{errors.email.message}</p>
          ) : null}
        </div>

        <div>
          <label htmlFor="password" className="block text-sm font-medium">
            Password
          </label>
          <input
            id="password"
            type="password"
            autoComplete="new-password"
            className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm"
            {...register("password")}
          />
          {errors.password ? (
            <p className="mt-1 text-xs text-red-700">{errors.password.message}</p>
          ) : null}
        </div>

        <div>
          <label htmlFor="role" className="block text-sm font-medium">
            I am a
          </label>
          <select
            id="role"
            className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm"
            {...register("role")}
          >
            <option value="student">Student</option>
            <option value="faculty">Faculty / researcher</option>
          </select>
          {errors.role ? <p className="mt-1 text-xs text-red-700">{errors.role.message}</p> : null}
        </div>

        {formError ? (
          <p role="alert" className="text-sm text-red-700">
            {formError}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full rounded-md bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isSubmitting ? "Creating account…" : "Create account"}
        </button>
      </form>

      <p className="mt-4 text-sm text-ink-muted">
        Already have an account?{" "}
        <Link to="/login" className="font-medium text-brand-700 hover:underline">
          Log in
        </Link>
      </p>
    </div>
  );
}

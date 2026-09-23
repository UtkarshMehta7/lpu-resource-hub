import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";

import { toApiError } from "@/lib/api/errors";

import { useAuth } from "./authContext";

const loginSchema = z.object({
  registration_number: z
    .string()
    .trim()
    .min(1, "Registration number is required")
    .max(50, "That's too long for a registration number"),
  password: z.string().min(1, "Password is required"),
});

type LoginFormValues = z.infer<typeof loginSchema>;

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({ resolver: zodResolver(loginSchema) });

  const redirectTo =
    typeof (location.state as { from?: string } | null)?.from === "string"
      ? (location.state as { from: string }).from
      : "/account";

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      // The main entrance. An administrator is refused here and told
      // where to go -- the check is the server's, not this page's.
      await login({ ...values, portal: "main" });
      void navigate(redirectTo, { replace: true });
    } catch (error) {
      setFormError(toApiError(error).message);
    }
  });

  return (
    <div className="mx-auto max-w-sm">
      <h1 className="text-2xl font-semibold tracking-tight">Log in</h1>
      <p className="mt-1 text-sm text-ink-muted">
        Sign in with your LPU registration number, the same one you use for UMS.
      </p>

      <form onSubmit={(event) => void onSubmit(event)} className="mt-6 space-y-4" noValidate>
        <div>
          <label htmlFor="registration_number" className="block text-sm font-medium">
            Registration number
          </label>
          <input
            id="registration_number"
            type="text"
            inputMode="text"
            autoComplete="username"
            autoCapitalize="characters"
            spellCheck={false}
            placeholder="e.g. 12345678"
            className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm"
            {...register("registration_number")}
          />
          {errors.registration_number ? (
            <p className="mt-1 text-xs text-red-700">{errors.registration_number.message}</p>
          ) : null}
        </div>

        <div>
          <label htmlFor="password" className="block text-sm font-medium">
            Password
          </label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm"
            {...register("password")}
          />
          {errors.password ? (
            <p className="mt-1 text-xs text-red-700">{errors.password.message}</p>
          ) : null}
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
          {isSubmitting ? "Logging in…" : "Log in"}
        </button>
      </form>

      <p className="mt-4 text-sm text-ink-muted">
        Accounts are created for you by your department. If you don&apos;t have one yet, ask your
        research coordinator or supervisor.
      </p>
      <p className="mt-2 text-sm text-ink-muted">
        Platform administrator?{" "}
        <Link to="/admin/login" className="font-medium text-brand-700 hover:underline">
          Sign in to administration
        </Link>
        .
      </p>
    </div>
  );
}

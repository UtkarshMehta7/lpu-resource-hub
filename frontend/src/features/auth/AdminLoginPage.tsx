import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { z } from "zod";

import { Crest, UNIVERSITY_NAME } from "@/components/layout/Brand";
import { toApiError } from "@/lib/api/errors";

import { useAuth } from "./authContext";

/**
 * Administration sign-in.
 *
 * A distinct door, not a stronger lock: the credentials, the endpoint and the
 * rate limit are the same as the ordinary login, and the authority comes from
 * the role on the account. What this page adds is that an administrator lands
 * on /admin rather than a dashboard, and that the address is not one a
 * student ever has reason to visit.
 */
const schema = z.object({
  registration_number: z
    .string()
    .trim()
    .min(1, "Registration number is required")
    .max(50, "That's too long for a registration number"),
  password: z.string().min(1, "Password is required"),
});

type FormValues = z.infer<typeof schema>;

const FIELD =
  "mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-200";

export function AdminLoginPage() {
  const { login, user } = useAuth();
  const navigate = useNavigate();
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await login({ ...values, portal: "admin" });
      // Where you land is decided after the fact, from the role the server
      // returned -- this page cannot grant anything by sending you to /admin.
      void navigate("/admin", { replace: true });
    } catch (error) {
      setFormError(toApiError(error).message);
    }
  });

  return (
    <div className="mx-auto max-w-md">
      <div className="rounded-card border border-line bg-surface p-6 shadow-sm sm:p-8">
        <div className="flex items-center gap-3">
          <Crest className="size-12" />
          <div className="leading-tight">
            <p className="text-xs font-medium text-brand-700">{UNIVERSITY_NAME}</p>
            <h1 className="text-xl font-semibold tracking-tight">Administration</h1>
          </div>
        </div>

        <p className="mt-4 text-sm text-ink-muted">
          For platform administrators only. Everyone else signs in on the{" "}
          <Link to="/login" className="font-medium text-brand-700 hover:underline">
            main login
          </Link>
          .
        </p>

        <form onSubmit={(event) => void onSubmit(event)} className="mt-6 space-y-4" noValidate>
          <div>
            <label htmlFor="registration_number" className="block text-sm font-medium">
              Registration number
            </label>
            <input
              id="registration_number"
              type="text"
              autoComplete="username"
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
            <label htmlFor="password" className="block text-sm font-medium">
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              className={FIELD}
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
            {isSubmitting ? "Signing in…" : "Sign in to administration"}
          </button>
        </form>

        {user && user.role !== "admin" ? (
          <p className="mt-4 text-sm text-ink-muted">
            You&apos;re signed in as a {user.role.replace("_", " ")}, so the administration pages
            stay closed.{" "}
            <Link to="/dashboard" className="font-medium text-brand-700 hover:underline">
              Go to your dashboard
            </Link>
            .
          </p>
        ) : null}
      </div>

      <p className="mt-4 text-center text-xs text-ink-muted">
        A separate entrance, enforced on the server: a non-administrator is refused here even with
        the right password, and administrators are refused on the main page.
      </p>
    </div>
  );
}

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { z } from "zod";

import { changePasswordRequest } from "@/features/auth/api";
import { useAuth } from "@/features/auth/authContext";
import { toApiError } from "@/lib/api/errors";

const schema = z
  .object({
    current_password: z.string().min(1, "Enter the temporary password you were given"),
    new_password: z.string().min(10, "Password must be at least 10 characters"),
    confirm_password: z.string(),
  })
  .refine((values) => values.new_password === values.confirm_password, {
    message: "The two passwords don't match",
    path: ["confirm_password"],
  });

type FormValues = z.infer<typeof schema>;

const FIELD = "mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm";

/**
 * Shown to someone whose account was created for them: until the temporary
 * password is replaced the API refuses everything else, so there is nowhere
 * else for them to go.
 */
export function ChangePasswordRequiredPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const submit = handleSubmit(async (values) => {
    setError(null);
    try {
      await changePasswordRequest({
        current_password: values.current_password,
        new_password: values.new_password,
      });
      // Changing the password revokes every session, so sign in again.
      await logout();
      void navigate("/login", { replace: true });
    } catch (caught) {
      setError(toApiError(caught).message);
    }
  });

  return (
    <div className="mx-auto max-w-sm">
      <h1 className="text-2xl font-semibold tracking-tight">Choose your password</h1>
      <p className="mt-1 text-sm text-ink-muted">
        {user ? `Welcome, ${user.full_name.split(" ")[0]}. ` : ""}
        Your account was created with a temporary password. Pick your own to continue — you&apos;ll
        sign in again afterwards.
      </p>

      {error ? (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {error}
        </p>
      ) : null}

      <form onSubmit={(event) => void submit(event)} className="mt-6 space-y-4" noValidate>
        <div>
          <label htmlFor="current_password" className="block text-sm font-medium">
            Temporary password
          </label>
          <input
            id="current_password"
            type="password"
            autoComplete="current-password"
            className={FIELD}
            {...register("current_password")}
          />
          {errors.current_password ? (
            <p className="mt-1 text-xs text-red-700">{errors.current_password.message}</p>
          ) : null}
        </div>
        <div>
          <label htmlFor="new_password" className="block text-sm font-medium">
            New password
          </label>
          <input
            id="new_password"
            type="password"
            autoComplete="new-password"
            className={FIELD}
            {...register("new_password")}
          />
          {errors.new_password ? (
            <p className="mt-1 text-xs text-red-700">{errors.new_password.message}</p>
          ) : null}
        </div>
        <div>
          <label htmlFor="confirm_password" className="block text-sm font-medium">
            Confirm new password
          </label>
          <input
            id="confirm_password"
            type="password"
            autoComplete="new-password"
            className={FIELD}
            {...register("confirm_password")}
          />
          {errors.confirm_password ? (
            <p className="mt-1 text-xs text-red-700">{errors.confirm_password.message}</p>
          ) : null}
        </div>
        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full rounded-md bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-800 disabled:opacity-50"
        >
          {isSubmitting ? "Saving…" : "Set my password"}
        </button>
      </form>
    </div>
  );
}

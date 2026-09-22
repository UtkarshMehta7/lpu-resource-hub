import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { z } from "zod";

import { toApiError } from "@/lib/api/errors";

import { useAuth } from "./authContext";
import { changePasswordRequest } from "./api";

const changePasswordSchema = z.object({
  currentPassword: z.string().min(1, "Current password is required"),
  newPassword: z.string().min(10, "New password must be at least 10 characters"),
});

type ChangePasswordFormValues = z.infer<typeof changePasswordSchema>;

/** Changing your password revokes every session, this one included, so we sign out after. */
export function ChangePasswordForm() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ChangePasswordFormValues>({ resolver: zodResolver(changePasswordSchema) });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await changePasswordRequest({
        current_password: values.currentPassword,
        new_password: values.newPassword,
      });
      await logout();
      void navigate("/login", { replace: true });
    } catch (error) {
      setFormError(toApiError(error).message);
    }
  });

  return (
    <form onSubmit={(event) => void onSubmit(event)} className="space-y-4" noValidate>
      <div>
        <label htmlFor="currentPassword" className="block text-sm font-medium">
          Current password
        </label>
        <input
          id="currentPassword"
          type="password"
          autoComplete="current-password"
          className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm"
          {...register("currentPassword")}
        />
        {errors.currentPassword ? (
          <p className="mt-1 text-xs text-red-700">{errors.currentPassword.message}</p>
        ) : null}
      </div>

      <div>
        <label htmlFor="newPassword" className="block text-sm font-medium">
          New password
        </label>
        <input
          id="newPassword"
          type="password"
          autoComplete="new-password"
          className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm"
          {...register("newPassword")}
        />
        {errors.newPassword ? (
          <p className="mt-1 text-xs text-red-700">{errors.newPassword.message}</p>
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
        className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm font-medium hover:bg-canvas disabled:cursor-not-allowed disabled:opacity-50"
      >
        {isSubmitting ? "Changing password…" : "Change password"}
      </button>
    </form>
  );
}

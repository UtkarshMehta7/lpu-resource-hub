import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { StatusIndicator, type StatusTone } from "@/components/ui/StatusIndicator";
import { useAuth } from "@/features/auth/authContext";
import { toApiError } from "@/lib/api/errors";

import { fetchMyProfile, saveProfile } from "./api";
import { ProfileForm } from "./ProfileForm";
import type { ResearcherProfileUpdate, StudentProfileUpdate, VerificationStatus } from "./types";

const PROFILE_QUERY_KEY = ["profile"] as const;

const VERIFICATION_VIEW: Record<VerificationStatus, { tone: StatusTone; label: string }> = {
  unverified: { tone: "neutral", label: "Not submitted" },
  pending: { tone: "warning", label: "Pending review" },
  verified: { tone: "success", label: "Verified" },
  rejected: { tone: "danger", label: "Rejected" },
};

export function ProfilePage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [saveError, setSaveError] = useState<string | null>(null);
  const [justSaved, setJustSaved] = useState(false);

  const { data: profile, isPending } = useQuery({
    queryKey: PROFILE_QUERY_KEY,
    queryFn: fetchMyProfile,
  });

  const mutation = useMutation({
    mutationFn: (update: StudentProfileUpdate | ResearcherProfileUpdate) => saveProfile(update),
    onSuccess: async () => {
      setSaveError(null);
      setJustSaved(true);
      await queryClient.invalidateQueries({ queryKey: PROFILE_QUERY_KEY });
    },
    onError: (error: unknown) => {
      setJustSaved(false);
      setSaveError(toApiError(error).message);
    },
  });

  if (!user) return null;

  if (isPending) {
    return <p className="text-sm text-ink-muted">Loading your profile…</p>;
  }

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-2xl font-semibold tracking-tight">My profile</h1>

      {profile === null ? (
        <p className="mt-2 text-sm text-ink-muted">
          You haven&apos;t set up a profile yet.{" "}
          <Link to="/onboarding" className="font-medium text-brand-700 hover:underline">
            Start onboarding
          </Link>
          .
        </p>
      ) : null}

      {profile?.profile_type === "researcher" ? (
        <div className="mt-4 flex items-center gap-3 rounded-card border border-line bg-surface px-4 py-3">
          <span className="text-sm text-ink-muted">Verification</span>
          <StatusIndicator
            tone={VERIFICATION_VIEW[profile.verification_status].tone}
            label={VERIFICATION_VIEW[profile.verification_status].label}
          />
        </div>
      ) : null}

      {saveError ? (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {saveError}
        </p>
      ) : null}

      {justSaved && !saveError ? (
        <p role="status" className="mt-4 text-sm text-emerald-700">
          Profile saved.
        </p>
      ) : null}

      <div className="mt-6">
        <ProfileForm
          key={profile?.updated_at ?? "new"}
          role={user.role}
          profile={profile ?? null}
          submitLabel="Save changes"
          onSubmit={async (update) => {
            await mutation.mutateAsync(update);
          }}
        />
      </div>

      <section className="mt-10">
        <h2 className="text-base font-semibold">Skills and research areas</h2>
        <p className="mt-1 text-sm text-ink-muted">
          {user.onboarding_complete
            ? "Your expertise is complete enough for recommendations."
            : "Add at least 3 skills and 3 research areas to enable recommendations."}
        </p>
        <Link
          to="/onboarding"
          className="mt-3 inline-block rounded-md border border-line bg-surface px-3 py-1.5 text-sm font-medium hover:bg-canvas"
        >
          Edit skills and research areas
        </Link>
      </section>
    </div>
  );
}

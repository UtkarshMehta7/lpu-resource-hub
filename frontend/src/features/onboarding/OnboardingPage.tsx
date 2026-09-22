import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "@/features/auth/authContext";
import { saveProfile, saveResearchAreas, saveSkills } from "@/features/profiles/api";
import {
  ResearchAreasPicker,
  type SelectedResearchArea,
} from "@/features/profiles/ResearchAreasPicker";
import { ProfileForm } from "@/features/profiles/ProfileForm";
import { SkillsPicker, type SelectedSkill } from "@/features/profiles/SkillsPicker";
import { toApiError } from "@/lib/api/errors";

const STEPS = ["Your profile", "Skills", "Research areas"] as const;
const MIN_FOR_RECOMMENDATIONS = 3;

const NEXT_BUTTON_CLASS =
  "rounded-md bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-800 disabled:cursor-not-allowed disabled:opacity-50";
const BACK_BUTTON_CLASS =
  "rounded-md border border-line bg-surface px-3 py-2 text-sm font-medium hover:bg-canvas";

export function OnboardingPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [step, setStep] = useState(0);
  const [skills, setSkills] = useState<SelectedSkill[]>([]);
  const [areas, setAreas] = useState<SelectedResearchArea[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isFinishing, setIsFinishing] = useState(false);

  if (!user) return null;

  const finish = async () => {
    setError(null);
    setIsFinishing(true);
    try {
      await saveSkills(skills.map((s) => ({ skill_id: s.id, proficiency: s.proficiency })));
      await saveResearchAreas(
        areas.map((a) => ({ research_area_id: a.id, is_expertise: a.isExpertise })),
      );
      await queryClient.invalidateQueries({ queryKey: ["me"] });
      await queryClient.invalidateQueries({ queryKey: ["profile"] });
      void navigate("/profile", { replace: true });
    } catch (caught) {
      setError(toApiError(caught).message);
    } finally {
      setIsFinishing(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-2xl font-semibold tracking-tight">Set up your profile</h1>
      <p className="mt-1 text-sm text-ink-muted">
        Three quick steps. You can change any of this later.
      </p>

      <ol className="mt-6 flex gap-2" aria-label="Progress">
        {STEPS.map((title, index) => (
          <li
            key={title}
            aria-current={index === step ? "step" : undefined}
            className={`flex-1 rounded-md border px-3 py-2 text-xs font-medium ${
              index === step
                ? "border-brand-700 bg-brand-50 text-brand-800"
                : "border-line bg-surface text-ink-muted"
            }`}
          >
            {index + 1}. {title}
          </li>
        ))}
      </ol>

      {error ? (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {error}
        </p>
      ) : null}

      <div className="mt-6">
        {step === 0 ? (
          <ProfileForm
            role={user.role}
            profile={null}
            submitLabel="Save and continue"
            onSubmit={async (update) => {
              await saveProfile(update);
              await queryClient.invalidateQueries({ queryKey: ["profile"] });
              setStep(1);
            }}
          />
        ) : null}

        {step === 1 ? (
          <div className="space-y-6">
            <SkillsPicker selected={skills} onChange={setSkills} />
            <StepFooter
              count={skills.length}
              onBack={() => setStep(0)}
              onNext={() => setStep(2)}
              nextLabel="Continue"
            />
          </div>
        ) : null}

        {step === 2 ? (
          <div className="space-y-6">
            <ResearchAreasPicker selected={areas} onChange={setAreas} />
            <StepFooter
              count={areas.length}
              onBack={() => setStep(1)}
              onNext={() => void finish()}
              nextLabel={isFinishing ? "Finishing…" : "Finish"}
              disabled={isFinishing}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}

interface StepFooterProps {
  count: number;
  onBack: () => void;
  onNext: () => void;
  nextLabel: string;
  disabled?: boolean;
}

function StepFooter({ count, onBack, onNext, nextLabel, disabled }: StepFooterProps) {
  return (
    <div className="flex items-center justify-between gap-3">
      <p className="text-xs text-ink-muted">
        {count} selected
        {count < MIN_FOR_RECOMMENDATIONS
          ? ` — ${String(MIN_FOR_RECOMMENDATIONS - count)} more for recommendations`
          : " — enough for recommendations"}
      </p>
      <span className="flex gap-3">
        <button type="button" onClick={onBack} className={BACK_BUTTON_CLASS}>
          Back
        </button>
        <button type="button" onClick={onNext} disabled={disabled} className={NEXT_BUTTON_CLASS}>
          {nextLabel}
        </button>
      </span>
    </div>
  );
}

import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { useForm, type UseFormRegisterReturn } from "react-hook-form";
import { z } from "zod";

import type { Role } from "@/features/auth/types";
import { fetchDepartments } from "@/features/directory/api-org";

import type { Profile, ResearcherProfileUpdate, StudentProfileUpdate } from "./types";

const studentSchema = z.object({
  program: z.string().min(1, "Programme is required").max(150, "Programme is too long"),
  year: z
    .number({ message: "Year is required" })
    .int("Year must be a whole number")
    .min(1, "Year must be at least 1")
    .max(10, "Year must be 10 or less"),
  bio: z.string().max(5000, "Bio is too long"),
  interests: z.string().max(2000, "Interests are too long"),
  is_discoverable: z.boolean(),
  department_id: z.string(),
});

const researcherSchema = z.object({
  designation: z.string().min(1, "Designation is required").max(150, "Designation is too long"),
  bio: z.string().max(5000, "Bio is too long"),
  availability: z.enum(["available", "limited", "unavailable"]),
  link: z.union([z.literal(""), z.string().url("Enter a full URL, e.g. https://example.com")]),
  department_id: z.string(),
});

type StudentFormValues = z.infer<typeof studentSchema>;
type ResearcherFormValues = z.infer<typeof researcherSchema>;

const FIELD_CLASS = "mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm";
const SUBMIT_CLASS =
  "rounded-md bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-800 disabled:cursor-not-allowed disabled:opacity-50";

/**
 * Where you belong. Someone who registered for themselves has no department,
 * which leaves everything department-scoped closed to them -- so they state it
 * here. Once a coordinator has verified a researcher it stops being a claim,
 * and only an admin can change it.
 */
function DepartmentField({
  locked,
  register,
}: {
  locked: boolean;
  register: UseFormRegisterReturn;
}) {
  const { data: departments } = useQuery({
    queryKey: ["departments"],
    queryFn: () => fetchDepartments(),
    enabled: !locked,
  });

  if (locked) {
    return (
      <p className="text-xs text-ink-muted">
        Your department was confirmed when your profile was verified. Ask an admin to change it.
      </p>
    );
  }

  return (
    <div>
      <label htmlFor="department_id" className="block text-sm font-medium">
        Department
      </label>
      <select id="department_id" className={FIELD_CLASS} {...register}>
        <option value="">Not set</option>
        {departments?.map((department) => (
          <option key={department.id} value={department.id}>
            {department.name}
          </option>
        ))}
      </select>
      <p className="mt-1 text-xs text-ink-muted">
        Your department decides which coordinator reviews your work.
      </p>
    </div>
  );
}

interface ProfileFormProps {
  role: Role;
  profile: Profile | null;
  submitLabel: string;
  onSubmit: (update: StudentProfileUpdate | ResearcherProfileUpdate) => Promise<void>;
}

/** Role-aware profile form, shared by the onboarding wizard and the profile page. */
export function ProfileForm({ role, profile, submitLabel, onSubmit }: ProfileFormProps) {
  if (role === "student") {
    return <StudentForm profile={profile} submitLabel={submitLabel} onSubmit={onSubmit} />;
  }
  return <ResearcherForm profile={profile} submitLabel={submitLabel} onSubmit={onSubmit} />;
}

function StudentForm({ profile, submitLabel, onSubmit }: Omit<ProfileFormProps, "role">) {
  const existing = profile?.profile_type === "student" ? profile : null;
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<StudentFormValues>({
    resolver: zodResolver(studentSchema),
    defaultValues: {
      program: existing?.program ?? "",
      year: existing?.year ?? 1,
      bio: existing?.bio ?? "",
      interests: existing?.interests ?? "",
      is_discoverable: existing?.is_discoverable ?? false,
      department_id: existing?.department_id ?? "",
    },
  });

  const submit = handleSubmit(async (values) => {
    await onSubmit({
      program: values.program,
      year: values.year,
      bio: values.bio || null,
      interests: values.interests || null,
      is_discoverable: values.is_discoverable,
      department_id: values.department_id || null,
    });
  });

  return (
    <form onSubmit={(event) => void submit(event)} className="space-y-4" noValidate>
      <div>
        <label htmlFor="program" className="block text-sm font-medium">
          Programme
        </label>
        <input id="program" type="text" className={FIELD_CLASS} {...register("program")} />
        {errors.program ? (
          <p className="mt-1 text-xs text-red-700">{errors.program.message}</p>
        ) : null}
      </div>

      <div>
        <label htmlFor="year" className="block text-sm font-medium">
          Year of study
        </label>
        <input
          id="year"
          type="number"
          min={1}
          max={10}
          className={FIELD_CLASS}
          {...register("year", { valueAsNumber: true })}
        />
        {errors.year ? <p className="mt-1 text-xs text-red-700">{errors.year.message}</p> : null}
      </div>

      <DepartmentField
        locked={existing?.department_locked ?? false}
        register={register("department_id")}
      />

      <div>
        <label htmlFor="bio" className="block text-sm font-medium">
          About you
        </label>
        <textarea id="bio" rows={3} className={FIELD_CLASS} {...register("bio")} />
      </div>

      <div>
        <label htmlFor="interests" className="block text-sm font-medium">
          Research interests
        </label>
        <textarea id="interests" rows={2} className={FIELD_CLASS} {...register("interests")} />
      </div>

      <div className="flex items-start gap-2">
        <input
          id="is_discoverable"
          type="checkbox"
          className="mt-1"
          {...register("is_discoverable")}
        />
        <label htmlFor="is_discoverable" className="text-sm">
          Let faculty and coordinators discover my profile
          <span className="block text-xs text-ink-muted">
            Off by default. Only public profile fields are ever shown.
          </span>
        </label>
      </div>

      <button type="submit" disabled={isSubmitting} className={SUBMIT_CLASS}>
        {isSubmitting ? "Saving…" : submitLabel}
      </button>
    </form>
  );
}

function ResearcherForm({ profile, submitLabel, onSubmit }: Omit<ProfileFormProps, "role">) {
  const existing = profile?.profile_type === "researcher" ? profile : null;
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ResearcherFormValues>({
    resolver: zodResolver(researcherSchema),
    defaultValues: {
      designation: existing?.designation ?? "",
      bio: existing?.bio ?? "",
      availability: existing?.availability ?? "available",
      link: existing?.links?.[0]?.url ?? "",
      department_id: existing?.department_id ?? "",
    },
  });

  const submit = handleSubmit(async (values) => {
    await onSubmit({
      designation: values.designation,
      bio: values.bio || null,
      availability: values.availability,
      links: values.link ? [{ label: "Profile", url: values.link }] : null,
      department_id: values.department_id || null,
    });
  });

  return (
    <form onSubmit={(event) => void submit(event)} className="space-y-4" noValidate>
      <div>
        <label htmlFor="designation" className="block text-sm font-medium">
          Designation
        </label>
        <input id="designation" type="text" className={FIELD_CLASS} {...register("designation")} />
        {errors.designation ? (
          <p className="mt-1 text-xs text-red-700">{errors.designation.message}</p>
        ) : null}
      </div>

      <DepartmentField
        locked={existing?.department_locked ?? false}
        register={register("department_id")}
      />

      <div>
        <label htmlFor="availability" className="block text-sm font-medium">
          Availability for collaboration
        </label>
        <select id="availability" className={FIELD_CLASS} {...register("availability")}>
          <option value="available">Available</option>
          <option value="limited">Limited</option>
          <option value="unavailable">Unavailable</option>
        </select>
      </div>

      <div>
        <label htmlFor="bio" className="block text-sm font-medium">
          About your research
        </label>
        <textarea id="bio" rows={3} className={FIELD_CLASS} {...register("bio")} />
      </div>

      <div>
        <label htmlFor="link" className="block text-sm font-medium">
          Profile link (optional)
        </label>
        <input
          id="link"
          type="url"
          placeholder="https://example.com/you"
          className={FIELD_CLASS}
          {...register("link")}
        />
        {errors.link ? <p className="mt-1 text-xs text-red-700">{errors.link.message}</p> : null}
      </div>

      <p className="text-xs text-ink-muted">
        Saving submits your profile to your department&apos;s research coordinator for verification.
      </p>

      <button type="submit" disabled={isSubmitting} className={SUBMIT_CLASS}>
        {isSubmitting ? "Saving…" : submitLabel}
      </button>
    </form>
  );
}

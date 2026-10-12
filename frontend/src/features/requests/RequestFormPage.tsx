import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { z } from "zod";

import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { SkeletonList } from "@/components/ui/Skeleton";
import { toApiError } from "@/lib/api/errors";

import { fetchRecipients, submitRequest } from "./api";
import { CATEGORY_OPTIONS, roleLabel } from "./labels";

const schema = z.object({
  recipient_id: z.string().min(1, "Choose who this is for"),
  subject: z.string().trim().min(1, "A subject is required").max(200),
  body: z.string().trim().min(1, "Say what you are asking for").max(10000),
  category: z.enum(["academic", "facility", "funding", "administrative", "other"]),
});

type FormValues = z.infer<typeof schema>;

const FIELD = "mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm";

/**
 * Put a request to a named person above you.
 *
 * The recipient list comes from the server, built by the same filter the
 * submit enforces, so this form cannot offer somebody the submit would
 * refuse. There is no free-text recipient and no "everyone" option: a
 * request travels upward, to one person, which is what keeps it from being
 * the general messaging route nudges deliberately refused to be.
 */
export function RequestFormPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const { data: people, isPending } = useQuery({
    queryKey: ["request-recipients"],
    queryFn: fetchRecipients,
  });

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { recipient_id: "", subject: "", body: "", category: "academic" },
  });

  const submit = handleSubmit(async (values) => {
    setError(null);
    try {
      const saved = await submitRequest({
        recipient_id: values.recipient_id,
        subject: values.subject,
        body: values.body,
        category: values.category,
      });
      await queryClient.invalidateQueries({ queryKey: ["requests"] });
      void navigate(`/requests/${saved.id}`, { replace: true });
    } catch (caught) {
      setError(toApiError(caught).message);
    }
  });

  if (isPending) return <SkeletonList rows={3} />;

  // An empty list is a real answer, not a failure: an administrator is at
  // the top of the institution and addresses nobody.
  if (!people || people.length === 0) {
    return (
      <EmptyState
        title="There is nobody for you to put a request to"
        description="A request travels upward. You are already at the top of the chain, or your account has no department set."
        actionLabel="Back to your requests"
        actionTo="/me/requests"
      />
    );
  }

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader
        title="Make a request"
        description="It goes to one named person above you, and only the two of you can read it."
      />

      <form onSubmit={(event) => void submit(event)} className="space-y-5" noValidate>
        <div>
          <label htmlFor="recipient_id" className="block text-sm font-medium">
            Who is this for?
          </label>
          <select id="recipient_id" className={FIELD} {...register("recipient_id")}>
            <option value="">Choose a person</option>
            {people.map((person) => (
              <option key={person.id} value={person.id}>
                {person.full_name} ({person.registration_number}) · {roleLabel(person.role)}
                {person.department_name ? ` · ${person.department_name}` : ""}
              </option>
            ))}
          </select>
          {errors.recipient_id ? (
            <p className="mt-1 text-xs text-red-700">{errors.recipient_id.message}</p>
          ) : null}
        </div>

        <div>
          <label htmlFor="category" className="block text-sm font-medium">
            What is it about?
          </label>
          <select id="category" className={FIELD} {...register("category")}>
            {CATEGORY_OPTIONS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="subject" className="block text-sm font-medium">
            Subject
          </label>
          <input
            id="subject"
            className={FIELD}
            placeholder="Approval needed for my project submission"
            {...register("subject")}
          />
          {errors.subject ? (
            <p className="mt-1 text-xs text-red-700">{errors.subject.message}</p>
          ) : null}
        </div>

        <div>
          <label htmlFor="body" className="block text-sm font-medium">
            What are you asking for?
          </label>
          <textarea id="body" rows={7} className={FIELD} {...register("body")} />
          {errors.body ? <p className="mt-1 text-xs text-red-700">{errors.body.message}</p> : null}
          <p className="mt-1 text-xs text-ink-muted">You can attach a document once it is sent.</p>
        </div>

        {error ? <p className="text-sm text-red-700">{error}</p> : null}

        <div className="flex items-center gap-3">
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Sending…" : "Send the request"}
          </Button>
          <Button variant="secondary" onClick={() => void navigate("/me/requests")}>
            Cancel
          </Button>
        </div>
      </form>
    </div>
  );
}

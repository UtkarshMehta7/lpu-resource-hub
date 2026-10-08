import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Button, ButtonLink } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { SkeletonList } from "@/components/ui/Skeleton";
import { StatusPill } from "@/components/ui/StatusPill";
import { Uid } from "@/components/ui/Uid";
import { useAuth } from "@/features/auth/authContext";
import { toApiError } from "@/lib/api/errors";

import { decidePatent, deletePatent, fetchPatent, movePatentStatus } from "./api";
import {
  BEFORE_THE_OFFICE,
  DATE_LABEL,
  DISCLOSURE_WARNING,
  NOTE_REQUIRED,
  NUMBER_LABEL,
  officeLabel,
  STATUS_ACTION,
  STATUS_LABEL,
  STATUS_TONE,
  VERIFICATION_LABEL,
  VERIFICATION_TONE,
} from "./labels";
import type { PatentStatus } from "./types";

const FIELD = "mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm";
const CAN_REVIEW = new Set(["research_coordinator", "admin"]);

export function PatentDetailPage() {
  const { patentId = "" } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [moving, setMoving] = useState<PatentStatus | null>(null);
  const [on, setOn] = useState("");
  const [number, setNumber] = useState("");
  const [moveNote, setMoveNote] = useState("");
  const [note, setNote] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: patent, isPending } = useQuery({
    queryKey: ["patent", patentId],
    queryFn: () => fetchPatent(patentId),
  });

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["patent", patentId] });
    await queryClient.invalidateQueries({ queryKey: ["patent-review-queue"] });
  };

  const move = useMutation({
    mutationFn: () =>
      movePatentStatus(patentId, {
        status: moving as PatentStatus,
        on: on || null,
        number: number || null,
        note: moveNote || null,
      }),
    onSuccess: async () => {
      setMoving(null);
      setOn("");
      setNumber("");
      setMoveNote("");
      setError(null);
      await refresh();
    },
    onError: (caught) => setError(toApiError(caught).message),
  });

  const decide = useMutation({
    mutationFn: (approved: boolean) => decidePatent(patentId, approved, note || undefined),
    onSuccess: async () => {
      setNote("");
      setError(null);
      await refresh();
    },
    onError: (caught) => setError(toApiError(caught).message),
  });

  const remove = useMutation({
    mutationFn: () => deletePatent(patentId),
    onSuccess: () => navigate("/patents"),
  });

  if (isPending) return <SkeletonList rows={4} />;
  if (!patent) return <p className="text-sm text-ink-muted">Patent not found.</p>;

  const isCreator = user?.id === patent.created_by;
  const canReview =
    user !== null && CAN_REVIEW.has(user.role) && patent.verification_status === "pending";
  const canDelete = isCreator || user?.role === "admin";

  return (
    <div className="space-y-8">
      <header>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{patent.title}</h1>
          <div className="flex shrink-0 gap-2">
            <StatusPill tone={STATUS_TONE[patent.status]}>{STATUS_LABEL[patent.status]}</StatusPill>
            <StatusPill tone={VERIFICATION_TONE[patent.verification_status]}>
              {VERIFICATION_LABEL[patent.verification_status]}
            </StatusPill>
          </div>
        </div>
        <p className="mt-2 text-sm text-ink-muted">
          {officeLabel(patent.jurisdiction)}
          {patent.reference ? ` · ${patent.reference}` : ""}
          {patent.filing_date ? ` · filed ${patent.filing_date}` : " · not filed yet"}
          {patent.assignee ? ` · assigned to ${patent.assignee}` : ""}
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {isCreator ? (
            <ButtonLink to={`/patents/${patent.id}/edit`} variant="secondary" size="sm">
              Edit
            </ButtonLink>
          ) : null}
          {canDelete ? (
            <Button variant="danger" size="sm" onClick={() => setConfirming(true)}>
              Delete
            </Button>
          ) : null}
        </div>
      </header>

      {patent.public_disclosure_date ? (
        <p
          role="alert"
          className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900"
        >
          <strong>Made public on {patent.public_disclosure_date}</strong>
          {patent.public_disclosure_note ? ` — ${patent.public_disclosure_note}.` : "."}{" "}
          {DISCLOSURE_WARNING}
        </p>
      ) : null}

      {patent.status === "declined" && patent.assessment_note ? (
        <p className="rounded-md border border-line bg-canvas px-4 py-3 text-sm">
          <strong>Not taken forward</strong>
          {patent.assessed_by_name ? ` by ${patent.assessed_by_name}` : ""}:{" "}
          {patent.assessment_note}
        </p>
      ) : null}

      {patent.verification_status === "rejected" && patent.verification_note ? (
        <p className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900">
          Returned by {patent.verified_by_name}: {patent.verification_note}
        </p>
      ) : null}

      {patent.abstract ? (
        <section>
          <h2 className="text-base font-semibold">Abstract</h2>
          <p className="mt-2 whitespace-pre-line text-sm text-ink-muted">{patent.abstract}</p>
        </section>
      ) : null}

      {patent.problem_statement || patent.novelty || patent.known_prior_art ? (
        <section>
          <h2 className="text-base font-semibold">The invention</h2>
          <dl className="mt-2 space-y-3 text-sm">
            <Prose label="What problem it solves" value={patent.problem_statement} />
            <Prose label="What is new about it" value={patent.novelty} />
            <Prose label="Prior art the inventor knows of" value={patent.known_prior_art} />
            <Prose label="Who would use it" value={patent.commercial_potential} />
            <Prose label="Funding source" value={patent.funding_source} />
          </dl>
        </section>
      ) : null}

      <section>
        <h2 className="text-base font-semibold">Inventors</h2>
        <ol className="mt-2 space-y-1">
          {patent.inventors.map((inventor) => (
            <li key={inventor.inventor_order} className="flex items-center gap-2 text-sm">
              <span className="w-5 text-xs text-ink-muted">{inventor.inventor_order}.</span>
              {inventor.user_id ? (
                <Link
                  to={`/researchers/${inventor.user_id}`}
                  className="text-brand-700 hover:underline"
                >
                  {inventor.name}
                </Link>
              ) : (
                <span>{inventor.name}</span>
              )}
              {inventor.registration_number ? <Uid value={inventor.registration_number} /> : null}
            </li>
          ))}
        </ol>
      </section>

      <section>
        <h2 className="text-base font-semibold">
          {BEFORE_THE_OFFICE.has(patent.status) ? "Where it has got to" : "At the patent office"}
        </h2>
        {BEFORE_THE_OFFICE.has(patent.status) ? (
          <p className="mt-2 text-sm text-ink-muted">
            Nothing has been lodged with an office yet, so there are no numbers to show. The IP cell
            decides whether the university files it.
          </p>
        ) : (
          <dl className="mt-2 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
            <Row label="Application number" value={patent.application_number} />
            <Row label="Filing date" value={patent.filing_date} />
            <Row label="Publication number" value={patent.publication_number} />
            <Row label="Publication date" value={patent.publication_date} />
            <Row label="Grant number" value={patent.grant_number} />
            <Row label="Grant date" value={patent.grant_date} />
          </dl>
        )}

        {patent.next_statuses.length > 0 ? (
          <div className="mt-4 rounded-card border border-line bg-surface p-4">
            <h3 className="text-sm font-semibold">What happens next</h3>
            <p className="mt-1 text-xs text-ink-muted">
              The backend returns the moves <em>you</em> may make from here, so this never offers a
              step it would then refuse.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {patent.next_statuses.map((next) => (
                <Button
                  key={next}
                  size="sm"
                  variant={moving === next ? "primary" : "secondary"}
                  onClick={() => setMoving(moving === next ? null : next)}
                >
                  {STATUS_ACTION[next]}
                </Button>
              ))}
            </div>
            {moving ? (
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                {NOTE_REQUIRED.has(moving) || BEFORE_THE_OFFICE.has(moving) ? (
                  <div className="sm:col-span-2">
                    <label htmlFor="move-note" className="block text-sm font-medium">
                      Reason {NOTE_REQUIRED.has(moving) ? "" : "(optional)"}
                    </label>
                    <textarea
                      id="move-note"
                      rows={2}
                      className={FIELD}
                      value={moveNote}
                      onChange={(event) => setMoveNote(event.target.value)}
                      placeholder={
                        NOTE_REQUIRED.has(moving)
                          ? "Why the university will not take this forward."
                          : "What you checked, or what is still needed."
                      }
                    />
                    {NOTE_REQUIRED.has(moving) ? (
                      <p className="mt-1 text-xs text-ink-muted">
                        Required. &ldquo;No&rdquo; without a reason is what stops the next person
                        disclosing at all.
                      </p>
                    ) : null}
                  </div>
                ) : null}
                {DATE_LABEL[moving] ? (
                  <div>
                    <label htmlFor="move-on" className="block text-sm font-medium">
                      {DATE_LABEL[moving]}
                    </label>
                    <input
                      id="move-on"
                      type="date"
                      className={FIELD}
                      value={on}
                      onChange={(event) => setOn(event.target.value)}
                    />
                  </div>
                ) : null}
                {NUMBER_LABEL[moving] ? (
                  <div>
                    <label htmlFor="move-number" className="block text-sm font-medium">
                      {NUMBER_LABEL[moving]}
                    </label>
                    <input
                      id="move-number"
                      className={FIELD}
                      value={number}
                      onChange={(event) => setNumber(event.target.value)}
                    />
                  </div>
                ) : null}
                <div className="sm:col-span-2">
                  <Button onClick={() => move.mutate()} disabled={move.isPending}>
                    {STATUS_ACTION[moving]}
                  </Button>
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
      </section>

      {canReview ? (
        <section className="rounded-card border border-brand-200 bg-brand-50 p-4">
          <h2 className="text-base font-semibold">Is this record right?</h2>
          <p className="mt-1 text-sm text-ink-muted">
            You are checking the numbers, dates and inventors against the office&rsquo;s own record
            &mdash; not whether the invention deserves a patent, which only the office decides.
          </p>
          <label htmlFor="decision-note" className="mt-3 block text-sm font-medium">
            Note
          </label>
          <textarea
            id="decision-note"
            rows={2}
            className={FIELD}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="What you checked, or what needs fixing."
          />
          <div className="mt-3 flex gap-2">
            <Button onClick={() => decide.mutate(true)} disabled={decide.isPending}>
              Verify
            </Button>
            <Button
              variant="secondary"
              onClick={() => decide.mutate(false)}
              disabled={decide.isPending}
            >
              Send back
            </Button>
          </div>
        </section>
      ) : null}

      {patent.verification_status === "verified" && patent.verified_by_name ? (
        <p className="text-sm text-ink-muted">
          Checked by {patent.verified_by_name}
          {patent.verification_note ? ` — ${patent.verification_note}` : ""}.
        </p>
      ) : null}

      {patent.projects.length > 0 ? (
        <section>
          <h2 className="text-base font-semibold">Projects</h2>
          <ul className="mt-2 space-y-1 text-sm">
            {patent.projects.map((project) => (
              <li key={project.id}>
                <Link to={`/projects/${project.id}`} className="text-brand-700 hover:underline">
                  {project.title}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {error ? <p className="text-sm text-red-700">{error}</p> : null}

      <ConfirmDialog
        open={confirming}
        title="Delete patent?"
        description="This permanently removes the record and its inventor list."
        confirmLabel="Delete"
        onConfirm={() => {
          setConfirming(false);
          remove.mutate();
        }}
        onCancel={() => setConfirming(false)}
      />
    </div>
  );
}

function Prose({ label, value }: { label: string; value: string | null }) {
  if (!value) return null;
  return (
    <div>
      <dt className="font-medium">{label}</dt>
      <dd className="mt-0.5 whitespace-pre-line text-ink-muted">{value}</dd>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex justify-between gap-3 border-b border-line py-1">
      <dt className="text-ink-muted">{label}</dt>
      <dd className="text-right">{value ?? "—"}</dd>
    </div>
  );
}

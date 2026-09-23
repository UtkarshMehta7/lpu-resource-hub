import { Link, Navigate } from "react-router-dom";

import { Crest, UNIVERSITY_NAME, UNIVERSITY_SHORT } from "@/components/layout/Brand";
import { useAuth } from "@/features/auth/authContext";

const AUDIENCES = [
  {
    role: "Students",
    line: "Find a supervisor, join a project, book lab time.",
    points: [
      "Search researchers by expertise, not by who you already know",
      "Apply to openings and watch the decision move in one place",
      "Get reminded before a deadline closes, not after",
    ],
  },
  {
    role: "Faculty",
    line: "Publish work, recruit help, share equipment.",
    points: [
      "Run projects through review and build a team",
      "Post openings and review applicants side by side",
      "Keep publications, collaborators and bookings together",
    ],
  },
  {
    role: "Coordinators & admins",
    line: "See the department, keep it healthy.",
    points: [
      "Verify researchers and review projects in one queue",
      "Approve equipment bookings without double-booking anyone",
      "Read department analytics scoped to exactly your remit",
    ],
  },
];

const CAPABILITIES = [
  {
    title: "Expertise you can actually search",
    body: "Full-text and typo-tolerant search across researcher profiles, projects and publications — plus a smart mode that matches meaning when the words differ.",
    to: "/search",
    action: "Try a search",
  },
  {
    title: "Projects and openings",
    body: "Faculty publish reviewed projects and student openings; students apply and track every application, with decisions recorded end to end.",
    to: "/opportunities",
    action: "Browse opportunities",
  },
  {
    title: "Labs and equipment",
    body: "A shared catalogue with a week-by-week calendar. Two people can never hold the same slot — the database itself refuses it.",
    to: "/facilities",
    action: "See facilities",
  },
  {
    title: "Funding, with reminders",
    body: "Calls in one list with their official source linked. Save one and you're reminded a week and a day before it closes.",
    to: "/funding",
    action: "View funding",
  },
  {
    title: "Recommendations that explain themselves",
    body: "Every suggestion shows the skills, research areas and wording it matched on. No black box, no invented reasons.",
    to: "/recommendations",
    action: "See your matches",
  },
  {
    title: "Oversight for the people responsible",
    body: "Verification and review queues, an append-only audit log, moderation, and analytics scoped to a coordinator's own department.",
    to: "/analytics",
    action: "View analytics",
  },
];

const STEPS = [
  {
    title: "Get an account",
    body: "Nobody signs themselves up. A coordinator sets up the faculty of their department, and faculty enrol their students — each with a one-time password to replace at first sign-in.",
  },
  {
    title: "Say what you work on",
    body: "Skills, research areas and a short profile. Three of each is enough for matching to start working.",
  },
  {
    title: "Get matched, get moving",
    body: "Openings, projects and collaborators surface with reasons attached — then apply, book, or send a request.",
  },
];

/** Signed-out landing page. Signed-in people go straight to their dashboard. */
export function HomePage() {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) return null;
  if (isAuthenticated) return <Navigate to="/dashboard" replace />;

  return (
    <div className="space-y-20">
      <section className="relative overflow-hidden rounded-card border border-brand-100 bg-gradient-to-br from-brand-50 via-surface to-surface px-6 py-14 text-center sm:px-10 sm:py-20">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-20 -top-24 size-72 rounded-full bg-brand-100/60 blur-3xl"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -bottom-28 -left-16 size-72 rounded-full bg-brand-200/40 blur-3xl"
        />
        <div className="relative mx-auto max-w-3xl">
          <div className="flex justify-center">
            <Crest className="size-24 rounded-full bg-white p-2 shadow-sm ring-1 ring-brand-100" />
          </div>
          <p className="mt-5 text-sm font-semibold uppercase tracking-wide text-brand-700">
            {UNIVERSITY_NAME}
          </p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-balance sm:text-5xl">
            Research Intelligence &amp; Collaboration Hub
          </h1>
          <p className="mt-5 text-base text-ink-muted sm:text-lg">
            Expertise, projects, lab equipment and funding across {UNIVERSITY_SHORT} departments —
            in one place, so students and researchers can actually find each other.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link
              to="/login"
              className="rounded-md bg-brand-700 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-brand-800"
            >
              Sign in with your registration number
            </Link>
          </div>
          <p className="mt-5 text-xs text-ink-muted">
            A prototype built for the {UNIVERSITY_SHORT} ecosystem. Every person, project and record
            you see is fictional demo data.
          </p>
        </div>
      </section>

      <section aria-labelledby="problem-heading" className="mx-auto max-w-3xl text-center">
        <h2 id="problem-heading" className="text-2xl font-semibold tracking-tight">
          Good work is invisible across department boundaries
        </h2>
        <p className="mt-4 text-ink-muted">
          A student who wants to work on sensing has no way to discover the lab two buildings away.
          Equipment sits idle because nobody outside its department knows it exists. Funding
          deadlines pass unnoticed. This platform makes each of those searchable, bookable and
          traceable.
        </p>
      </section>

      <section aria-labelledby="audiences-heading">
        <h2 id="audiences-heading" className="text-center text-2xl font-semibold tracking-tight">
          Built for everyone in the research chain
        </h2>
        <ul className="mt-8 grid gap-4 md:grid-cols-3">
          {AUDIENCES.map((audience) => (
            <li key={audience.role} className="rounded-card border border-line bg-surface p-6">
              <h3 className="text-base font-semibold">{audience.role}</h3>
              <p className="mt-1 text-sm text-brand-700">{audience.line}</p>
              <ul className="mt-4 space-y-2">
                {audience.points.map((point) => (
                  <li key={point} className="flex gap-2 text-sm text-ink-muted">
                    <span aria-hidden="true" className="mt-0.5 text-brand-600">
                      →
                    </span>
                    {point}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="capabilities-heading">
        <h2 id="capabilities-heading" className="text-center text-2xl font-semibold tracking-tight">
          What you can do here
        </h2>
        <ul className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {CAPABILITIES.map((capability) => (
            <li
              key={capability.title}
              className="flex flex-col rounded-card border border-line bg-surface p-5 transition hover:border-brand-200"
            >
              <h3 className="text-base font-semibold">{capability.title}</h3>
              <p className="mt-2 flex-1 text-sm text-ink-muted">{capability.body}</p>
              <Link
                to={capability.to}
                className="mt-4 text-sm font-medium text-brand-700 hover:underline"
              >
                {capability.action} →
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section
        aria-labelledby="how-heading"
        className="rounded-card bg-brand-50 px-6 py-12 sm:px-10"
      >
        <h2 id="how-heading" className="text-center text-2xl font-semibold tracking-tight">
          How it works
        </h2>
        <ol className="mx-auto mt-8 grid max-w-4xl gap-6 sm:grid-cols-3">
          {STEPS.map((step, index) => (
            <li key={step.title}>
              <span className="grid size-8 place-items-center rounded-full bg-brand-700 text-sm font-semibold text-white">
                {index + 1}
              </span>
              <h3 className="mt-3 text-base font-semibold">{step.title}</h3>
              <p className="mt-1 text-sm text-ink-muted">{step.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="rounded-card border border-line bg-surface px-6 py-12 text-center sm:px-10">
        <h2 className="text-2xl font-semibold tracking-tight">Ready to look around?</h2>
        <p className="mx-auto mt-3 max-w-xl text-sm text-ink-muted">
          Sign in with the registration number and temporary password your department gave you.
          Accounts are created for you — there is no sign-up.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <Link
            to="/login"
            className="rounded-md bg-brand-700 px-5 py-2.5 text-sm font-medium text-white hover:bg-brand-800"
          >
            Sign in
          </Link>
        </div>
      </section>
    </div>
  );
}

import { Link, Navigate } from "react-router-dom";

import { Monogram, UNIVERSITY_NAME, UNIVERSITY_SHORT } from "@/components/layout/Brand";
import { useAuth } from "@/features/auth/authContext";
import { BackendStatusCard } from "@/features/system-status/BackendStatusCard";

const CAPABILITIES = [
  {
    title: "Find the right people",
    body: "Search researcher expertise across departments, or ask in plain language and let the platform match meaning, not just keywords.",
    to: "/search",
    action: "Try a search",
  },
  {
    title: "Projects and openings",
    body: "Faculty publish reviewed research projects and student openings; students apply and track every application in one place.",
    to: "/opportunities",
    action: "Browse opportunities",
  },
  {
    title: "Labs and equipment",
    body: "A shared catalogue with a week-by-week booking calendar. Two people can never hold the same slot.",
    to: "/facilities",
    action: "See facilities",
  },
  {
    title: "Funding, with reminders",
    body: "Funding calls in one list. Save one and you're reminded a week and a day before it closes.",
    to: "/funding",
    action: "View funding calls",
  },
  {
    title: "Recommendations that explain themselves",
    body: "Every suggestion shows the skills, research areas and wording it matched on — no black box.",
    to: "/recommendations",
    action: "See your matches",
  },
  {
    title: "Work together",
    body: "Send a collaboration request to a researcher or an opted-in student, and keep the thread in your inbox.",
    to: "/collaborations",
    action: "Open requests",
  },
];

/** Signed-out landing page. Signed-in people go straight to their dashboard. */
export function HomePage() {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) return null;
  if (isAuthenticated) return <Navigate to="/dashboard" replace />;

  return (
    <div className="space-y-14">
      <section className="mx-auto max-w-3xl text-center">
        <div className="flex justify-center">
          <Monogram className="size-14 text-lg" />
        </div>
        <p className="mt-4 text-sm font-medium text-brand-700">{UNIVERSITY_NAME}</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
          Research Intelligence &amp; Collaboration Hub
        </h1>
        <p className="mt-4 text-base text-ink-muted">
          Expertise, projects, lab equipment and funding across {UNIVERSITY_SHORT} departments — in
          one place, so students and researchers can actually find each other.
        </p>
        <div className="mt-7 flex flex-wrap justify-center gap-3">
          <Link
            to="/register"
            className="rounded-md bg-brand-700 px-5 py-2.5 text-sm font-medium text-white hover:bg-brand-800"
          >
            Create an account
          </Link>
          <Link
            to="/login"
            className="rounded-md border border-line bg-surface px-5 py-2.5 text-sm font-medium hover:bg-canvas"
          >
            Log in
          </Link>
        </div>
        <p className="mt-4 text-xs text-ink-muted">
          A prototype built for the {UNIVERSITY_SHORT} ecosystem. Everything you see is fictional
          demo data.
        </p>
      </section>

      <section aria-labelledby="capabilities-heading">
        <h2 id="capabilities-heading" className="sr-only">
          What you can do here
        </h2>
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {CAPABILITIES.map((capability) => (
            <li
              key={capability.title}
              className="flex flex-col rounded-card border border-line bg-surface p-5"
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

      <section className="mx-auto max-w-3xl">
        <BackendStatusCard />
      </section>
    </div>
  );
}

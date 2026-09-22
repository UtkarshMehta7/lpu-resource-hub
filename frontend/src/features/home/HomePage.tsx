import { BackendStatusCard } from "@/features/system-status/BackendStatusCard";

const PLANNED_CAPABILITIES = [
  "Researcher profiles and a searchable expertise directory across departments",
  "Research projects and opportunities that students can browse and apply to",
  "Facility and equipment catalogue with a booking calendar",
  "Funding calls with deadline reminders",
  "Explainable, tag-based collaboration and research recommendations",
];

export function HomePage() {
  return (
    <div className="space-y-10">
      <section className="max-w-3xl">
        <p className="text-sm font-medium text-brand-700">
          Development status: Step 0 · Foundation
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">
          Make research expertise, projects and facilities discoverable.
        </h1>
        <p className="mt-4 text-ink-muted">
          Faculty expertise, ongoing projects and lab facilities are often invisible across
          department boundaries. This platform is being built to help students and researchers find
          each other, put equipment to use and stay ahead of funding deadlines.
        </p>
      </section>

      <BackendStatusCard />

      <section aria-labelledby="planned-heading">
        <h2 id="planned-heading" className="text-base font-semibold">
          Planned capabilities
        </h2>
        <p className="mt-1 text-sm text-ink-muted">
          Not yet implemented; delivered phase by phase.
        </p>
        <ul className="mt-4 grid gap-3 sm:grid-cols-2">
          {PLANNED_CAPABILITIES.map((item) => (
            <li
              key={item}
              className="rounded-card border border-line bg-surface px-4 py-3 text-sm text-ink-muted"
            >
              {item}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

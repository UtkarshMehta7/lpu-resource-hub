import { Crest, UNIVERSITY_NAME, UNIVERSITY_SHORT } from "@/components/layout/Brand";

import {
  FACILITIES,
  FIELD_STRENGTHS,
  HEADLINE_FIGURES,
  NIRF_RANKINGS,
  OPEN_ALEX_FIGURES,
  RETRIEVED,
  SOURCES,
  type Figure,
} from "./lpuResearch";

const WORKS_FORMAT = new Intl.NumberFormat("en-IN");

/** The widest bar fills the track; the rest are drawn in proportion to it. */
const BUSIEST_FIELD = Math.max(...FIELD_STRENGTHS.map((entry) => entry.works));

function FigureCard({ figure }: { figure: Figure }) {
  return (
    <li className="rounded-card border border-line bg-surface p-5">
      <p className="text-3xl font-semibold tracking-tight text-brand-700 tabular-nums">
        {figure.value}
      </p>
      <h3 className="mt-1 text-sm font-semibold">{figure.label}</h3>
      <p className="mt-1 text-xs text-ink-muted">{figure.note}</p>
    </li>
  );
}

/**
 * What research at this university actually looks like, before anyone signs
 * in. Every figure is published by LPU, by NIRF or by OpenAlex and is linked
 * to its source at the foot of the section -- none of it comes from this
 * prototype's demo data, and the two are kept visibly apart on purpose.
 */
export function ResearchShowcase() {
  return (
    <section aria-labelledby="research-heading" className="space-y-12">
      <div className="mx-auto max-w-3xl text-center">
        <p className="text-sm font-semibold uppercase tracking-wide text-brand-700">
          Research at {UNIVERSITY_SHORT}
        </p>
        <h2
          id="research-heading"
          className="mt-3 text-2xl font-semibold tracking-tight sm:text-3xl"
        >
          One of India&rsquo;s most productive research universities
        </h2>
        <p className="mt-4 text-ink-muted">
          {UNIVERSITY_NAME} publishes across engineering, computing, agriculture, medicine and the
          sciences at a scale few private universities in the country match &mdash; and four fifths
          of that output has come in the last five years. The figures below are published by the
          university and by independent indexes, and every one of them is linked to its source.
        </p>
      </div>

      <div>
        <h3 className="text-center text-sm font-semibold uppercase tracking-wide text-ink-muted">
          As published by the university
        </h3>
        <ul className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {HEADLINE_FIGURES.map((figure) => (
            <FigureCard key={figure.label} figure={figure} />
          ))}
        </ul>
      </div>

      <div className="rounded-card bg-brand-50 px-6 py-10 sm:px-10">
        <div className="mx-auto max-w-3xl text-center">
          <h3 className="text-xl font-semibold tracking-tight">
            Ranked 31st in the country, and 40th among research institutions
          </h3>
          <p className="mt-3 text-sm text-ink-muted">
            National Institutional Ranking Framework 2025, the tenth edition, against every
            institution in India &mdash; government and private alike.
          </p>
        </div>
        <ul className="mx-auto mt-8 grid max-w-4xl gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {NIRF_RANKINGS.map((ranking) => (
            <li
              key={ranking.discipline}
              className="flex items-baseline gap-3 rounded-md bg-surface px-4 py-3"
            >
              <span className="text-xl font-semibold tabular-nums text-brand-700">
                #{ranking.rank}
              </span>
              <span className="text-sm text-ink-muted">{ranking.discipline}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="grid gap-8 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <h3 className="text-lg font-semibold tracking-tight">Where the work actually is</h3>
          <p className="mt-2 text-sm text-ink-muted">
            Indexed works by field of research &mdash; counted, not claimed. It is the same question
            this platform asks of a department, asked of the whole university.
          </p>
          <ul className="mt-6 space-y-3">
            {FIELD_STRENGTHS.map((entry) => (
              <li key={entry.field}>
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-sm">{entry.field}</span>
                  <span className="text-sm font-semibold tabular-nums text-ink-muted">
                    {WORKS_FORMAT.format(entry.works)}
                  </span>
                </div>
                <div
                  className="mt-1 h-2 overflow-hidden rounded-full bg-brand-50"
                  role="img"
                  aria-label={`${entry.field}: ${WORKS_FORMAT.format(entry.works)} indexed works`}
                >
                  <div
                    className="h-full rounded-full bg-brand-600"
                    style={{ width: `${Math.round((entry.works / BUSIEST_FIELD) * 100)}%` }}
                  />
                </div>
              </li>
            ))}
          </ul>
        </div>

        <div className="lg:col-span-2">
          <h3 className="text-lg font-semibold tracking-tight">Counted independently</h3>
          <p className="mt-2 text-sm text-ink-muted">
            OpenAlex indexes a wider corpus than Scopus, so its totals differ from the
            university&rsquo;s own. Both are shown rather than blended &mdash; a number that belongs
            to neither database is worse than two that each say where they came from.
          </p>
          <ul className="mt-6 grid gap-4 sm:grid-cols-2">
            {OPEN_ALEX_FIGURES.map((figure) => (
              <FigureCard key={figure.label} figure={figure} />
            ))}
          </ul>
        </div>
      </div>

      <div>
        <h3 className="text-lg font-semibold tracking-tight">Shared facilities behind it</h3>
        <ul className="mt-5 grid gap-4 md:grid-cols-3">
          {FACILITIES.map((facility) => (
            <li key={facility.name} className="rounded-card border border-line bg-surface p-5">
              <h4 className="text-base font-semibold">{facility.name}</h4>
              <p className="mt-2 text-sm text-ink-muted">{facility.body}</p>
            </li>
          ))}
        </ul>
      </div>

      <div className="rounded-card border border-line bg-surface px-6 py-6 text-sm">
        <div className="flex items-start gap-4">
          <Crest className="hidden size-12 shrink-0 rounded-full bg-white p-1 ring-1 ring-brand-100 sm:block" />
          <div>
            <h3 className="font-semibold">Where these figures come from</h3>
            <p className="mt-1 text-ink-muted">
              Read {RETRIEVED}. These are the university&rsquo;s own published figures and
              third-party index data &mdash; <strong>not</strong> records held in this prototype,
              whose people, projects and bookings are all fictional demo data.
            </p>
            <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1">
              {Object.values(SOURCES).map((source) => (
                <li key={source.url}>
                  <a
                    className="text-brand-700 hover:underline"
                    href={source.url}
                    target="_blank"
                    rel="noreferrer noopener"
                  >
                    {source.label} &rarr;
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}

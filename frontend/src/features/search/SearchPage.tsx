import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonList } from "@/components/ui/Skeleton";

import { searchLexical, searchSemantic, totalResults } from "./api";

type Mode = "smart" | "keyword";

const EXAMPLES = [
  "researchers working on soil moisture sensing",
  "projects about machine learning for crops",
  "funding for field trials",
];

/** One search box across researchers, projects, publications and openings. */
export function SearchPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const query = searchParams.get("q") ?? "";
  const mode: Mode = searchParams.get("mode") === "keyword" ? "keyword" : "smart";
  const [draft, setDraft] = useState(query);

  const { data, isPending, isError, isFetching } = useQuery({
    queryKey: ["search", mode, query],
    queryFn: () => (mode === "smart" ? searchSemantic(query) : searchLexical(query)),
    enabled: query.trim().length > 0,
  });

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const next = new URLSearchParams(searchParams);
    if (draft.trim()) next.set("q", draft.trim());
    else next.delete("q");
    setSearchParams(next);
  };

  const setMode = (next: Mode) => {
    const params = new URLSearchParams(searchParams);
    if (next === "keyword") params.set("mode", "keyword");
    else params.delete("mode");
    setSearchParams(params);
  };

  const count = totalResults(data);
  const semanticOff = mode === "smart" && data?.semantic_used === false;

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Search</h1>
      <p className="mt-1 text-sm text-ink-muted">
        Ask in plain language — smart search also matches work described in different words.
      </p>

      <form onSubmit={submit} className="mt-6">
        <label htmlFor="search-q" className="block text-sm font-medium">
          What are you looking for?
        </label>
        <div className="mt-1 flex flex-wrap gap-2">
          <input
            id="search-q"
            type="search"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="e.g. researchers working on soil moisture sensing"
            className="min-w-64 flex-1 rounded-md border border-line bg-surface px-3 py-2 text-sm"
          />
          <button
            type="submit"
            className="rounded-md bg-brand-700 px-4 py-2 text-sm font-medium text-white hover:bg-brand-800"
          >
            Search
          </button>
        </div>
      </form>

      <div className="mt-3 flex flex-wrap items-center gap-2" role="group" aria-label="Search mode">
        <button
          type="button"
          aria-pressed={mode === "smart"}
          onClick={() => setMode("smart")}
          className="rounded-md border border-line px-3 py-1.5 text-sm font-medium aria-pressed:bg-brand-700 aria-pressed:text-white"
        >
          Smart
        </button>
        <button
          type="button"
          aria-pressed={mode === "keyword"}
          onClick={() => setMode("keyword")}
          className="rounded-md border border-line px-3 py-1.5 text-sm font-medium aria-pressed:bg-brand-700 aria-pressed:text-white"
        >
          Keyword
        </button>
        <span className="text-xs text-ink-muted">
          {mode === "smart"
            ? "Finds related work even when the words differ."
            : "Matches the exact words you typed."}
        </span>
      </div>

      {semanticOff ? (
        <p className="mt-3 rounded-card border border-line bg-surface px-3 py-2 text-xs text-ink-muted">
          Smart search isn&apos;t available on this server, so these are keyword results.
        </p>
      ) : null}

      {!query ? (
        <div className="mt-8">
          <EmptyState title="Try a question" description="For example:">
            <ul className="mt-3 flex flex-wrap justify-center gap-2">
              {EXAMPLES.map((example) => (
                <li key={example}>
                  <button
                    type="button"
                    onClick={() => {
                      setDraft(example);
                      const next = new URLSearchParams(searchParams);
                      next.set("q", example);
                      setSearchParams(next);
                    }}
                    className="rounded-full border border-line bg-surface px-3 py-1 text-xs hover:bg-brand-50"
                  >
                    {example}
                  </button>
                </li>
              ))}
            </ul>
          </EmptyState>
        </div>
      ) : null}

      {query && isPending ? (
        <div className="mt-8">
          <SkeletonList rows={4} />
        </div>
      ) : null}
      {isError ? (
        <p role="alert" className="mt-8 text-sm text-red-700">
          Search failed. Try again in a moment.
        </p>
      ) : null}

      {data ? (
        <div className="mt-8">
          <p className="text-sm text-ink-muted" aria-live="polite">
            {count === 0 ? "No matches" : `${count} match${count === 1 ? "" : "es"}`} for “
            {data.query}”{isFetching ? " · updating…" : ""}
          </p>
          {count === 0 ? (
            <div className="mt-4">
              <EmptyState
                title="Nothing found"
                description={
                  mode === "smart"
                    ? "Try different words, or browse the directory."
                    : "Try smart search — it matches meaning, not just words."
                }
                actionLabel="Browse researchers"
                actionTo="/researchers"
              />
            </div>
          ) : null}

          <Section title="Researchers">
            {data.researchers.map((researcher) => (
              <Row
                key={researcher.user_id}
                to={`/researchers/${researcher.user_id}`}
                title={researcher.full_name}
                subtitle={researcher.designation}
              />
            ))}
          </Section>
          <Section title="Projects">
            {data.projects.map((project) => (
              <Row
                key={project.id}
                to={`/projects/${project.id}`}
                title={project.title}
                subtitle={`Led by ${project.owner_name}`}
              />
            ))}
          </Section>
          <Section title="Opportunities">
            {data.opportunities.map((opportunity) => (
              <Row
                key={opportunity.id}
                to={`/opportunities/${opportunity.id}`}
                title={opportunity.title}
                subtitle={`Closes ${opportunity.deadline}`}
              />
            ))}
          </Section>
          <Section title="Publications">
            {data.publications.map((publication) => (
              <Row
                key={publication.id}
                to={`/publications/${publication.id}`}
                title={publication.title}
                subtitle={[publication.venue, publication.year].filter(Boolean).join(" · ")}
              />
            ))}
          </Section>
        </div>
      ) : null}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode[] }) {
  if (children.length === 0) return null;
  return (
    <section className="mt-6">
      <h2 className="text-base font-semibold">{title}</h2>
      <ul className="mt-2 space-y-2">{children}</ul>
    </section>
  );
}

function Row({ to, title, subtitle }: { to: string; title: string; subtitle?: string }) {
  return (
    <li className="rounded-card border border-line bg-surface p-3">
      <Link to={to} className="text-sm font-medium hover:underline">
        {title}
      </Link>
      {subtitle ? <p className="text-xs text-ink-muted">{subtitle}</p> : null}
    </li>
  );
}

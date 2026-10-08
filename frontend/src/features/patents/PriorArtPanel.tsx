import { useMutation } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import { StatusPill } from "@/components/ui/StatusPill";

import { searchPriorArt } from "./api";
import { officeLabel, STATUS_LABEL, STATUS_TONE } from "./labels";

/**
 * Prior art for a patent being drafted.
 *
 * **The one thing this panel must never do is imply the world has been
 * searched.** No open API covers worldwide patents -- Espacenet, USPTO,
 * PatentsView, PATENTSCOPE and PQAI were each tested and each need a key --
 * so the honest shape is: show what we can actually check, and hand the
 * query to the registers that can check the rest. An empty result here means
 * "we found nothing in two open indexes", not "this is novel", and the
 * wording says exactly that.
 */
export function PriorArtPanel({
  title,
  abstract,
  excludeId,
}: {
  title: string;
  abstract?: string | null;
  excludeId?: string;
}) {
  const search = useMutation({
    mutationFn: () => searchPriorArt(title, abstract, excludeId),
  });
  const result = search.data;
  const ready = title.trim().length >= 3;

  return (
    <section className="rounded-card border border-line bg-surface p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-base font-semibold">Has this been done before?</h2>
          <p className="mt-1 max-w-xl text-sm text-ink-muted">
            Checks this register and the open research literature, then hands your title to the
            patent offices that can search their own collections.
          </p>
        </div>
        <Button onClick={() => search.mutate()} disabled={!ready || search.isPending}>
          {search.isPending ? "Checking…" : "Check prior art"}
        </Button>
      </div>

      {!ready ? (
        <p className="mt-4 text-sm text-ink-muted">Give the patent a title first.</p>
      ) : null}

      {search.isError ? (
        <p className="mt-4 text-sm text-red-700">
          The check could not be completed. The registry links below still work.
        </p>
      ) : null}

      {result ? (
        <div className="mt-6 space-y-6">
          <div>
            <h3 className="text-sm font-semibold">Already recorded here</h3>
            {result.similar_patents.length === 0 ? (
              <p className="mt-1 text-sm text-ink-muted">
                Nothing in this university&rsquo;s register looks like it.
              </p>
            ) : (
              <ul className="mt-2 space-y-2">
                {result.similar_patents.map((patent) => (
                  <li
                    key={patent.id}
                    className="flex flex-wrap items-baseline justify-between gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2"
                  >
                    <Link
                      to={`/patents/${patent.id}`}
                      className="text-sm font-medium text-brand-800 hover:underline"
                    >
                      {patent.title}
                    </Link>
                    <span className="flex items-center gap-2 text-xs text-ink-muted">
                      <StatusPill tone={STATUS_TONE[patent.status]}>
                        {STATUS_LABEL[patent.status]}
                      </StatusPill>
                      {officeLabel(patent.jurisdiction)} · {patent.score}% alike
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div>
            <h3 className="text-sm font-semibold">Published research that may count</h3>
            <p className="mt-1 text-sm text-ink-muted">
              A published paper is prior art exactly as another patent is, and it is what most often
              defeats a claim of novelty.
            </p>
            {result.literature_unavailable ? (
              <p className="mt-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                One of the literature indexes could not be reached, so this list is incomplete. Run
                the check again before relying on it.
              </p>
            ) : null}
            {result.related_works.length === 0 && !result.literature_unavailable ? (
              <p className="mt-2 text-sm text-ink-muted">
                Nothing close came back from OpenAlex or Crossref.
              </p>
            ) : (
              <ul className="mt-2 space-y-2">
                {result.related_works.map((work) => (
                  <li key={`${work.source}-${work.doi ?? work.title}`} className="text-sm">
                    {work.url ? (
                      <a
                        href={work.url}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="font-medium text-brand-700 hover:underline"
                      >
                        {work.title}
                      </a>
                    ) : (
                      <span className="font-medium">{work.title}</span>
                    )}
                    <span className="text-ink-muted">
                      {work.venue ? ` · ${work.venue}` : ""}
                      {work.year ? ` · ${work.year}` : ""} · {work.source}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="rounded-md bg-brand-50 px-4 py-4">
            <h3 className="text-sm font-semibold">
              This has <em>not</em> searched the world&rsquo;s patents
            </h3>
            <p className="mt-1 text-sm text-ink-muted">
              No patent office offers an open search anyone can call, so the worldwide check has to
              happen on their own sites. Your title is already in each link.
            </p>
            <ul className="mt-3 grid gap-2 sm:grid-cols-2">
              {result.registries.map((registry) => (
                <li key={registry.name}>
                  <a
                    href={registry.url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="block rounded-md bg-surface px-3 py-2 hover:ring-1 hover:ring-brand-200"
                  >
                    <span className="text-sm font-medium text-brand-700">{registry.name} →</span>
                    <span className="mt-0.5 block text-xs text-ink-muted">
                      {registry.description}
                    </span>
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}
    </section>
  );
}

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import {
  fetchPublications,
  PUB_TYPE_LABEL,
  type Publication,
  type PublicationFilters,
} from "./api";

export function PublicationItem({ publication }: { publication: Publication }) {
  return (
    <li className="rounded-card border border-line bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <Link
          to={`/publications/${publication.id}`}
          className="text-sm font-semibold hover:underline"
        >
          {publication.title}
        </Link>
        <span className="rounded-md border border-line px-2 py-1 text-xs text-ink-muted">
          {PUB_TYPE_LABEL[publication.pub_type]}
        </span>
      </div>
      <p className="mt-1 text-sm text-ink-muted">
        {publication.authors.map((a) => a.name).join(", ")}
      </p>
      <p className="mt-1 text-xs text-ink-muted">
        {[publication.venue, publication.year].filter(Boolean).join(" · ")}
      </p>
    </li>
  );
}

/** A compact "Publications" section for researcher and project detail pages. */
export function PublicationsSection({ filters }: { filters: PublicationFilters }) {
  const { data } = useQuery({
    queryKey: ["publications", filters],
    queryFn: () => fetchPublications(filters),
  });

  return (
    <section className="mt-8">
      <h2 className="text-base font-semibold">Publications</h2>
      {data && data.items.length > 0 ? (
        <ul className="mt-2 space-y-2">
          {data.items.map((publication) => (
            <PublicationItem key={publication.id} publication={publication} />
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-ink-muted">No publications yet.</p>
      )}
    </section>
  );
}

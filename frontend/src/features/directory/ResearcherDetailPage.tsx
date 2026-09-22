import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { StatusIndicator } from "@/components/ui/StatusIndicator";

import { fetchResearcher } from "./api";

const AVAILABILITY_LABEL = {
  available: "Available for collaboration",
  limited: "Limited availability",
  unavailable: "Not currently available",
} as const;

export function ResearcherDetailPage() {
  const { userId } = useParams<{ userId: string }>();
  const { data, isPending, isError } = useQuery({
    queryKey: ["researcher", userId],
    queryFn: () => fetchResearcher(userId ?? ""),
    enabled: Boolean(userId),
  });

  if (isPending) return <p className="text-sm text-ink-muted">Loading profile…</p>;

  if (isError || !data) {
    return (
      <div>
        <p role="alert" className="text-sm text-red-700">
          This researcher could not be found.
        </p>
        <Link
          to="/researchers"
          className="mt-3 inline-block text-sm text-brand-700 hover:underline"
        >
          Back to the directory
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl">
      <Link to="/researchers" className="text-sm text-brand-700 hover:underline">
        ← Directory
      </Link>

      <div className="mt-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{data.full_name}</h1>
          <p className="mt-1 text-sm text-ink-muted">{data.designation}</p>
        </div>
        {data.verification_status === "verified" ? (
          <StatusIndicator tone="success" label="Verified" />
        ) : null}
      </div>

      <p className="mt-3 text-sm text-ink-muted">{AVAILABILITY_LABEL[data.availability]}</p>

      {data.bio ? <p className="mt-6 text-sm">{data.bio}</p> : null}

      <TagSection title="Research areas" tags={data.research_areas} />
      <TagSection title="Skills" tags={data.skills} />

      {data.links && data.links.length > 0 ? (
        <section className="mt-8">
          <h2 className="text-base font-semibold">Links</h2>
          <ul className="mt-2 space-y-1">
            {data.links.map((link) => (
              <li key={link.url}>
                <a
                  href={link.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="text-sm text-brand-700 hover:underline"
                >
                  {link.label}
                </a>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <p className="mt-10 text-xs text-ink-muted">
        Projects and publications appear here in a later step.
      </p>
    </div>
  );
}

function TagSection({ title, tags }: { title: string; tags: string[] }) {
  if (tags.length === 0) return null;
  return (
    <section className="mt-8">
      <h2 className="text-base font-semibold">{title}</h2>
      <ul className="mt-2 flex flex-wrap gap-2">
        {tags.map((tag) => (
          <li
            key={tag}
            className="rounded-md border border-line bg-surface px-2 py-1 text-xs text-ink-muted"
          >
            {tag}
          </li>
        ))}
      </ul>
    </section>
  );
}

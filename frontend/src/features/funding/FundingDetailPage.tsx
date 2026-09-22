import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { SkeletonList } from "@/components/ui/Skeleton";
import { SaveButton } from "@/features/saved/SaveButton";
import { useNow } from "@/lib/useNow";

import { amountLabel, daysUntil, fetchFunding } from "./api";

export function FundingDetailPage() {
  const { fundingId = "" } = useParams<{ fundingId: string }>();
  const now = useNow();
  const {
    data: call,
    isPending,
    isError,
  } = useQuery({
    queryKey: ["funding-call", fundingId],
    queryFn: () => fetchFunding(fundingId),
  });

  if (isPending) return <SkeletonList rows={2} />;
  if (isError) {
    return (
      <p role="alert" className="text-sm text-red-700">
        Funding call not found.
      </p>
    );
  }

  const days = daysUntil(call.deadline, now);

  return (
    <div className="mx-auto max-w-3xl">
      <Link to="/funding" className="text-sm text-brand-700 hover:underline">
        ← Funding calls
      </Link>
      <p className="mt-2 text-xs text-ink-muted">
        {call.organization}
        {call.is_demo ? " · fictional demo call" : ""}
      </p>
      <h1 className="mt-1 text-2xl font-semibold tracking-tight">{call.title}</h1>
      <p className="mt-2 text-sm text-ink-muted">
        Deadline {call.deadline}
        {call.status === "open" && days !== null && days >= 0
          ? ` · ${days} day${days === 1 ? "" : "s"} left`
          : ` · ${call.status}`}
        {amountLabel(call) ? ` · ${amountLabel(call)}` : ""}
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <SaveButton type="funding" targetId={call.id} />
        {call.official_source_url ? (
          <a
            href={call.official_source_url}
            target="_blank"
            rel="noreferrer"
            className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm font-medium"
          >
            Official source ↗
          </a>
        ) : null}
      </div>

      <section className="mt-8">
        <h2 className="text-base font-semibold">About this call</h2>
        <p className="mt-2 whitespace-pre-line text-sm">{call.description}</p>
      </section>
      {call.eligibility ? (
        <section className="mt-6">
          <h2 className="text-base font-semibold">Eligibility</h2>
          <p className="mt-2 whitespace-pre-line text-sm">{call.eligibility}</p>
        </section>
      ) : null}
      {call.research_areas.length > 0 ? (
        <section className="mt-6">
          <h2 className="text-base font-semibold">Research areas</h2>
          <ul className="mt-2 flex flex-wrap gap-2">
            {call.research_areas.map((area) => (
              <li key={area} className="rounded-md border border-line px-2 py-1 text-xs">
                {area}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <p className="mt-8 text-xs text-ink-muted">
        Always check the official source before applying. Calls shown in this prototype may be
        fictional demo data.
      </p>
    </div>
  );
}

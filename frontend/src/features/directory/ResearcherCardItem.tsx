import { Link } from "react-router-dom";
import { Uid } from "@/components/ui/Uid";

import type { ResearcherCard } from "./api";

const AVAILABILITY_LABEL = {
  available: "Available",
  limited: "Limited availability",
  unavailable: "Not available",
} as const;

const MAX_TAGS = 4;

export function ResearcherCardItem({ researcher }: { researcher: ResearcherCard }) {
  const tags = [...researcher.research_areas, ...researcher.skills];
  const shown = tags.slice(0, MAX_TAGS);
  const remaining = tags.length - shown.length;

  return (
    <li className="rounded-card border border-line bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <Link
            to={`/researchers/${researcher.user_id}`}
            className="text-sm font-semibold hover:underline"
          >
            {researcher.full_name}
            <Uid value={researcher.registration_number} className="ml-2" />
          </Link>
          <p className="text-sm text-ink-muted">{researcher.designation}</p>
        </div>
        {researcher.verification_status === "verified" ? (
          <span className="rounded-md bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700">
            Verified
          </span>
        ) : null}
      </div>

      <p className="mt-2 text-xs text-ink-muted">{AVAILABILITY_LABEL[researcher.availability]}</p>

      {shown.length > 0 ? (
        <ul className="mt-3 flex flex-wrap gap-2">
          {shown.map((tag) => (
            <li
              key={tag}
              className="rounded-md border border-line px-2 py-1 text-xs text-ink-muted"
            >
              {tag}
            </li>
          ))}
          {remaining > 0 ? (
            <li className="px-2 py-1 text-xs text-ink-muted">+{remaining} more</li>
          ) : null}
        </ul>
      ) : null}
    </li>
  );
}

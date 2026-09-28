import { useQuery } from "@tanstack/react-query";

import { fetchImportHistory } from "./api";

/**
 * What this profile has pulled in, and when.
 *
 * An import writes to the publication register under somebody's name, so it
 * leaves a trail the person can see for themselves rather than only an
 * administrator reading an audit table.
 */

const FIELD_LABELS: Record<string, string> = {
  designation: "designation",
  bio: "biography",
  links: "links",
};

export function ImportHistory() {
  const { data: history } = useQuery({
    queryKey: ["import-history"],
    queryFn: fetchImportHistory,
  });

  if (!history || history.length === 0) return null;

  return (
    <div className="mt-4 border-t border-line pt-4">
      <h3 className="text-sm font-medium">Previous imports</h3>
      <ul className="mt-2 space-y-1.5">
        {history.map((entry) => (
          <li key={entry.id} className="text-xs text-ink-muted">
            <span className="font-medium text-ink">
              {new Date(entry.created_at).toLocaleDateString(undefined, {
                day: "numeric",
                month: "short",
                year: "numeric",
              })}
            </span>{" "}
            · {entry.works_found} found, {entry.works_imported} added
            {entry.works_already_known > 0 ? `, ${entry.works_already_known} already saved` : ""}
            {entry.applied_fields.length > 0
              ? ` · updated ${entry.applied_fields
                  .map((field) => FIELD_LABELS[field] ?? field)
                  .join(", ")}`
              : ""}
            {entry.orcid_id ? ` · ORCID ${entry.orcid_id}` : ""}
          </li>
        ))}
      </ul>
    </div>
  );
}

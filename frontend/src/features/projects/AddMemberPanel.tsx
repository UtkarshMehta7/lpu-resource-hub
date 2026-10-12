import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Uid } from "@/components/ui/Uid";
import { fetchDiscoverableStudents, fetchResearchers } from "@/features/directory/api";
import { toApiError } from "@/lib/api/errors";

import { addMember } from "./api";

const FIELD =
  "mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm " +
  "focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500";

interface Candidate {
  user_id: string;
  full_name: string;
  registration_number: string;
  department_name: string | null;
  detail: string;
}

/**
 * Put somebody on the team without waiting for them to apply.
 *
 * Two ways onto a project, and only one of them existed in the interface.
 * Accepting an application is how a stranger joins; this is how the lead adds
 * the colleague or the student they already work with, and
 * `POST /projects/{id}/members` had been built, enforced and left unreachable
 * since projects shipped -- the same shape as `/admin/accounts/new`.
 *
 * Both lookups go through the directory's own endpoints, so a student who has
 * not opted in to being discovered is not surfaced here either. That is the
 * student opt-in doing its job rather than a gap: they can still apply, and
 * accepting that is the other route onto the team.
 */
export function AddMemberPanel({
  projectId,
  memberIds,
  onAdded,
}: {
  projectId: string;
  memberIds: string[];
  onAdded: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [role, setRole] = useState("Research assistant");
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState<string | null>(null);

  const term = q.trim();
  const { data, isFetching } = useQuery({
    queryKey: ["project-member-candidates", term],
    queryFn: async (): Promise<Candidate[]> => {
      const [researchers, students] = await Promise.all([
        fetchResearchers({ q: term }),
        // A student list is the point of this for most projects, and it is a
        // separate endpoint with a separate permission; failing the whole
        // search because one of the two is unavailable would hide the other.
        fetchDiscoverableStudents({ q: term }).catch(() => ({ items: [] })),
      ]);
      return [
        ...researchers.items.map((r) => ({
          user_id: r.user_id,
          full_name: r.full_name,
          registration_number: r.registration_number,
          department_name: r.department_name,
          detail: r.designation,
        })),
        ...students.items.map((s) => ({
          user_id: s.user_id,
          full_name: s.full_name,
          registration_number: s.registration_number,
          department_name: s.department_name,
          detail: `${s.program}, year ${s.year}`,
        })),
      ];
    },
    enabled: open && term.length > 1,
  });

  // Somebody already on the team is not a candidate, and offering them is how
  // a picker ends up proposing what the submit would refuse -- the rule the
  // facility-custodian candidate list holds.
  const candidates = (data ?? []).filter((c) => !memberIds.includes(c.user_id));

  async function add(candidate: Candidate): Promise<void> {
    setError(null);
    setAdding(candidate.user_id);
    try {
      await addMember(projectId, candidate.user_id, role.trim() || "Member");
      setQ("");
      onAdded();
    } catch (caught) {
      setError(toApiError(caught).message);
    } finally {
      setAdding(null);
    }
  }

  if (!open) {
    return (
      <Button variant="secondary" size="sm" className="mt-3" onClick={() => setOpen(true)}>
        Add someone to the team
      </Button>
    );
  }

  return (
    <div className="mt-3 rounded-card border border-line bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Add someone to the team</h3>
        <button
          type="button"
          className="text-xs text-ink-muted hover:underline"
          onClick={() => {
            setOpen(false);
            setQ("");
            setError(null);
          }}
        >
          Cancel
        </button>
      </div>
      <p className="mt-1 text-xs text-ink-muted">
        They join the project and its team chat straight away. To have people apply instead, post an
        opening under Hiring.
      </p>

      <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_14rem]">
        <div>
          <label htmlFor="member-q" className="block text-sm font-medium">
            Find a person
          </label>
          <input
            id="member-q"
            type="search"
            value={q}
            onChange={(event) => setQ(event.target.value)}
            placeholder="Name or registration number"
            className={FIELD}
          />
        </div>
        <div>
          <label htmlFor="member-role" className="block text-sm font-medium">
            Role on this project
          </label>
          <input
            id="member-role"
            value={role}
            maxLength={100}
            onChange={(event) => setRole(event.target.value)}
            className={FIELD}
          />
        </div>
      </div>

      {error ? <p className="mt-2 text-sm text-red-700">{error}</p> : null}

      {term.length > 1 ? (
        <ul className="mt-3 divide-y divide-line rounded-card border border-line">
          {candidates.length === 0 ? (
            <li className="px-3 py-2 text-sm text-ink-muted">
              {isFetching
                ? "Searching…"
                : "Nobody matches, or everybody who does is already on the team."}
            </li>
          ) : (
            candidates.map((candidate) => (
              <li
                key={candidate.user_id}
                className="flex flex-wrap items-center justify-between gap-2 px-3 py-2"
              >
                <span className="min-w-0 text-sm">
                  {candidate.full_name} <Uid value={candidate.registration_number} />
                  <span className="ml-1 text-xs text-ink-muted">
                    {candidate.detail}
                    {candidate.department_name ? ` · ${candidate.department_name}` : ""}
                  </span>
                </span>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={adding !== null}
                  onClick={() => void add(candidate)}
                >
                  {adding === candidate.user_id ? "Adding…" : "Add"}
                </Button>
              </li>
            ))
          )}
        </ul>
      ) : null}
    </div>
  );
}

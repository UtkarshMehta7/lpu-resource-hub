import { useState } from "react";

import { fetchResearchers, type ResearcherCard } from "@/features/directory/api";

import { newAuthorRow, type AuthorRow } from "./authors";

const FIELD = "w-full rounded-md border border-line bg-surface px-3 py-1.5 text-sm";

/** Ordered author list: platform researchers or external names, reorderable. */
export function AuthorListEditor({
  rows,
  onChange,
}: {
  rows: AuthorRow[];
  onChange: (rows: AuthorRow[]) => void;
}) {
  const update = (key: string, patch: Partial<AuthorRow>) =>
    onChange(rows.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  const move = (index: number, delta: number) => {
    const target = index + delta;
    if (target < 0 || target >= rows.length) return;
    const next = [...rows];
    const [moved] = next.splice(index, 1);
    if (moved) next.splice(target, 0, moved);
    onChange(next);
  };

  return (
    <fieldset>
      <legend className="block text-sm font-medium">Authors (in order)</legend>
      <ol className="mt-2 space-y-2">
        {rows.map((row, index) => (
          <li key={row.key} className="rounded-md border border-line bg-surface p-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="w-5 text-xs text-ink-muted">{index + 1}.</span>
              <select
                aria-label={`Author ${index + 1} type`}
                value={row.kind}
                onChange={(event) =>
                  update(row.key, {
                    kind: event.target.value as AuthorRow["kind"],
                    userId: null,
                    name: "",
                  })
                }
                className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
              >
                <option value="user">Researcher on the platform</option>
                <option value="external">External author</option>
              </select>
              <div className="min-w-48 flex-1">
                {row.kind === "external" ? (
                  <input
                    aria-label={`Author ${index + 1} name`}
                    value={row.name}
                    placeholder="Full name"
                    onChange={(event) => update(row.key, { name: event.target.value })}
                    className={FIELD}
                  />
                ) : row.userId ? (
                  <span className="text-sm">
                    {row.name}{" "}
                    <button
                      type="button"
                      className="text-xs text-brand-700 hover:underline"
                      onClick={() => update(row.key, { userId: null, name: "" })}
                    >
                      change
                    </button>
                  </span>
                ) : (
                  <ResearcherSearch
                    label={`Author ${index + 1} researcher`}
                    onPick={(r) => update(row.key, { userId: r.user_id, name: r.full_name })}
                  />
                )}
              </div>
              <button
                type="button"
                aria-label={`Move author ${index + 1} up`}
                disabled={index === 0}
                onClick={() => move(index, -1)}
                className="px-1 text-sm disabled:opacity-30"
              >
                ↑
              </button>
              <button
                type="button"
                aria-label={`Move author ${index + 1} down`}
                disabled={index === rows.length - 1}
                onClick={() => move(index, 1)}
                className="px-1 text-sm disabled:opacity-30"
              >
                ↓
              </button>
              <button
                type="button"
                aria-label={`Remove author ${index + 1}`}
                onClick={() => onChange(rows.filter((r) => r.key !== row.key))}
                className="px-1 text-sm text-red-700"
              >
                ✕
              </button>
            </div>
          </li>
        ))}
      </ol>
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          onClick={() => onChange([...rows, newAuthorRow("user")])}
          className="rounded-md border border-line bg-surface px-2 py-1 text-xs"
        >
          + Researcher
        </button>
        <button
          type="button"
          onClick={() => onChange([...rows, newAuthorRow("external")])}
          className="rounded-md border border-line bg-surface px-2 py-1 text-xs"
        >
          + External author
        </button>
      </div>
    </fieldset>
  );
}

function ResearcherSearch({
  label,
  onPick,
}: {
  label: string;
  onPick: (researcher: ResearcherCard) => void;
}) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<ResearcherCard[]>([]);

  const search = async (value: string) => {
    setQ(value);
    if (value.trim().length < 2) {
      setResults([]);
      return;
    }
    const page = await fetchResearchers({ q: value, page_size: 5 });
    setResults(page.items);
  };

  return (
    <div className="relative">
      <input
        aria-label={label}
        value={q}
        placeholder="Search researchers by name"
        onChange={(event) => void search(event.target.value)}
        className={FIELD}
      />
      {results.length > 0 ? (
        <ul className="absolute z-10 mt-1 w-full rounded-md border border-line bg-surface shadow">
          {results.map((researcher) => (
            <li key={researcher.user_id}>
              <button
                type="button"
                onClick={() => onPick(researcher)}
                className="block w-full px-3 py-1.5 text-left text-sm hover:bg-brand-50"
              >
                {researcher.full_name}
                <span className="text-xs text-ink-muted"> · {researcher.designation}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

import { useEffect, useState, type ReactNode } from "react";

export interface TagOption {
  id: string;
  name: string;
}

interface TagPickerProps {
  label: string;
  description?: string;
  /** Called with the debounced query; an alias hit resolves to its canonical tag. */
  search: (query: string) => Promise<TagOption[]>;
  selected: TagOption[];
  onAdd: (option: TagOption) => void;
  onRemove: (id: string) => void;
  /** Per-selection control, e.g. a proficiency select or an expertise checkbox. */
  renderSelectedExtra?: (option: TagOption) => ReactNode;
}

const DEBOUNCE_MS = 250;

/** Autocomplete multi-select over the shared taxonomy. */
export function TagPicker({
  label,
  description,
  search,
  selected,
  onAdd,
  onRemove,
  renderSelectedExtra,
}: TagPickerProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<TagOption[]>([]);
  const [isSearching, setIsSearching] = useState(false);

  useEffect(() => {
    let cancelled = false;
    // Flipped inside the timer, not in the effect body: the request only
    // actually starts after the debounce.
    const timer = setTimeout(() => {
      setIsSearching(true);
      search(query)
        .then((options) => {
          if (!cancelled) setResults(options);
        })
        .catch(() => {
          if (!cancelled) setResults([]);
        })
        .finally(() => {
          if (!cancelled) setIsSearching(false);
        });
    }, DEBOUNCE_MS);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query, search]);

  const selectedIds = new Set(selected.map((option) => option.id));
  const available = results.filter((option) => !selectedIds.has(option.id));

  return (
    <div>
      <label htmlFor={`tagpicker-${label}`} className="block text-sm font-medium">
        {label}
      </label>
      {description ? <p className="mt-1 text-xs text-ink-muted">{description}</p> : null}

      <input
        id={`tagpicker-${label}`}
        type="search"
        value={query}
        placeholder="Type to search…"
        onChange={(event) => setQuery(event.target.value)}
        className="mt-2 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm"
      />

      {query && available.length > 0 ? (
        <ul className="mt-2 max-h-48 divide-y divide-line overflow-y-auto rounded-md border border-line bg-surface">
          {available.map((option) => (
            <li key={option.id}>
              <button
                type="button"
                onClick={() => {
                  onAdd(option);
                  setQuery("");
                }}
                className="w-full px-3 py-2 text-left text-sm hover:bg-canvas"
              >
                {option.name}
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {query && !isSearching && available.length === 0 ? (
        <p className="mt-2 text-xs text-ink-muted">
          No matches. Coordinators can add new tags; you can suggest one from your profile.
        </p>
      ) : null}

      <ul className="mt-3 space-y-2">
        {selected.map((option) => (
          <li
            key={option.id}
            className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-line bg-surface px-3 py-2"
          >
            <span className="text-sm font-medium">{option.name}</span>
            <span className="flex items-center gap-3">
              {renderSelectedExtra ? renderSelectedExtra(option) : null}
              <button
                type="button"
                onClick={() => onRemove(option.id)}
                aria-label={`Remove ${option.name}`}
                className="rounded-md border border-line px-2 py-1 text-xs font-medium hover:bg-canvas"
              >
                Remove
              </button>
            </span>
          </li>
        ))}
      </ul>

      {selected.length === 0 ? (
        <p className="mt-2 text-xs text-ink-muted">Nothing selected yet.</p>
      ) : null}
    </div>
  );
}

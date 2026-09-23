import { useState } from "react";

/**
 * Click the heading, correct it, press Save.
 *
 * A lab's name is the thing most likely to be typed wrong and most likely to
 * need fixing later, so it is edited in place rather than behind a form on
 * another page. Shared by facilities and equipment, which need exactly the
 * same gesture.
 */
export function EditableName({
  value,
  canEdit,
  isSaving,
  onSave,
  label,
}: {
  value: string;
  canEdit: boolean;
  isSaving: boolean;
  onSave: (next: string) => void;
  /** Names the thing for screen readers: "Rename Soil Lab". */
  label: string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);

  if (!canEdit) {
    return <h1 className="mt-2 text-2xl font-semibold tracking-tight">{value}</h1>;
  }

  if (!editing) {
    return (
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">{value}</h1>
        <button
          type="button"
          aria-label={`Rename ${value}`}
          onClick={() => {
            setDraft(value);
            setEditing(true);
          }}
          className="rounded-md border border-line bg-surface px-2 py-1 text-xs font-medium hover:bg-canvas"
        >
          Rename
        </button>
      </div>
    );
  }

  return (
    <form
      className="mt-2 flex flex-wrap items-center gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        const next = draft.trim();
        if (next && next !== value) onSave(next);
        setEditing(false);
      }}
    >
      <label className="sr-only" htmlFor="editable-name">
        {label}
      </label>
      <input
        id="editable-name"
        autoFocus
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        className="rounded-md border border-line bg-surface px-3 py-2 text-lg font-semibold"
      />
      <button
        type="submit"
        disabled={isSaving}
        className="rounded-md bg-brand-700 px-3 py-2 text-sm font-medium text-white hover:bg-brand-800 disabled:opacity-50"
      >
        {isSaving ? "Saving…" : "Save"}
      </button>
      <button
        type="button"
        onClick={() => setEditing(false)}
        className="text-sm font-medium text-ink-muted hover:underline"
      >
        Cancel
      </button>
    </form>
  );
}

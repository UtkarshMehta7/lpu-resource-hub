import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { StatusPill, type PillTone } from "@/components/ui/StatusPill";
import { toApiError } from "@/lib/api/errors";

import { applyProfileImport, previewProfileImport } from "./api";
import type { ImportPreview, ImportResult, ImportWorkCandidate, ImportWorkStatus } from "./types";

/**
 * Pull a researcher's profile and publication list in from the public
 * research sites.
 *
 * Nothing here writes on its own. The researcher looks themselves up, reads
 * what was found, unticks whatever is wrong, and only then imports -- because
 * an import that silently overwrote a bio or added a namesake's paper would
 * be much harder to undo than to prevent.
 */

const SOURCE_LABELS: Record<string, string> = {
  orcid: "ORCID",
  openalex: "OpenAlex",
  crossref: "Crossref",
  semantic_scholar: "Semantic Scholar",
};

const STATUS_VIEW: Record<ImportWorkStatus, { tone: PillTone; label: string }> = {
  new: { tone: "positive", label: "New" },
  already_in_register: { tone: "neutral", label: "Already saved" },
  possible_duplicate: { tone: "warning", label: "Possible duplicate" },
  not_importable: { tone: "negative", label: "Can't import" },
};

const FIELD_LABELS: Record<string, string> = {
  designation: "Designation",
  bio: "Biography",
  links: "Links",
};

const METRIC_LABELS: Record<string, string> = {
  works_count: "Works",
  cited_by_count: "Citations",
  h_index: "h-index",
};

function sourceName(source: string): string {
  return SOURCE_LABELS[source] ?? source;
}

export function ImportProfilePanel({
  onImported,
  linkedOrcid,
}: {
  onImported: () => Promise<void> | void;
  linkedOrcid: string | null;
}) {
  const [orcid, setOrcid] = useState(linkedOrcid ?? "");
  const [name, setName] = useState("");
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [chosenWorks, setChosenWorks] = useState<Set<string>>(new Set());
  const [chosenFields, setChosenFields] = useState<Set<string>>(new Set());

  const lookup = { orcid: orcid.trim() || null, name: name.trim() || null };

  const previewMutation = useMutation({
    mutationFn: () => previewProfileImport(lookup),
    onSuccess: (data) => {
      setError(null);
      setResult(null);
      setPreview(data);
      // Everything genuinely new starts ticked; anything that needs a human
      // decision -- a possible duplicate -- starts unticked.
      setChosenWorks(new Set(data.works.filter((w) => w.status === "new").map((w) => w.key)));
      setChosenFields(new Set(data.fields.filter((f) => f.changed).map((f) => f.field)));
    },
    onError: (err: unknown) => {
      setPreview(null);
      setError(toApiError(err).message);
    },
  });

  const applyMutation = useMutation({
    mutationFn: () =>
      applyProfileImport({
        ...lookup,
        fields: [...chosenFields],
        work_keys: [...chosenWorks],
      }),
    onSuccess: async (data) => {
      setError(null);
      setResult(data);
      setPreview(null);
      await onImported();
    },
    onError: (err: unknown) => setError(toApiError(err).message),
  });

  function toggle(set: Set<string>, key: string, update: (next: Set<string>) => void) {
    const next = new Set(set);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    update(next);
  }

  const busy = previewMutation.isPending || applyMutation.isPending;
  const canLookUp = (orcid.trim() || name.trim()) !== "" && !busy;

  return (
    <section className="mt-8 rounded-lg border border-line bg-surface p-4">
      <h2 className="text-base font-semibold">Import from research sites</h2>
      <p className="mt-1 text-sm text-ink-muted">
        Bring your details and publication list in from ORCID, OpenAlex, Crossref and Semantic
        Scholar. You choose what is added — nothing is saved until you press Import.
      </p>

      {linkedOrcid ? (
        <p className="mt-2 text-xs text-ink-muted">
          Linked ORCID iD: <span className="font-medium text-ink">{linkedOrcid}</span>
        </p>
      ) : null}

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div className="text-sm">
          <label htmlFor="import-orcid" className="font-medium">
            ORCID iD
          </label>
          <input
            id="import-orcid"
            aria-describedby="import-orcid-hint"
            value={orcid}
            onChange={(event) => setOrcid(event.target.value)}
            placeholder="0000-0002-1825-0097"
            className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm"
          />
          <p id="import-orcid-hint" className="mt-1 text-xs text-ink-muted">
            The reliable way to find you. Free to register at orcid.org.
          </p>
        </div>
        <div className="text-sm">
          <label htmlFor="import-name" className="font-medium">
            or your published name
          </label>
          <input
            id="import-name"
            aria-describedby="import-name-hint"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="A. Sharma"
            className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm"
          />
          <p id="import-name-hint" className="mt-1 text-xs text-ink-muted">
            Used only if you have no ORCID iD. Check the results carefully — names are shared.
          </p>
        </div>
      </div>

      <div className="mt-3 flex items-center gap-3">
        <Button onClick={() => previewMutation.mutate()} disabled={!canLookUp}>
          {previewMutation.isPending ? "Looking you up…" : "Look me up"}
        </Button>
        {busy ? (
          <span className="text-xs text-ink-muted">Reading the sources, this takes a moment…</span>
        ) : null}
      </div>

      {error ? (
        <p
          role="alert"
          className="mt-3 rounded-md border border-red-200 bg-red-50 p-2 text-sm text-red-800"
        >
          {error}
        </p>
      ) : null}

      {result ? <ImportSummary result={result} /> : null}

      {preview ? (
        <PreviewPanel
          preview={preview}
          chosenWorks={chosenWorks}
          chosenFields={chosenFields}
          onToggleWork={(key) => toggle(chosenWorks, key, setChosenWorks)}
          onToggleField={(key) => toggle(chosenFields, key, setChosenFields)}
          onApply={() => applyMutation.mutate()}
          applying={applyMutation.isPending}
        />
      ) : null}
    </section>
  );
}

function ImportSummary({ result }: { result: ImportResult }) {
  return (
    <div className="mt-3 rounded-md border border-green-200 bg-green-50 p-3 text-sm text-green-900">
      <p className="font-medium">
        Imported {result.works_imported} publication{result.works_imported === 1 ? "" : "s"}.
      </p>
      <ul className="mt-1 space-y-0.5 text-xs">
        {result.applied_fields.length > 0 ? (
          <li>Updated: {result.applied_fields.map((f) => FIELD_LABELS[f] ?? f).join(", ")}.</li>
        ) : null}
        {result.works_skipped > 0 ? (
          <li>{result.works_skipped} skipped — already in the register.</li>
        ) : null}
        {result.works_failed > 0 ? (
          <li>{result.works_failed} could not be saved. You can add those by hand.</li>
        ) : null}
      </ul>
    </div>
  );
}

function PreviewPanel({
  preview,
  chosenWorks,
  chosenFields,
  onToggleWork,
  onToggleField,
  onApply,
  applying,
}: {
  preview: ImportPreview;
  chosenWorks: Set<string>;
  chosenFields: Set<string>;
  onToggleWork: (key: string) => void;
  onToggleField: (key: string) => void;
  onApply: () => void;
  applying: boolean;
}) {
  const chosenCount = chosenWorks.size + chosenFields.size;
  return (
    <div className="mt-4 border-t border-line pt-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <p className="text-sm font-medium">
            {preview.full_name ?? "Record found"}
            {preview.affiliation ? (
              <span className="font-normal text-ink-muted"> · {preview.affiliation}</span>
            ) : null}
          </p>
          <p className="mt-0.5 text-xs text-ink-muted">
            Found in {preview.sources_used.map(sourceName).join(", ") || "no source"} ·{" "}
            {preview.new_count} new, {preview.known_count} already saved
          </p>
        </div>
        {Object.entries(preview.metrics).length > 0 ? (
          <ul className="flex gap-3 text-xs text-ink-muted">
            {Object.entries(preview.metrics).map(([key, value]) => (
              <li key={key}>
                <span className="font-medium text-ink">{value}</span> {METRIC_LABELS[key] ?? key}
              </li>
            ))}
          </ul>
        ) : null}
      </div>

      {Object.keys(preview.source_errors).length > 0 ? (
        <ul className="mt-2 space-y-1 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
          {Object.entries(preview.source_errors).map(([source, message]) => (
            <li key={source}>
              <span className="font-medium">{sourceName(source)}:</span> {message}
            </li>
          ))}
        </ul>
      ) : null}

      {preview.fields.some((f) => f.changed) ? (
        <fieldset className="mt-4">
          <legend className="text-sm font-medium">Profile details</legend>
          <ul className="mt-2 space-y-2">
            {preview.fields
              .filter((field) => field.changed)
              .map((field) => (
                <li key={field.field} className="rounded-md border border-line p-2">
                  <label className="flex items-start gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={chosenFields.has(field.field)}
                      onChange={() => onToggleField(field.field)}
                      className="mt-1"
                    />
                    <span className="min-w-0">
                      <span className="font-medium">
                        {FIELD_LABELS[field.field] ?? field.field}
                      </span>
                      <span className="mt-0.5 block break-words text-xs text-ink-muted">
                        {field.current ? (
                          <>
                            <s>{field.current}</s>{" "}
                          </>
                        ) : null}
                        {field.incoming}
                      </span>
                    </span>
                  </label>
                </li>
              ))}
          </ul>
        </fieldset>
      ) : null}

      {preview.topics.length > 0 ? (
        <div className="mt-4">
          <p className="text-sm font-medium">Subjects these sites associate with you</p>
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {preview.topics.map((topic) => (
              <li key={topic}>
                <StatusPill tone="info">{topic}</StatusPill>
              </li>
            ))}
          </ul>
          <p className="mt-1.5 text-xs text-ink-muted">
            Suggestions only — add the ones you want under Skills and research areas.
          </p>
        </div>
      ) : null}

      <fieldset className="mt-4">
        <legend className="text-sm font-medium">Publications ({preview.works.length} found)</legend>
        <ul className="mt-2 space-y-2">
          {preview.works.map((work) => (
            <WorkRow
              key={work.key}
              work={work}
              checked={chosenWorks.has(work.key)}
              onToggle={() => onToggleWork(work.key)}
            />
          ))}
        </ul>
      </fieldset>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button onClick={onApply} disabled={applying || chosenCount === 0}>
          {applying ? "Importing…" : `Import ${chosenCount} selected`}
        </Button>
        <span className="text-xs text-ink-muted">
          Only ticked items are saved. Nothing else on your profile is touched.
        </span>
      </div>
    </div>
  );
}

function WorkRow({
  work,
  checked,
  onToggle,
}: {
  work: ImportWorkCandidate;
  checked: boolean;
  onToggle: () => void;
}) {
  const view = STATUS_VIEW[work.status];
  return (
    <li className="rounded-md border border-line p-2">
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          checked={checked}
          disabled={!work.importable}
          onChange={onToggle}
          className="mt-1"
          aria-label={`Import ${work.title}`}
        />
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-baseline gap-2">
            <span className="font-medium">{work.title}</span>
            <StatusPill tone={view.tone}>{view.label}</StatusPill>
          </span>
          <span className="mt-0.5 block text-xs text-ink-muted">
            {[work.year, work.venue].filter(Boolean).join(" · ")}
            {work.doi ? ` · doi:${work.doi}` : ""}
          </span>
          {work.authors.length > 0 ? (
            <span className="mt-0.5 block truncate text-xs text-ink-muted">
              {work.authors.slice(0, 6).join(", ")}
              {work.authors.length > 6 ? ` +${work.authors.length - 6} more` : ""}
            </span>
          ) : null}
          {work.reason ? (
            <span className="mt-0.5 block text-xs text-ink-muted">{work.reason}</span>
          ) : null}
          <span className="mt-0.5 block text-xs text-ink-muted">
            From {work.sources.map(sourceName).join(", ")}
          </span>
        </span>
      </label>
    </li>
  );
}

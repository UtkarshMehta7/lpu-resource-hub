import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { SkeletonList } from "@/components/ui/Skeleton";
import { toApiError } from "@/lib/api/errors";

import {
  downloadInstitutionalReport,
  fetchAcademicYears,
  fetchInstitutionalReport,
  type ReportSection,
  type ReportTable,
} from "./api";

/**
 * The institutional research report for one academic year.
 *
 * Shown on screen and downloadable as CSV or PDF — all three from the same
 * aggregation on the server, so a figure here is the figure in the file.
 *
 * Each table carries the rule it was produced under. A number handed to
 * somebody without its definition invites the wrong reading, and a report is
 * exactly the artefact that outlives the conversation explaining it.
 */
export function InstitutionalReportPage() {
  const [year, setYear] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: years } = useQuery({
    queryKey: ["academic-years"],
    queryFn: fetchAcademicYears,
  });

  const selected = year ?? years?.find((option) => option.is_current)?.label ?? null;

  const { data: report, isPending } = useQuery({
    queryKey: ["institutional-report", selected],
    queryFn: () => fetchInstitutionalReport(selected as string),
    enabled: selected !== null,
  });

  const download = useMutation({
    mutationFn: (format: "csv" | "pdf") => downloadInstitutionalReport(selected as string, format),
    onSuccess: () => setError(null),
    onError: (err: unknown) => setError(toApiError(err).message),
  });

  return (
    <div>
      <PageHeader
        title="Institutional research report"
        description="A full academic year of research activity. Every figure is counted from the platform's own records when you load the page — nothing is estimated or carried forward."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <label htmlFor="academic-year" className="sr-only">
              Academic year
            </label>
            <select
              id="academic-year"
              value={selected ?? ""}
              onChange={(event) => setYear(event.target.value)}
              className="rounded-md border border-line bg-surface px-3 py-2 text-sm"
            >
              {years?.map((option) => (
                <option key={option.label} value={option.label}>
                  {option.label}
                  {option.is_current ? " (current)" : ""}
                </option>
              ))}
            </select>
            <Button
              variant="secondary"
              disabled={!selected || download.isPending}
              onClick={() => download.mutate("csv")}
            >
              Download CSV
            </Button>
            <Button
              disabled={!selected || download.isPending}
              onClick={() => download.mutate("pdf")}
            >
              {download.isPending ? "Preparing…" : "Download PDF"}
            </Button>
          </div>
        }
      />

      {error ? (
        <p role="alert" className="mb-4 text-sm text-red-700">
          {error}
        </p>
      ) : null}

      {isPending || !report ? (
        <SkeletonList rows={4} />
      ) : report.sections.length === 0 ? (
        <EmptyState
          title="Nothing recorded for this year"
          description="No research activity falls inside this academic year yet."
        />
      ) : (
        <>
          <p className="mb-6 text-xs text-ink-muted">
            {report.academic_year} · {report.period_start} to {report.period_end} · covering{" "}
            {report.scope} · generated {report.generated_at}
          </p>
          <div className="space-y-8">
            {report.sections.map((section) => (
              <Section key={section.title} section={section} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function Section({ section }: { section: ReportSection }) {
  return (
    <section>
      <h2 className="text-base font-semibold">{section.title}</h2>

      {section.summary.length > 0 ? (
        <dl className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {section.summary.map(([label, value]) => (
            <div key={label} className="rounded-card border border-line bg-surface p-3">
              <dt className="text-xs text-ink-muted">{label}</dt>
              <dd className="mt-0.5 text-lg font-semibold tabular-nums">{value}</dd>
            </div>
          ))}
        </dl>
      ) : null}

      {section.tables.map((table) => (
        <DataTable key={table.title} table={table} />
      ))}
    </section>
  );
}

function DataTable({ table }: { table: ReportTable }) {
  return (
    <div className="mt-5">
      <h3 className="text-sm font-medium">{table.title}</h3>
      {table.definition ? (
        <p className="mt-0.5 text-xs text-ink-muted">{table.definition}</p>
      ) : null}
      {table.rows.length === 0 ? (
        <p className="mt-2 text-sm text-ink-muted">No records in this period.</p>
      ) : (
        <div className="mt-2 overflow-x-auto rounded-card border border-line bg-surface">
          <table className="w-full text-sm">
            <caption className="sr-only">{table.title}</caption>
            <thead>
              <tr className="border-b border-line text-left">
                {table.columns.map((column, index) => (
                  <th
                    key={column}
                    scope="col"
                    className={`px-3 py-2 text-xs font-semibold ${index === 0 ? "" : "text-right"}`}
                  >
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {table.rows.map((row) => (
                <tr key={row.join("|")} className="border-b border-line last:border-0">
                  {row.map((cell, index) => (
                    <td
                      key={`${row.join("|")}-${index}`}
                      className={`px-3 py-2 ${index === 0 ? "" : "text-right tabular-nums"}`}
                    >
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

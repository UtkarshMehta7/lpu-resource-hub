# The institutional research report

A full academic year of research activity, on screen and as a file.

`GET /api/v1/analytics/institutional-report?academic_year=2025-26`
`GET /api/v1/analytics/institutional-report/export?format=pdf|csv`

## Academic years, not calendar years

An academic year runs from the configured start month to the day before the
same month the following year. With the default (July), **2025-26** means
**1 July 2025 to 30 June 2026** inclusive.

`ACADEMIC_YEAR_START_MONTH` is configuration rather than a constant, because
it is the one thing that genuinely differs between institutions.

Labels are parsed strictly. `2025-26`, `2025-2026` and `2024–25` (en dash,
which word processors produce) are accepted. **`2025-27` is refused** — it is
a typo, not a two-year period, and silently reinterpreting it would put the
wrong dates on a signed report.

## One aggregation, three renderings

The JSON response, the CSV and the PDF are produced from the same
`InstitutionalReport` structure. There is no second aggregation that could
drift, so a figure on screen **is** the figure in the file.

## Sections

| Section | Contents |
|---|---|
| People | Researchers, verified proportion, research students |
| Research projects | Projects by status, completed in year, milestones due, on-time rate, outstanding milestones by risk |
| Publications | Total and attributable counts; by department, year, type and venue |
| Collaboration | Cross-department rate with its exclusions |
| Research opportunities | Application outcomes and success rate; opportunity funnel |
| Facilities and equipment | Equipment utilisation from approved bookings |
| Funding | Funding calls by recorded interest |

Every table carries the rule it was produced under, rendered **with** the
table rather than left in documentation nobody opens beside the figure. The
PDF closes with a "How to read this report" page restating the definitions
that most invite misreading.

Metric definitions are in [analytics.md](analytics.md).

## Nothing is estimated

Every figure is counted from real rows at the moment the report runs. Nothing
is extrapolated, defaulted or carried over from a previous run. Where a
metric cannot be computed — no decided applications, no qualifying
collaborations — it reads **"not applicable"** rather than `0`, because zero
is a claim and absence is not.

## Formats

- **PDF** via reportlab: pure Python wheels, no system libraries, so it
  renders on the deployed container exactly as it does locally.
- **CSV** with a UTF-8 BOM so Excel opens it in the right encoding. Blocks are
  separated by blank lines and each names itself, so the file is readable in a
  spreadsheet without a legend.

XLSX is not offered. The CSV carries the same data, and a spreadsheet format
would add a runtime dependency for presentation only.

## Access

`Permission.ANALYTICS_READ` — research coordinators and administrators. A
coordinator's report covers their department; an administrator's covers the
institution, and the report states which. Students and faculty receive 403 on
**both** the JSON and the export, asserted by test: the file is the same data,
so hiding the download button is not the control.

## Known limitations

- **Publication dates.** A bibliographic record carries a year, not a date, so
  a publication is placed in an academic year by its year overlapping the
  period. A paper published in, say, March 2026 cannot be distinguished from
  one published in September 2026 by the data available.
- **"Completed during the year"** uses `updated_at`, the closest thing to a
  completion timestamp the projects table records.
- **Milestone risk is a snapshot**, not a year-long measure. Stated beside the
  table.
- There is no per-run history: the report is recomputed each time rather than
  archived. Export the file to keep a copy.

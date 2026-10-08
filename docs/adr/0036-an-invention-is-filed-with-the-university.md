# ADR 0036: An invention is filed WITH the university, not only recorded after

- **Status:** Accepted
- **Date:** 2026-10-08
- **Amends:** ADR 0035

## Context

ADR 0035 built the patent register and described `status` as "what the patent
office did". That was the second half of the story.

The half it left out is the one that decides whether a patent ever exists. An
inventor discloses an invention to the university's IP cell; the cell assesses
patentability and commercial merit; the university decides to file, or declines
and says why. Only then does an office have an opinion about anything. A
platform that can only record what has *already* been filed is useful to the
people who least need help.

## Decision

### One record, one pipeline

Four stages go in front of `FILED`:

```
disclosed → under_assessment → approved_to_file → filed → published → granted → lapsed
                 │                                   └→ rejected / withdrawn
                 ├→ disclosed        (sent back for more detail)
                 └→ declined         (terminal, and must carry a reason)
```

`filing_date` becomes nullable, because nothing inside the university has one:
the office issues it. A CHECK keeps the two halves honest — everything before
the office has no filing date, everything from `filed` onwards has one.

**Not a separate disclosures table.** That was the obvious alternative and it
splits one invention across two rows, which immediately raises the question of
which row owns the inventor list, the abstract and the project links. It is also
not how the field models it: a technology-transfer office keeps one invention
record moving through one pipeline. The entry point is chosen by a boolean on
create — `already_filed` — which selects between exactly two starting stages and
is not a `status` field by the back door.

### Two actors, checked in the right order

The university's half belongs to the IP cell; the office's half belongs to the
inventor, because they are the one who hears from the office. The transition
table is keyed by `(from, to)` and holds the set of actors allowed to make the
move — the same shape the milestones module uses.

A move that **does not exist** is `409` whoever asks. A move that exists but
belongs to **somebody else** is `403`. Checked in that order, because deciding
the second first would tell an inventor that `granted → disclosed` is merely
above their pay grade rather than impossible.

### The fields an assessor actually reads

Three questions rather than one description box — the problem, the inventive
step, and the prior art the inventor already knows of. Declaring known art is a
duty in most jurisdictions, and concealing it can invalidate a granted patent.
Plus the funding source, because public money carries ownership and reporting
obligations the IP cell must know about before it files.

And above all, **`public_disclosure_date`**. A paper, poster, thesis or
demonstration before filing is the commonest way a university loses patent
rights outright. It is captured at disclosure, shown to the assessor, and
flagged in the interface — with wording that sends the question to the IP cell
rather than pretending to give legal advice, because grace periods differ
sharply between offices and this platform is not qualified to say which applies.

### A docket, because people say it out loud

`LPU/IDF/2026/0007`, allocated per calendar year from the highest already issued.
Deleting a record leaves a gap rather than letting the next one reuse its
number: a reference that has ever been quoted must never point at a different
invention. A unique index is the real guard; two disclosures in the same second
collide and the loser retries.

### Declining requires a reason

Enforced in the service and as a CHECK. "No" with no reason is what stops the
next person disclosing at all, which costs the university far more than any
single refused application.

## Rejected

- **A separate `invention_disclosures` table.** Splits one invention across two
  records and duplicates the inventor list. See above.
- **Deriving the stage from the dates.** A grant date implies a grant, the way a
  milestone's risk is derived (ADR 0026) — but no date distinguishes DECLINED,
  REJECTED, WITHDRAWN or LAPSED from one another. A rule that answers four of ten
  states is worse than no rule.
- **Folding assessment into `verification_status`.** They answer different
  questions: "should we file this" is not "are these numbers right". A granted
  patent can still be entered wrongly, and a well-recorded disclosure can still
  be one the university declines.

## Consequences

- Students can put an invention to the university rather than only record one
  somebody else filed, which is what the permission was opened up for.
- The prior-art check now runs at the moment it is most useful — while the
  disclosure is being written, before anything is filed.
- The IP cell's queue carries two kinds of waiting in one place: disclosures to
  assess and records to check. Splitting them would have meant two pages to
  forget to look at.
- Migration 0033's CHECK constraints compare `status::text` rather than the enum
  literals, because PostgreSQL refuses a literal whose value was added by an
  `ALTER TYPE` in the same uncommitted transaction. That is what keeps the whole
  pipeline in one migration instead of two.

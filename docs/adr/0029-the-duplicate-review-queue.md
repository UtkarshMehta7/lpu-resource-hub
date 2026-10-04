# ADR 0029: Reviewing duplicate publications, and why a merge deletes

- **Status:** Accepted
- **Date:** 2026-10-04

## Context

The importer de-duplicates what it brings in (ADR 0025,
`docs/publication-deduplication.md`), and that measurement now sits at F1 =
1.00 on a labelled fixture. It does nothing about duplicates that are already
stored, which arrive by routes no importer can intercept:

- two researchers each add the same paper by hand;
- somebody types a paper in, and an import later brings the same paper
  carrying its DOI;
- a title is re-entered with different punctuation or a dropped subtitle.

`merge.py` already held two thresholds, and only one of them was used:

```
TITLE_MATCH_THRESHOLD   = 92.0   # the importer merges, unattended
TITLE_SUGGEST_THRESHOLD = 84.0   # written for this, never wired up
```

84 is the floor: below it nothing is worth raising. There is deliberately **no
ceiling**, and the first draft of this ADR got that wrong — it said anything
above 92 had "already been merged on the way in". That is only true of records
the importer saw in the *same* pass. A paper typed in by hand and the same
paper imported a month later are two stored rows that no import-time merge
could have caught, and they score 100. The demo data proves it: both seeded
pairs score exactly 100 and belong in the queue.

So 92 governs the importer's licence to act unattended; 84 governs when to ask
a person. They are answers to different questions, not two edges of one band.

## Decisions

### A merge deletes the losing record, and does not leave a tombstone

The obvious design is a `merged_into_id` column on `publications`: hide the
row, keep it for reversal. It was rejected.

Publications are read in **fifteen places across eight modules** — listings,
search, hybrid search, recommendations, analytics, the institutional report,
reports, imports. A hidden-row flag has to be honoured by every one of them.
One missed query is a ghost publication that still answers a search or still
counts towards a figure, and it fails silently — exactly the class of bug this
codebase keeps paying for.

So a merge snapshots the losing record in full (metadata, author slots in
order, project links) onto the review row, carries what it holds onto the
survivor, and deletes it. A deleted row cannot be missed by a query it was
never excluded from, and the snapshot is what makes the merge reversible
anyway, so the tombstone bought nothing the snapshot did not.

The cost is honest and stated: an undo recreates the record with a **new id**,
so a link saved to the old one will not resolve. Everything else returns.

### The pair is the unit, and the database enforces it

`publication_duplicates` stores `publication_a_id < publication_b_id` under a
unique constraint and a CHECK, so the same pair cannot be queued twice —
the same reasoning as `collaborations` (ADR 0023), where a duplicate is made
impossible in the database rather than guarded in a service somebody can
forget.

The columns are **nullable with `ON DELETE SET NULL`**. A merge deletes one
side and an outright deletion may remove either, and the decision has to stay
readable afterwards. NULLs are distinct in a unique constraint, which is what
lets a decided row keep its place without blocking a later pair.

### A decided pair is never resurrected by a later scan

If "these are different works" came back next week as an open item, the queue
would never empty and people would stop reading it. A scan refreshes the score
of pairs still awaiting review and leaves every decided pair alone.

### A merge must name its survivor

`keep_id` is required. Choosing by date or by completeness would silently
discard the better-described record some fraction of the time, and the
reviewer is looking at both records already.

### Scanning is a button, not a background job

Detection is O(n²) over stored publications. Blocking by normalised-title
prefix is what you would reach for at a hundred thousand records; at this
institution's scale it would be unmeasurable cleverness. More importantly a
reviewer wants a stable list to work down rather than one shifting under them,
so the scan is an explicit act and its result is reported.

### Its own permission, and its own resource path

`publication:deduplicate`, granted to `RESEARCH_COORDINATOR` and `ADMIN`.
Separate from `publication:create` because writing your own record and merging
somebody else's are different powers. A dean is **excluded deliberately**:
they read the institution's figures and change nothing, and a merge changes
the records behind the figures.

The endpoints live at `/publication-duplicates`, not
`/publications/duplicates`. The publications router registers
`/publications/{publication_id}` and FastAPI matches in registration order, so
the nested form was swallowed and `"duplicates"` was parsed as a UUID — found
by a test, not by reasoning. Mounting this router first would also have worked
and would have broken silently the day somebody reordered `app/main.py`. A
review row is not a publication anyway; it is a judgement about two of them.

## Consequences

- Migration `0027` adds one table. Its downgrade drops the `duplicate_status`
  enum by hand, because dropping a table does not drop its type — the omission
  that broke `0023` in CI.
- A new module's models must be added to `app/db/model_registry.py` or
  autogenerate produces an **empty migration**. It did, silently, first time.
- Four audited actions: `publication.duplicate_scan`,
  `publication.duplicate_merge`, `publication.duplicate_separate`,
  `publication.duplicate_ignore`, plus
  `publication.duplicate_merge_undone`.
- The detection rules are reused from `merge.py` rather than reimplemented, so
  the queue and the importer cannot develop separate opinions about what makes
  two records the same paper. The DOI veto in particular — two different DOIs
  are never the same work — holds in both.

## What was deliberately not done

No automatic merging at any threshold. The importer already merges what it is
certain about; everything else is a person's decision, and the point of the
queue is to make that decision cheap rather than to remove it.

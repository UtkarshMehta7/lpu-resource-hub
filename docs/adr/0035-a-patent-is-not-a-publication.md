# ADR 0035: A patent is not a publication

- **Status:** Accepted
- **Date:** 2026-10-08

## Context

The platform recorded publications and nothing else, while the university's
own headline figure is **3,200+ IPR granted**. The obvious cheap move was an
eighth member of `PublicationType`.

It is the wrong move, and not on taste:

* **Analytics counts `publications` with no type filter.** `institutional.py`,
  `insights.py`, publications-by-year and the co-authorship network all count
  the table whole, and nineteen modules read it. An eighth enum member would
  have folded patents into every publication figure on the platform, silently.
* **A patent has a lifecycle that runs for years.** Filed, published, granted,
  then lapsed, rejected or withdrawn. `publications` has no status column at
  all, because a paper does not change state after it appears.
* **The identifiers are different.** There is no DOI. There is an application
  number, a pre-grant publication number and a grant number, each meaningful
  only inside a jurisdiction. The de-duplication rules are built on the DOI --
  "two different DOIs are never the same work" -- and have nothing to say here.
* **It has an assignee.** Usually the university, sometimes a sponsor. It is
  the commercially important field and no publication has an equivalent.

## Decision

### Its own table, its own module, its own counts

`patents`, `patent_inventors`, `project_patents`, mirroring the publications
layout exactly where the two are genuinely alike -- an ordered list of people,
links to projects, a creator who may edit -- so they read alike where they are
alike and differently where they are not.

**Inventors, not authors.** On a patent that is a legal distinction rather
than a stylistic one: an inventor contributed to the claims, and naming the
wrong set can invalidate the grant. The list widget is shared with
publications through a `noun` prop rather than copied, because two lists of
the same thing is how they drift.

### Two workflows on one row, deliberately kept apart

`status` is **where the application has got to at the patent office**. Its
transitions are the ones the real process allows; `LAPSED -> GRANTED` exists
because paying a renewal fee late really does restore a patent, and REJECTED
and WITHDRAWN are terminal because a fresh attempt is a new application with
a new filing date.

`verification_status` is **whether this institution has vouched for the
record**. A granted patent can still be entered here with the wrong number,
the wrong inventors, or somebody else's invention.

Collapsing them would say that a coordinator's approval and a patent office's
grant were the same event. They are not, and the interface shows them as two
pills for the same reason.

A status that claims an event carries that event's date -- `granted` requires
a grant date, `published` a publication date -- as a CHECK in the database and
as a sentence in the service. The same shape as the milestones' "done is never
undated".

`verification_status` reuses the researcher profiles' existing enum rather
than minting a second one that would say the same four words. UNVERIFIED goes
unused here: recording a patent *is* asking for it to be checked, so a new
record starts PENDING. An administrator's record starts VERIFIED, by the same
reasoning that exempts an administrator's profile -- nobody is senior to an
administrator, so a PENDING admin record would ask a coordinator to vouch for
their own senior.

### Anyone in the research chain may record one -- students included

`PATENT_CREATE` is the first thing a student may create, and that is the
point: student inventors are ordinary here, and the university's own showcase
is built on them. The safeguard is not withholding the form; it is that every
record a non-admin enters waits for a coordinator before it counts.

**A Dean of Research and a facility custodian may not.** ADR 0028 makes the
dean deliberately read-only -- "reads, and changes nothing" -- and a
custodian's remit is a set of rooms. Both may still be *named* as inventors by
whoever records the patent, so nobody is cut out of the credit. Both read
patents like everybody else.

`PATENT_VERIFY` is a coordinator's and an administrator's. The queue filters
through the same scope rule the decision enforces, or it is a dead button.

Editing the substance of a verified record sends it back to PENDING: a tick
means somebody checked *that* content, and the content has just changed. The
same rule that sends an imported profile back to pending.

## Prior art: say what was searched, and what was not

**No open worldwide patent register can be read without a key.** Each was
tested, not assumed:

| Source | Answer |
|---|---|
| EPO OPS (Espacenet) | `403` -- OAuth credential required |
| USPTO Open Data | `401 Unauthorized` |
| PatentsView (both hosts) | keyless endpoint retired; serves a web page |
| WIPO PATENTSCOPE | `403`, and no API is published |
| PQAI | `401` -- token required |

That is the same wall ADR 0025 hit with Scopus and Web of Science, and the
zero-cost rule answers it the same way: use what is open, and be explicit
about the edge of what was searched.

So the check does three honest things:

1. **Looks for the same invention already recorded here**, reusing the trigram
   shortlist and rapidfuzz scoring the publication de-duplication runs on. Two
   teams in one university filing over each other is the failure this can
   actually prevent.
2. **Searches the open literature** through OpenAlex and Crossref, which are
   keyless and already wired up. A published paper is prior art in exactly the
   way another patent is, and it is what most often defeats novelty -- so this
   is not a consolation prize.
3. **Hands the query to the registers that can answer it**, pre-built.

The panel says in as many words that it has **not** searched the world's
patents, and a test asserts that sentence is present. An empty result means
"two open indexes found nothing", never "this is novel", and a source being
unreachable is reported rather than hidden -- a short list presented as a clean
result is the single most harmful thing this feature could do.

## Consequences

- Patent figures and publication figures can never be confused for each other,
  because they were never in the same table.
- No semantic search for patents yet: `EntityType` has no PATENT member, and
  adding one means an enum migration plus a document builder. Patents are
  full-text searchable through their own listing. Half-wiring it would have
  been worse than not wiring it.
- The prior-art check makes two outbound calls per run. Both are keyless,
  rate-limited by politeness headers, and failure degrades to the registry
  links rather than to an error.

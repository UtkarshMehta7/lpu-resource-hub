# ADR 0025: Profile import reads four public sites, and Scopus is not one of them

- **Status:** Accepted
- **Date:** 2026-09-28

## Context

Researchers were expected to type their own publication history into the
register, one entry at a time. Nobody with eighty papers is going to do that,
so the register stayed thin and the analytics built on it stayed unconvincing.

The project brief asks for "researcher profile with ORCID and Scopus import"
and names Scopus, Web of Science, Google Scholar and an institutional
repository as integrations. It also sets a hard constraint this project has
held to throughout: **zero cost, no paid APIs**.

Those two requirements are in direct conflict, so the sources were chosen by
testing rather than by the list in the brief.

## Decision

Four sources, all reachable without a key or a licence. Each was verified
against its live API before being written:

| Source | Role | Why |
|---|---|---|
| **ORCID** | Identity anchor | The researcher owns the record, so the name, employments and work list are self-asserted rather than inferred. Public API, no key. |
| **OpenAlex** | Breadth | Affiliations, subject topics and citation metrics. CC0, no key. This is what replaces Scopus. |
| **Crossref** | Metadata authority | Given a DOI, returns what the publisher registered: title, venue, type, date. No key. |
| **Semantic Scholar** | Supplement | Abstracts and fields of study, looked up by DOI. Keyless, on a shared rate-limited pool, so strictly best-effort. |

### Rejected, with the reason

- **Scopus** and **Web of Science** — require a paid institutional licence and
  an API key. Excluded by the zero-cost rule, not by preference. OpenAlex
  covers substantially the same corpus.
- **Google Scholar** — has no API. Scraping it breaches its terms, and the
  brief itself says "import only, no scraping".
- **ResearchGate** — has no public API. `api.researchgate.net` does not
  resolve, and a plain request for a profile page answers **403 with a CAPTCHA**.
  Reaching it would mean defeating an access control, which is out of the
  question. ORCID covers what it would have offered, with better provenance:
  a researcher's self-curated record rather than a scraped page.
- **JSTOR** — is a content archive, not a profile service. It has no concept
  of a researcher profile, so there is nothing to import. `/api/` answers 404,
  Constellate has been retired, and its holdings are subscription-gated.
  Journals it hosts are already reachable by DOI through Crossref and OpenAlex.
- **DBLP** — excellent for computer science, but answers server-side requests
  with an anti-bot challenge page instead of JSON.

### How identity is resolved

ORCID runs first, because it is the only source that *resolves* identity
rather than guessing it. The name it returns is then used to disambiguate the
others. Where an ORCID iD is not given, OpenAlex is matched on name and
affiliation and the result is labelled unconfirmed in the interface.

An ORCID that maps to several OpenAlex author records is reported as
ambiguous rather than resolved by picking the first. This is not theoretical:
ORCID's own public demo iD resolves to **42** distinct OpenAlex authors,
because real people pasted the example into their submissions.

### Preview, then apply

Import is two steps. `preview` reads the sources and changes nothing. `apply`
**re-reads them** and writes only what the researcher ticked.

Re-reading looks wasteful and is deliberate: it means bibliographic data
always comes from the source and never from the browser. If apply trusted the
payload sent back to it, any account could post arbitrary publications under
an "imported from Crossref" banner. Imports are rare and take a few seconds;
the guarantee is worth the round trip.

## Consequences

- Two runtime dependencies were added: `httpx` (it was already present, but
  only in the `dev` extra) and `rapidfuzz`.
- One new table, `profile_imports`, records every import, so "where did this
  publication come from" is answerable later.
- `researcher_profiles.orcid_id` is **unique**: an ORCID identifies one
  person, so two accounts claiming one is a data error refused at the database.
- The endpoint is rate-limited to 6 per hour per account. Each call fans out
  to four external APIs, and an unthrottled endpoint would let one account get
  the whole deployment throttled by Crossref and OpenAlex.
- Outbound requests identify this deployment by `mailto`. Both Crossref and
  OpenAlex route identified callers into a faster pool and throttle anonymous
  ones first, so this is not optional politeness.
- Import can be switched off entirely with `IMPORT_ENABLED=false`.
- There is **no** endpoint that imports into another person's profile. A
  publication list is a claim about oneself.
- De-duplication rules and their known failure cases are written up in
  [publication-deduplication.md](../publication-deduplication.md).

## Notes

Two bugs were found by running against the live APIs rather than against
stubs, and both are now covered by tests:

1. OpenAlex percent-encodes the slash in some DOIs
   (`10.5210%2fdisco.v5i0.2785`). Passed through unchanged, Crossref rejects
   the **whole batch** it appears in with a 400, losing the metadata for
   every other paper in that batch.
2. Crossref validates every DOI in a filter, so a single unusable identifier
   fails 40 good ones. Batches are now split on rejection to isolate the
   offender.

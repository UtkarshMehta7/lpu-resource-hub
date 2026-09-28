# ADR 0027: Choosing yourself, verifying what was imported, and nudging

- **Status:** Accepted
- **Date:** 2026-09-29

## Context

Three problems showed up the first time the profile import was used against
the live site, by a real person with a real name.

1. **It imported the wrong person.** Searching "Nitish Kumar" returned
   *Nitish Srivastava, Google (United States)* — 40 works, h-index 23 — and
   the interface presented that as the researcher's own record. It was the
   first hit of 25, and the connector was taking `results[0]`.
2. **Nothing could be checked.** Titles and DOIs were plain text, so the only
   way to confirm a publication was really yours was to copy the DOI and look
   it up elsewhere.
3. **An import could quietly launder unverified claims.** A verified profile
   stayed verified after pulling in an affiliation, a biography and eighty
   publications that nobody at this institution had looked at.

A fourth came from watching how the queues behave: somebody waiting on a
verification, a review, an approval or a decision had no way to say "this is
still sitting there" except to find the person.

## Decisions

### 1. A name search offers candidates; it never picks one

`search_candidates` returns up to ten possible people with their institution,
other affiliations, works count, citations, h-index, ORCID iD and subject
topics — and a link to the record itself. The researcher chooses, and their
choice is passed back as `openalex_author_id`, which overrides any name
matching.

A name lookup that *cannot* be narrowed now raises rather than guessing. An
affiliation match is still accepted, and a single result is still trusted,
but "25 people match, here is the first one" is not an answer.

> A name is not an identifier. This is the same class of mistake as the ORCID
> demo iD resolving to 42 OpenAlex authors (ADR 0025) — the difference is
> that this one was found by a person importing a stranger's publication list
> under their own name.

### 2. Everything links to its source, before and after importing

Each work in the preview links to `https://doi.org/<doi>`, falling back to the
source URL for books, theses and older papers without one. `WorkCandidate`
carries `url` for that reason. Each candidate profile links to its OpenAlex
record.

The point is that a claim can be checked *before* it is accepted, not only
audited afterwards.

### 3. Importing sends a verified profile back for verification

If an import changes any profile field or adds any publication, and the
profile was `VERIFIED`, it returns to `PENDING` and `verified_by` /
`verified_at` are cleared. An unverified profile is left alone.

A verification tick means somebody here checked the record. After an import it
holds claims nobody here has seen, so the tick has not been earned. The
researcher is told plainly, and their work stays visible meanwhile.

### 4. Nudging is a first-class action, with a cooldown

`POST /api/v1/nudges` with a kind and an entity. Four kinds: profile
verification, project review, booking approval, application decision.

Two rules keep it from becoming a nuisance, both enforced in the service
rather than the interface:

- **You may only nudge about your own thing, while it is genuinely waiting.**
  A nudge about somebody else's project, or one already decided, is a 404 —
  not a 403, so nudging cannot be used to discover what exists.
- **One nudge per thing per day**, from the `nudges` table. The notification
  carries a dedupe key for the same day, so a retry cannot slip a second copy
  through even if the cooldown check were bypassed.

**The sender never names the recipient.** The service resolves it from the
thing being chased — the department's coordinators, or administrators as the
fallback so a nudge is never delivered to nobody. A recipient field would
make this a way to message anyone in the institution, and a test asserts the
request schema has exactly two fields.

## Consequences

- Migration `0024` adds `nudges` and the `nudge_received` notification value,
  written by hand as always. Its downgrade drops the `nudge_kind` type —
  applied up front this time, having learned it from 0023.
- `describe.ts` gained a case for `nudge_received`, routing each kind to the
  queue that resolves it. Without it the notification arrives invisible.
- Nudges share the collaboration rate-limit budget: both are "this account is
  generating notifications for other people".
- The profile page shows past imports, so a researcher can see what their own
  account pulled in and when.
- Import history and the candidate search are both scoped to `/me`. A test
  asserts the full list of import routes, so adding one stays a decision.

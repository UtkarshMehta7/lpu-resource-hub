# 0037 — An unreachable prior-art source is named, not counted

**Status:** accepted
**Date:** 2026-10-09

## Context

The prior-art check queries two open literature sources concurrently, OpenAlex
and Crossref, each under its own six-second budget. Either can refuse or run
out of time, and ADR 0025's rule has always applied here: an unreachable
source is REPORTED, because a short list read as a clean result is the worst
thing this feature can produce.

It was reported, but only as a count. `PriorArtResult.literature_unavailable`
was a boolean, and the panel said:

> One of the literature indexes could not be reached, so this list is
> incomplete.

That sentence tells the reader something is missing and then withholds the
one fact that would let them judge how much. The two sources do not cover the
same ground: OpenAlex is the broad open index, Crossref is publisher-deposited
metadata keyed by DOI. "One of them" could mean either, and a researcher
deciding whether to file cannot act on it. The gap is also what the draft
claims say the system closes — naming the sources that did not answer is the
element that distinguishes it from US 2010/0125566 A1, whose claim 19 requires
only that a completed report identify the databases it used.

## Decision

Report the sources by name.

- `SOURCES` in `patents/priorart.py` pairs each fetcher with its name and
  fixes the order the result reports them in.
- `PriorArtResult.literature_unavailable: bool` becomes
  `unavailable_sources: list[str]`. Empty means every source answered; there
  is no second, derived boolean, because two fields saying the same thing is
  how they come to disagree.
- `pool.map` preserves input order, so each answer is zipped back to the
  source at the same position. `strict=True` on the zip, so adding a third
  source without extending `SOURCES` fails loudly instead of silently
  mislabelling which one was down.
- When the client itself cannot be built nothing was asked at all, so every
  source is named rather than none.
- The panel names them: "Crossref could not be reached", "OpenAlex and
  Crossref could not be reached".

## Consequences

The response schema changed shape rather than growing a field. Nothing outside
this repository reads it, and the frontend mirror ships in the same change —
the hand-written TS types have drifted from the Pydantic schemas twice before,
which is why they move together here.

Three backend tests now cover it instead of one: either source failing alone,
and both failing. A single one-sided test would pass just as happily with the
pairing hardcoded the wrong way round, which is the error this change is most
able to introduce.

# 0041 — A published opening goes on the board

**Status:** accepted — amends [ADR 0038](0038-the-institution-can-say-one-thing-to-everybody.md)
**Date:** 2026-10-12

## Context

An opening posted on this platform reached three places: the opportunities
board, the project it belongs to (ADR 0040), and a notification to the people
whose profile matched it. Everyone else had to go looking.

The notice board exists for exactly the case the matcher does not cover —
something the department should all know about, whether or not an algorithm
thinks it is for them. "We are hiring a research assistant" is that.

**But ADR 0038 withholds `ANNOUNCEMENT_POST` from faculty on purpose**, and
says why: `ROLE_HIERARCHY` would otherwise hand it to every faculty member, and
an institution-wide megaphone per person is not a notice board. Most openings
are posted by faculty. So "publishing an opening posts an announcement" is, on
its face, the precise thing that ADR was written to prevent.

## Decision

Publishing an opening raises a notice, and **three properties** keep that from
re-opening the hole ADR 0038 closed. All three are necessary; any one alone is
not sufficient.

### 1. The reach is the OPENING's, not the poster's

`policies.reach_of` — the function that gives an institution-wide role the
institution — **is not used here.** The audience is the department the opening
already belongs to (`Opportunity.department_id`, taken from its project or the
coordinator's own scope). A faculty member publishing an opening therefore
addresses their own department and nothing wider, which is the scope their
opening already had.

The institution-wide case exists only when an opening belongs to no
department, which only a coordinator can create.

### 2. Nothing here is free text

Subject and body are **derived** from the opening — its title, description,
eligibility, places and deadline. This is not a route by which somebody says an
arbitrary thing to their department; it is the opening, restated where people
read things.

### 3. One opening is on the board once, as a fact about the database

`announcements.source_opportunity_id` is **UNIQUE**, so a second notice for the
same opening is impossible rather than guarded in a handler somebody can later
skip — the rule `collaborations` holds for pairs. Postgres allows any number of
NULLs in a unique column, so hand-written notices are untouched.

In practice an opening is published exactly once in its life anyway:
`opportunities/policies.py:TRANSITIONS` has no `CLOSED -> OPEN`. The guard is
there so that adding reopening later changes the workflow, and not — silently —
the board.

## How it is wired

A second subscriber on `OPPORTUNITY_PUBLISHED`, an event that **already
existed** (it is what tells matching profiles). Nothing in the opportunities
module knows that announcements exist, and no module calls into another.

`OPPORTUNITY_CLOSED` is new, raised both by `close_opportunity` and by
`mark_filled_if_full`, because closed and filled mean the same thing to
somebody reading about it: there is no longer a way in. Its handler
**withdraws** the notice. A board advertising a closed opening is worse than
one that never mentioned it — somebody reads it, goes to apply, and finds a
door that does not open. Withdrawn rather than deleted, because said to
everybody is not unsayable; an administrator can still account for what was
announced.

The whole of it runs in a **savepoint that swallows `SQLAlchemyError`**, like
the thread opened on acceptance. Publishing an opening is the older and more
important act, and a new dependency from it to a new column does not get to
500 it.

## Consequences

- One nullable column, its UNIQUE and its FK — migration 0036, purely
  additive. CASCADE, because a notice about an opening that no longer exists
  is not a notice about anything.
- The board shows an **Opening** pill on these notices and the notice links to
  the position, so a reader does not have to go and find it by name.
- `posted_by_role` is frozen as it is for any notice, so these read "from
  Neha Gupta (faculty)" and not "from the institution". That is accurate: it
  **is** that person's opening.
- **Volume is the real cost.** Every published opening is now a line on its
  department's board, and a board people stop reading is worse than no board.
  Department scope is what keeps this proportionate; if it still proves too
  noisy, the next move is a per-reader filter on the board, not a change to
  who may post.

## Alternatives rejected

**Posting it institution-wide.** It is the hole ADR 0038 exists to close, it
would put every department's hiring in front of everybody, and nobody would
read the board a week later.

**Granting faculty `ANNOUNCEMENT_POST`.** Enormously larger than the request:
it would let any faculty member announce anything, not just their own opening.
The permission stays exactly where ADR 0038 put it; this feature does not use
it.

**Writing it as a notification instead.** Notifications are personal and
*caused* — that is ADR 0038's opening sentence — and one per recipient per
opening is a row per account per post on a 0.5 GB quota. The matcher already
notifies the people it is plausibly for; this is for everyone else.

**Leaving the notice up when the opening closes.** The cheapest option and the
one that makes the board untrustworthy: its oldest notices would be the ones
most likely to be false.

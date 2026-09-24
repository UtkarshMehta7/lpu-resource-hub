# ADR 0022: Conversation threads are scoped to a relationship, and polled

- **Status:** Accepted
- **Date:** 2026-09-24
- **Builds on:** [ADR 0020](0020-identity-on-screen-and-derived-coordinator-scope.md)
  (the UID beside every name), [ADR 0021](0021-account-deletion.md) (deletion
  and its cascade).

## Context

`collaboration_requests.message` was a single `Text` column. Someone sent one
message, the other person accepted, and the platform had nothing further to
offer — at the exact moment it succeeded at its whole purpose, it handed people
off to email or WhatsApp. The gap was not "we have no chat feature"; it was
that a connection the platform made could not be continued inside it.

Two things had to be decided: who may talk to whom, and how new messages reach
a browser.

## Decision

### Threads are scoped, never an open inbox

A thread belongs to an **accepted collaboration request** or to a **project
team**. There is no endpoint that creates one between two arbitrary people;
threads appear as a consequence of something else succeeding. A client cannot
conjure a channel, which is asserted directly in the tests against the OpenAPI
document.

This keeps the privacy rule the platform already had. `can_contact`
(`collaborations/policies.py`) says a student is reachable only if they opted
in to discovery; a general-purpose inbox would have quietly repealed that. It
also means somebody has already said yes before any thread exists, which is a
far better answer to harassment than a block list on a prototype with no
moderation staff.

**Membership is a table, not a derivation.** `conversation_participants` holds
who may read and how far they have read. Leaving a project deletes the
participant row and revokes access; the messages stay, still attributed. A
conversation is a record of what was said, not a possession of whoever is
currently on the team.

### 404, never 403

Every thread route answers 404 to a non-participant. A 403 on a thread id would
confirm that two named people are talking, which is precisely the fact a
private thread exists to keep. Administrators are no exception: seeing a
reported message in the moderation queue is not the same as being able to open
the thread it came from, and only the first is offered.

### Polling, not WebSockets

Four reasons, all from this repository rather than from taste:

- `docs/architecture.md` commits to sync SQLAlchemy and no Redis. WebSockets
  would be the first async code in the codebase.
- Render's free plan spins the instance down when idle, so a socket dies
  anyway.
- Polling was already the established pattern — `NotificationBell` at 60s.
- At this scale a 10-second poll on an open thread is indistinguishable from
  real time.

The cursor is a **keyset** over `(created_at, id)`, not an offset: a message
arriving between two polls shifts every offset by one, which would silently
skip a message. A malformed cursor replays the thread rather than erroring, so
a stale client recovers by itself.

Two things make 10 seconds feel instant rather than laggy: a sent message is
rendered from the POST response instead of waiting for the next poll, and
polling stops while the tab is hidden (`useVisible`) so a backgrounded tab does
not spend requests, battery, or keep a free instance awake.

### One notification per thread, re-armed by reading

The dedupe key is the conversation, so twenty messages produce one "you have a
message" line. Reading the thread **deletes** that notification row, which both
clears the bell and frees the key — so the next thing said after a lull is
announced again. Without this, chat would have been the feature that made the
notification bell useless.

### Moderation hides, never deletes

`ReportTargetType.MESSAGE` plus `hidden_at`/`hidden_by`. A hidden message keeps
its place in the thread with its text withheld, so the exchange still reads in
order and the other party is not left with a hole they cannot explain. The
conversation list shows no preview for a hidden message — the list must not be
a way to read around a moderator's decision. Reporting a message requires being
in the thread, or reporting would become a way to ask whether a message id is
real.

## Consequences

- A new module, `messages`, which is **not** in the approved module list in
  `docs/architecture.md`. That list is extended rather than bent: threads are
  not collaborations (a project thread has no request) and not notifications
  (a notification is one-way).
- `conversations` carries two nullable foreign keys with a `CHECK` that exactly
  one is set, rather than one polymorphic `subject_id` — the same shape as
  `tag_aliases`. Real foreign keys cascade, so deleting a project or a request
  takes its thread with it; a polymorphic id cannot, and would strand threads
  forever.
- `DeletionImpact` gained `messages_sent`. Deleting an account takes its half
  of every thread with it (consistent with ADR 0021), and the confirmation now
  says how much before anyone agrees to it.
- Migration 0019 adds two enum values by hand. Autogenerate compares tables,
  not enum members, so `notification_type` and `report_target_type` additions
  are written explicitly — and the downgrade leaves them, because PostgreSQL
  cannot drop an enum value and rebuilding both types would rewrite every
  notification and report row.
- A whitespace-only message was accepted and stored blank before the schema
  trimmed first; `min_length` counts spaces. Fixed with a validator, tested.

## Amendment, same day: ending a collaboration, and not taking it down with us

Two things the first pass got wrong, both found by using it rather than by
testing it.

**Chat took collaboration down with it.** Opening a thread on acceptance was a
plain call inside the accepting transaction, so on the deployed instance --
where the code shipped before its migration -- every acceptance answered 500
and the collaboration was never accepted at all. An additive feature broke an
older, more important one. It now runs in a savepoint and swallows
`SQLAlchemyError`: the acceptance commits, the thread is simply missing, and
the log says why. Tested by making thread creation raise and asserting the
acceptance still succeeds.

**A collaboration could be started but never ended.** `ACCEPTED -> ENDED` is
now in the transition table, open to *either* party: it takes two to start one
and one to stop it, because requiring both to agree would mean nobody could
ever leave. The thread stays readable and takes no new messages -- what was
said still happened, and the record outlives the relationship. `open` on the
conversation says so, so the composer is hidden rather than the person
discovering it by pressing Send and getting a 409. Project threads never close
this way: a project has its own lifecycle, and an archived project's team can
still need to talk about what happened.

## Alternatives considered

- **Generic user-to-user DMs.** The obvious reading of "add chat", and the
  wrong one here: an open inbox in a university product is a harassment
  surface, needs per-user blocking, and repeals the student opt-in.
- **WebSockets or SSE.** Rejected for now on the four grounds above. SSE
  remains the upgrade path if chat ever has to feel instant: one endpoint, no
  schema change, no Redis.
- **One notification per message.** Simplest, and it would have buried the
  bell under a live conversation.
- **Deleting a moderated message.** Leaves a hole mid-exchange that the other
  party cannot interpret; hiding says what happened.
- **Requiring both parties to agree before a collaboration ends.** Symmetrical
  and unworkable: somebody who wants out would need permission from the person
  they want out from.
- **Deleting the thread when a collaboration ends.** Destroys the other
  party's record of an exchange they were half of, to tidy a list.
- **Deriving thread membership from the project on every read.** Saves a table
  and loses the ability to revoke access without rewriting history — and makes
  every message read a join against project membership.

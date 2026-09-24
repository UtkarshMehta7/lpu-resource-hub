# ADR 0023: A collaboration belongs to a pair of people, not to a request

- **Status:** Accepted
- **Date:** 2026-09-24
- **Amends:** [ADR 0022](0022-scoped-conversation-threads.md), which keyed a
  conversation to a collaboration *request*.

## Context

Three bugs were reported as one ("it still offers to collaborate, and the
messages are wrong"). Reproduced against a running instance:

1. A student already collaborating with a faculty member could send a fresh
   request to the same person: `201`. The partial unique index
   `uq_collaboration_requests_pending` only constrained `status='pending'`, so
   an accepted or ended relationship blocked nothing.
2. Accepting that second request opened a **second conversation**. The student
   then had two threads titled with the same person's name, one open and one
   closed, and their history was split down the middle.
3. Direction was not normalised. `A→B` and `B→A` were different rows, so two
   people could hold simultaneous pending requests to each other, and a third
   thread was one acceptance away.

They are not three bugs. They are one modelling mistake with three symptoms:
**a collaboration and its conversation were keyed to a request, when they
belong to a pair of people.** Fixing the symptoms individually would have
meant three guards in the service layer, each of which somebody could later
forget; modelling the relationship removes the possibility.

## Decision

**One relationship row per unordered pair.** `collaborations` stores
`user_a_id < user_b_id` — enforced by a CHECK — under
`UNIQUE(user_a_id, user_b_id)`. Asking for `{a,b}` and `{b,a}` returns the same
row. The database makes a duplicate impossible; no service check can drift
from it.

**Requests become events against the relationship**, not the relationship
itself. `collaboration_requests` keeps every row as the history of what was
asked and answered, and gains a `collaboration_id`.

**States live on the pair**: `none → requested → active → ended`, and
`ended → requested` again. Declining or cancelling returns to `none`, because
a question answered "no" is not a relationship — either person may ask again.
Accepting makes it `active`; either party may end an `active` one.

**One conversation per pair, for the life of the pair.** Collaborating again
after ending **reopens the same thread**. Two people have one history, however
many times they start and stop. A thread is writable only while the
relationship is `active`, and readable always.

`project_id` stays on the request as context. A request *about* a project is
still a request between two people, so two people have one relationship and
one thread even if they work on three projects together. The alternative —
keying on pair+project — gives a thread per project and reintroduces the
reported bug in a subtler form.

**The interface asks the state and shows one action.**
`GET /collaborations/with/{user_id}` answers in one call, and the button
renders request / pending+cancel / accept+decline / open+end accordingly. It
previously offered "Request collaboration" unconditionally, which is how a
user was invited to create the duplicate in the first place.

## Consequences

- **Migration 0021 repairs existing data**, and that is the risky half: it
  derives one relationship per pair from existing requests (accepted beats
  ended beats pending), then **merges duplicate threads** — oldest kept, every
  message repointed, participants unioned. No message is deleted.
- **Merging read marks takes the earliest, and NULL wins.** Showing something
  unread twice is a nuisance; hiding something nobody has read is a failure.
- The migration is irreversible in substance. The downgrade drops what was
  added but cannot unpick a merge — once two threads are one, which message
  came from which is no longer a question the data can answer. The docstring
  says so rather than implying a clean rollback.
- `uq_collaboration_requests_pending` is dropped: the pair's own state decides
  whether a request may be made, and a partial index per direction would only
  disagree with it.
- Two existing tests asserted the old behaviour and were rewritten, not
  deleted: "the reverse direction is a different request" and "a project
  request is distinct from a general one" were the bug, written down as
  guarantees. A third had quietly become vacuous — it proved the database
  rejects a self-request via an IntegrityError that the new NOT NULL column
  would have raised anyway, so it now asserts the stronger thing: a pair
  cannot be a person with themselves.

## Alternatives considered

- **Widen the partial unique index to cover accepted and ended.** Fixes symptom
  1 only, leaves the direction hole and the split history.
- **Guard in the service layer.** Works until someone adds a second write path.
  A unique constraint cannot be forgotten.
- **Key the pair and the project together.** A thread per project sounds
  tidier and re-splits the history of two people the moment they collaborate
  on something new.
- **Delete the older thread when merging.** Faster, and it destroys one
  party's record of an exchange they were half of.

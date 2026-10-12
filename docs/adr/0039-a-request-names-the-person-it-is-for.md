# 0039 — A request names the person it is for

**Status:** accepted
**Date:** 2026-10-12

## Context

ADR 0031 settled a rule and stated it plainly: **a nudge never names its
recipient.** `POST /nudges` takes a kind and an entity, and the service works
out who hears about it from the thing being chased. A recipient field there
would have made it a way to message anyone in the institution, and a test
asserts the schema has exactly two fields.

That rule is right for a nudge, which is always *about* something the
platform already knows about — a verification waiting, a project unreviewed.
The recipient follows from the thing.

It is wrong for the request people actually need to make. "My supervisor has
not signed my form", "the lab I was assigned is locked", "I need the
department's sign-off before Friday" are addressed to a **person**, and
nobody else can act on them. There is no entity to resolve the recipient
from; the recipient *is* the point.

Nothing else fitted:

- **Messages** are scoped to an accepted collaboration or a project team
  (ADR 0022), and there is deliberately no route that creates a thread —
  adding one repeals the student opt-in (`can_contact`) by the back door. A
  student with a problem has no collaboration with their coordinator.
- **Announcements** (ADR 0038) address an audience, not a person, and travel
  downward.
- **Nudges** cannot carry a subject or a document, and their resolvers refuse
  an entity the sender does not own.

## Decision

A personal request **names its recipient**, and the recipient field is made
safe by two things rather than by trusting the interface.

### 1. `REQUEST_RECIPIENT_ROLES` — upward only

A table in `app/core/permissions.py`, and the only authority on how far a
request travels:

| sender | may address |
|---|---|
| student | faculty, research coordinator |
| faculty | research coordinator, dean, admin |
| facility custodian | research coordinator, dean, admin |
| research coordinator | dean, admin |
| dean of research | admin |
| **admin** | **nobody** |

Nobody addresses their own role or anything below it, and a test asserts that
property of the table itself rather than of any particular row. An
administrator addresses nobody because they are the top of the institution: a
request from there is an instruction, which is a different thing, and the
form says so rather than disappearing.

A custodian escalates like a coordinator's report would — their facilities
belong to a department, so their path runs through it.

### 2. The department check

Role alone is not enough. Without a scope check, naming *any* faculty member
in the university would work and the recipient field really would be the
general messaging route nudges refused to be. `policies.addressable_filter`
adds it: the recipient must be in the sender's own department, **unless** they
answer to the institution rather than a department (`INSTITUTION_WIDE_ROLES` —
a dean and an administrator belong to none).

**The same filter builds the candidate list and checks the submit**, so the
picker can never offer somebody the submit would refuse — the rule the
facility-custodian candidate list already holds. `may_address` re-reads the
stored row; it is not a second opinion assembled from the role.

### 3. One transition table, two actors

`policies.TRANSITIONS` maps `(from, to)` to the sides that may make the move,
the way `milestones/policies.py` serves members and owners from one table.
The recipient drives the institution's half — take it up, resolve, decline —
and the sender may only ever **withdraw**.

`withdrawn` is kept distinct from `declined` deliberately: "I no longer need
this" and "the answer is no" are different outcomes, and a queue that read
them as one would mislead.

**Reopening a decided request does not exist for anybody.** An answer has been
given; asking again is a new request with its own date, not a mutation of the
old one.

The two refusals are ordered the way the patent pipeline orders them: a move
that does **not exist** is **409 whoever asks**, and a move that exists but is
the other party's is **403**. Checked that way round, or a sender asking to
resolve their own request is told it is merely somebody else's to do — when
the honest answer is that resolving is not a thing a sender ever does.

`next_statuses` is computed **per reader**, so the interface cannot offer a
step the service would refuse, and the frontend holds no copy of the table.

### 4. Declining requires a reason

In the Pydantic schema, in the service, and as a `CHECK`. Three places,
because "no" without a reason is what stops the next person asking — the same
rule the patent pipeline holds for declining a disclosure. A status claiming a
decision carries its date, also as a `CHECK`.

### 5. Two people, and no third

`policies.visibility_filter` is the sender or the recipient. **Administrators
included**: a third party gets 404, the same answer a conversation thread
gives a non-participant. A channel somebody else reads is useless for the
thing this exists for.

Attachments follow the request exactly — the download re-runs that filter and
scopes the attachment id to the request in the path, so there is no public
route to the bytes. The sender attaches, and only while the request is still
open to an answer: adding to a decided request changes what the other party
answered, after they answered it.

## Consequences

- Two tables, two new enums, two reused (`user_role` twice, with
  `create_type=False`) — migration 0035.
- `notification_type` gains `request_received` and `request_decided` by a
  **hand-written** `ALTER TYPE`, because autogenerate compares tables and
  never enum members (migrations 0017 and 0019 again). Shipping the Python
  members without it — which is what happened when this work was merged
  half-finished — leaves the two enums disagreeing until the first
  notification fails at the insert.
- `request_received` is the only notification on the platform whose recipient
  the **sender** chose. It names the sender's role, because "a student has
  asked you" and "a coordinator has asked you" are different things to read.
- Shares the collaboration rate-limit budget with nudges: both are "this
  account is generating notifications for other people", which is the thing
  worth capping.
- The navigation entry for `/collaborations` was renamed from "Requests" to
  "Collaboration requests". One menu with two unrelated things under the same
  word is unreadable, and a test now asserts it cannot come back.
- `/requests/inbox` is offered only to roles somebody can actually address. A
  student's or a custodian's inbox would always be empty.

## Alternatives rejected

**Extending nudges with a recipient.** The smallest change, and the one ADR
0031 exists to prevent. The guard there is that the recipient is *derived*;
adding a field removes the guard rather than adding a feature, and every
existing nudge kind would inherit a hole.

**A thread per request, reusing messages.** Conversations are scoped to an
existing relationship on purpose, and a create-conversation route is the one
thing ADR 0022 forbids. It would also give a request no status, when "where
has this got to" is most of what a sender wants.

**Letting the sender address anyone above them anywhere in the university.**
Drops the department check, which is the half that keeps this from being
general messaging. A student emailing a coordinator in another school is not
an escalation; it is a message.

**Reopening a decided request.** Tempting, and wrong: it would let an answer
be erased and re-asked under its original date. A new request costs one form
and keeps the history honest.

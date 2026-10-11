# 0038 — The institution can say one thing to everybody

**Status:** accepted
**Date:** 2026-10-12

## Context

Every notification on this platform is personal and *caused*. An application
was received, a profile was verified, a milestone fell due, somebody asked you
to look at a project. Fifteen `NotificationType` members and each one answers
"this happened to you, or involving you".

Nothing could say one thing to everybody. The IP cell had no way to tell the
institution that the invention-disclosure window closes on Friday, and a
coordinator had no way to tell their department that a seminar had moved. The
nearest things were all the wrong shape:

- **Messages** are scoped to an accepted collaboration or a project team
  (ADR 0022), and there is deliberately no endpoint that creates a thread —
  adding one would repeal the student opt-in (`can_contact`) by the back door.
- **Nudges** take a kind and an entity and resolve the recipient from the
  thing being chased (ADR 0031). A recipient field there would make them a way
  to message anyone in the institution, and a test asserts the schema has
  exactly two fields.
- **Funding calls** are a register of external opportunities with deadlines,
  not a channel.

So the gap was real, and it was not a row that fitted an existing table.

A second question came with it. A notice addressed to the whole institution,
delivered as a notification, writes one row per account per post. At the
demonstration scale that is tens of rows; at a real university it is tens of
thousands, against a 0.5 GB free-tier quota, for a thing most people read once.

## Decision

A notice is **read from a board, not delivered**, and its reach is **derived
from whoever posts it**.

### Reading needs no permission

Every signed-in role reads the board. A student, a facility custodian and the
dean see the same page, and there is no role filter anywhere in the module.
That is the feature: a channel that reached only some roles would not be an
announcement.

### Posting is `Permission.ANNOUNCEMENT_POST`, held by three roles

`RESEARCH_COORDINATOR`, `DEAN_OF_RESEARCH` and `ADMIN`. The grant sits on the
coordinator's own rung rather than faculty's, because `ROLE_HIERARCHY` makes a
coordinator inherit faculty and not the reverse — granted one rung lower,
every faculty member would have acquired an institutional voice for free.

For the dean this is the one thing the role **writes**. ADR 0028 made a dean
deliberately read-only over records, which is right, and which had left
somebody senior able to see the whole institution and unable to tell it
anything. A notice is not a record.

A facility custodian may not post. They look after rooms, and ADR 0028's
reasoning holds: that must not confer a voice over people.

### The reach is derived, never named in the request

`AnnouncementCreate` has **no `audience` field**, and must never grow one.
`policies.reach_of` answers it from the poster:

- an institution-wide role (`INSTITUTION_WIDE_ROLES`) addresses the
  institution;
- a coordinator addresses the department they are the coordinator *of*, read
  from `coordinator_scope_id` rather than `department_id` — the two are kept in
  step by `_sync_coordinator_scope`, and the scope is the one that means
  authority.

This is the same discipline `CREATABLE_ROLE` holds for a new account's role,
for the same reason: a field the client sets is a field the client can forge.
A coordinator's scope IS their department everywhere else in this schema, and
an `audience` field is exactly how ten coordinators would each acquire an
institution-wide megaphone.

A coordinator whose scope is missing gets **409, not a widened audience**. The
sync makes that state unreachable through the application, but a row written by
a script could still be in it, and the wrong answer is to quietly promote the
notice to everybody.

### Delivery is a read marker, not a fan-out

`announcement_reads` carries one row per person who has **opened** a notice.
The unread count is a `NOT EXISTS` against it, so posting writes one row
whatever the size of the institution. This is the derived-not-stored choice
ADR 0026 made for milestone risk, applied to a different question: the count
is computed on read rather than materialised at post time.

The badge sits in the header beside Messages and the bell, on the same gentle
60-second poll. A board nobody is told about is a board nobody reads.

### A draft stage, because attachments need a saved row

An upload is multipart against an existing notice, so there has to be a stage
before anyone else can see it — otherwise a notice appears on the board and
grows its documents afterwards. `draft → published → withdrawn`:

- A **published notice cannot be edited by anyone, its author included.** The
  institution has already read it; the answer is a correction, not a rewrite.
  That is **409 whoever asks**, and a notice belonging to somebody else is
  **403** — checked in that order, or an author would be told that editing
  their own published notice was merely above their pay grade (the patent
  pipeline's rule, ADR 0036). `_assert_may_edit` is the single place the two
  checks are ordered, for all three write paths; spelled out separately they
  disagreed, and a test caught an admin being told that somebody else's
  published notice was merely not theirs.
- An administrator may **withdraw** somebody else's notice but never **rewrite**
  it. Changing what another person is recorded as having announced is a worse
  power than taking it down, so there is no state in which the route succeeds:
  a draft is invisible to them and a published notice is editable by nobody.
- **A draft is its author's alone, administrators included.** The form tells
  the author that nobody else can see it, and that has to be true — the same
  answer a conversation thread gives a non-participant. An admin can see a
  *withdrawn* notice, so somebody is able to clear one away.
- `published_at` is enforced by a `CHECK`, the "done is never undated" rule
  from the milestones and the patent pipeline.

### The poster is frozen on the row

`posted_by_name` and `posted_by_role` are copied at post time, and `posted_by`
is `ON DELETE SET NULL`. "From the Dean of Research" is part of what was said:
promoting that person later must not retitle a notice from last term, and
deleting the account must not silently retract it.

## Consequences

- Four tables, two new enums, one reused (`user_role`, with
  `create_type=False` — migration 0034).
- Attachment bytes live on `announcement_attachments.data`, the same shape as
  `message_attachments` and for the same reason: the FK cascade reaps them, so
  no blob outlives the thing that referenced it. The type is sniffed from the
  bytes (`uploads/validation.py`); a RAR called `circular.pdf` is stored and
  served as a RAR.
- There is **no public path to an attachment**. The download re-runs the
  notice's own visibility filter and scopes the attachment id to the notice in
  the path, so another department's file is exactly as unreachable as its
  notice. The interface therefore fetches bytes through the API client and
  renders images from a blob — an `<img src>` would send no Authorization
  header, and the route answers `Content-Disposition: attachment` with
  `nosniff` so nothing uploaded here can run as the application.
- Links are their own rows with labels, and `http(s)` only. A `javascript:`
  URL on a notice the whole institution reads would be a stored script with an
  audience; refused on the way in as well as escaped on render, because either
  alone is a single point of failure.
- `policies.visibility_filter` is used by the list, the single read, the
  unread count and the download, so none of them can disagree — the same
  composition milestones use when they call the projects module's filter
  instead of restating it.
- Announcements are **not** registered with the global search module. The board
  has its own `search_document` for `?q=`, but a notice is not a research
  entity and an `EntityType` would put it in the embedding pipeline and the
  cross-entity results.

## Alternatives rejected

**A notification per recipient.** Visible in the existing bell with no new
page, and the delivery problem already solved. Rejected on the fan-out: one
post costs a row per account, and notices are the one kind of message
everybody gets. The read marker gives the same unread badge for one row.

**An `audience` field on the create request.** Would let an administrator post
to a chosen department, which is a real use. Rejected because the same field
necessarily lets a coordinator choose `institution`, and no validation can
distinguish "an admin picked a department" from "a coordinator widened
themselves" without reintroducing the derived rule anyway. An admin who needs
to reach one department can say so in the subject.

**Role-filtered notices** ("for faculty only"). Rejected as a different
feature. The ask was a channel the whole institution reads, and a role filter
on a notice board is how a notice quietly fails to reach the person it was
about.

**Editing a published notice.** Rejected: people have read it. A board whose
history can be rewritten is worth less than one whose notices can only be
withdrawn and corrected.

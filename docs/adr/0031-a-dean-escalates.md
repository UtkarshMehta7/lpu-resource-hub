# ADR 0031: A dean escalates, and nudges learn to travel downward

- **Status:** Accepted
- **Date:** 2026-10-05

## Context

ADR 0028 gave the Dean of Research `ANALYTICS_READ` and nothing else, on the
principle that senior figures should see the institution's numbers *without*
acquiring the ability to edit the records behind them. That principle is
right. The result, reported from the deployed interface, was not: the dean
could open the at-risk board, see seven slipping projects, and **do nothing at
all** — not even ask the department's coordinator to look.

Reading without any means of acting is not restraint; it is a dead end.

## The obvious fix was wrong

Add the dean to the existing nudge kinds. It does not work, and the reason is
worth stating because it is the shape of the whole feature.

Every existing nudge means **"my own thing is stuck, please act"**. Each
resolver enforces exactly that:

```python
if project.owner_id != actor.id:      raise NothingToNudgeAboutError
if booking.user_id != actor.id:       raise NothingToNudgeAboutError
if application.applicant_id != actor.id: raise NothingToNudgeAboutError
```

A nudge travels **upward**, from the person waiting to the person who can act.
A dean escalating travels **downward**: an institutional reader saying
*"somebody else's project is slipping, please look at it"*. The ownership
checks would refuse them, correctly. It is a different act that happens to
share a delivery mechanism.

## Decision

A new kind, `NudgeKind.PROJECT_AT_RISK`, with its own resolver and its own
rules. In place of the ownership check it makes two others:

- **The sender must be an institution-wide reader** (`INSTITUTION_WIDE_ROLES`
  — a dean or an admin). A coordinator escalating would be nudging themselves,
  and a project owner already has `PROJECT_REVIEW` for their own work.
- **The project must actually be in trouble.** "Please look at this" about a
  project that is perfectly on track is noise, and somebody who receives one
  such nudge discounts the next. Risk is asked for through the same `assess`
  the board and the project page use — derived on every read (ADR 0026), never
  stored.

Recipients are resolved exactly as before: `_approvers` gives the department's
coordinators, falling back to administrators so a nudge is never delivered to
nobody. **The request still names no recipient** — it carries a kind and an
entity, and a test asserts the schema has those two fields and nothing else.
That constraint is what stops this becoming a way to message anyone in the
institution, and it survives unchanged.

The daily cooldown applies as it does to every other kind.

## Consequences

- Migration `0029` adds the enum value by hand. Autogenerate compares tables,
  not enum members, and emits an empty migration otherwise — the omission that
  has now bitten this repository four times (0017, 0019, 0028, 0029).
- `_dependency_map` in the milestones service became `dependency_map`, shared
  rather than copied, so the escalation and the board cannot develop different
  opinions about what "blocked" means.
- The 404 message lost the word *"yours"*. It read "There is nothing of yours
  waiting on anyone here", which is a confusing answer to a dean asking about
  somebody else's project.
- The notification reads differently for this kind: *"X asked you to look at
  …"* rather than *"X is waiting on …"*. Identical wording would have told a
  coordinator that the dean was waiting on them, which inverts who owes whom.
- The button appears on the at-risk board for institution-wide readers only.
  The server refuses anyone else regardless; the guard merely stops offering a
  control that cannot work.

## What was deliberately not done

The dean still edits nothing. An escalation changes no record — it writes a
nudge row and a notification, exactly as a researcher chasing their own
verification does. ADR 0028's principle is intact: the dean acts on what they
see by **asking the people who can act**, not by acting themselves.

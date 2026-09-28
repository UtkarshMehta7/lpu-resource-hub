# ADR 0026: Milestones, and why "at risk" is derived rather than stored

- **Status:** Accepted
- **Date:** 2026-09-28

## Context

Projects had a status workflow, members, a review queue and conversations, but
no plan: nothing said what a project intends to deliver or when. That single
absence blocked six separate things at once — the milestone and Gantt views,
the at-risk board on the admin dashboard, milestone notifications, the
scheduled at-risk computation, milestone-adherence reporting, and the
acceptance criterion that milestones be "flagged at-risk automatically with
configurable thresholds".

## Decisions

### 1. Risk is derived on every read, not stored on the row

The brief asks for "milestone at-risk computation as a **scheduled job**".
This deliberately departs from that.

A stored flag is correct only at the instant the job last ran. A milestone
that falls due overnight would read as on track until the job next fires, and
the number on the coordinator's board would disagree with the one on the
project page — and the number people trust is whichever they saw last.

Risk is a pure function of the status, the due date, today, and the state of
what the milestone waits on. There is nothing to cache and nothing that can go
stale, so `app/modules/milestones/risk.py` computes it per request and the
analytics view calls the *same function* rather than reimplementing the rules
in SQL.

The scheduled job still exists and does the one thing derivation cannot:
telling somebody exactly once. That is what the dedupe key buys.

The order of the rules is itself a decision:

```
settled (done / cancelled)  -> none      not "fine", simply not outstanding
due date has passed         -> overdue   a fact beats a prediction
waits on something late     -> blocked   says *why*, which is actionable
due within N days           -> at_risk
otherwise                   -> on_track
```

Overdue beats blocked because a date that has passed is a fact while a
blockage is a forecast. Blocked beats at-risk because "the thing before it is
late" is more useful to act on than "it is due soon".

### 2. Two actors, not one

Project members may move a milestone along (`in_progress`, `done`); only the
owner may create, edit, delete or cancel one. Moving work along is the team's
motion and happens weekly — the student who did the work marks it done.
Changing what the plan *is*, or striking work off it, is the owner's and
happens rarely. `policies.TRANSITIONS` is the single table both are checked
against, matching the project-wide rule that a workflow lives in one place.

### 3. The threshold is deployment-wide configuration

`MILESTONE_AT_RISK_DAYS` (default 7), surfaced read-only on
`/admin/settings`. That endpoint already states the position this follows:
*"changing behaviour is a deploy, not a click"*. Because risk is derived,
changing it takes effect on the next page load rather than the next job run.

A per-project override was considered and rejected for now: it adds a column,
a form field and a fallback path to test, for a distinction no one has yet
asked for.

### 4. Dependencies are a graph, and the service keeps it acyclic

`milestone_dependencies` is an edge table. Self-dependency is refused by a
CHECK constraint — the one case a constraint *can* express. Longer cycles are
refused by the service, which walks the existing edges before inserting and
rejects an edge whose target already reaches the source. No constraint can
express acyclicity, and a cycle would make the risk walk non-terminating.

### 5. A timeline and a list, not one or the other

The brief asks for a "milestone **or** Gantt view". Both are built, because
the Gantt cannot be the only view: five months of columns are unreadable on a
phone, so the chart is hidden below `md` and the list carries the same
information — including "waits on X", which a chart can only imply.

The timeline is hand-rolled SVG with no new dependency, following
`features/analytics/NetworkGraph`. Recharts has no Gantt primitive (it would
have to be faked with a stacked bar whose first segment is transparent, and
dependency arrows would be impossible), and a dedicated Gantt package brings
styling that fights the design system.

## Consequences

- Migration `0023` adds `milestones` and `milestone_dependencies`, plus two
  `notification_type` values written by hand — autogenerate compares tables
  and columns and never sees enum members (the trap behind 0017 and 0019).
- No new permission: the at-risk board reuses `Permission.PROJECT_REVIEW`,
  which is already coordinator-and-admin, so the RBAC matrix is unchanged.
- Milestone visibility is **composed** from `projects.policies.visibility_filter`
  rather than restated. A milestone is visible exactly when its project is,
  and one on a project the caller cannot see is a 404, never a 403.
- The reminder job sends at 7 and 1 days before, and once — ever — when a
  milestone goes past its date. Not once a day for as long as it stays late.
- `scripts/seed_demo_data.py` now seeds three projects whose milestones span
  every risk state, so the board and the timeline are not empty on a new
  install.

## Note

The seed script previously created no projects at all, so "add milestones to
the demo projects" had no demo projects to add them to. It seeds both now.

# ADR 0032: A dean decides what crosses departments

- **Status:** Accepted
- **Date:** 2026-10-05

## Context

ADR 0028 said the dean "reviews nothing". ADR 0031 let them escalate. This is
the third power, and unlike the other two it is not a convenience added to a
role — it closes a hole that was already in the model.

`review_queue` scopes a reviewer to one department:

```python
query = query.where(Project.department_id == reviewer.coordinator_scope_id)
```

A coordinator's authority stops at their department. So a project whose team
reaches into a second department has **no reviewer who can see all of it**.
The coordinator who owns the project's department sees half the team; the
other coordinator cannot see the project at all. Only an administrator could
decide it, which makes an institutional research judgement into an
administrative one.

That is the gap the Dean of Research exists to fill.

## Decision

`DEAN_OF_RESEARCH` gains `PROJECT_REVIEW`, and the scope is enforced in
`projects/policies.py` rather than by the permission.

That division matters and is the same one `FACILITY_MANAGE` needed in
ADR 0028: **holding a permission says a person may review *a* project, never
every project.** `may_review` decides which:

| Reviewer | May decide |
|---|---|
| Admin | anything |
| Research coordinator | their own department's work |
| **Dean of research** | **work that crosses departments, and nothing else** |

"Crosses" is **computed, not flagged** — a project crosses when any member's
department differs from the project's own, or when the project has no
department at all (in which case no coordinator can reach it either). Nobody
has to remember to set a field, and a project that becomes cross-department by
gaining a member becomes reviewable by the dean at the same moment.

A dean deciding ordinary departmental work is refused, because it would
quietly replace the coordinator who is meant to.

### The queue and the decision use the same function

`review_queue` filters a dean's list through `crosses_departments`, and
`review_project` checks `may_review` on the loaded row. A queue that offered a
project the review call would refuse is a dead button — the same reasoning as
`manageable_facility_filter` and the booking queue (ADR 0028).

### Visibility had to widen, authority did not

`visibility_filter` refused a dean a pending project outright, so the review
returned 404 before the authority check was reached. A reviewer who cannot
open what they are asked to approve is no reviewer. The filter now admits a
dean, and `may_review` makes the judgement on the loaded row — SQL cannot see
whether a team crosses departments.

This widens what a dean may **see**, not what they may **do**. Everything else
remains read-only.

## The dashboard

The dashboard had sections for student, faculty, coordinator and admin and
none for a dean or a custodian, so both roles signed in to an empty page.
Both now have one, built from the same helpers the analytics page uses so the
two cannot disagree about the same number — and every figure links to the
place it can be acted on, because a number with nowhere to go is the same dead
end in a smaller form.

## Consequences

- `ROLE_PERMISSIONS[DEAN_OF_RESEARCH]` is two permissions, not one. The guard
  test that asserted exactly `{ANALYTICS_READ}` now asserts both, with the
  scoping noted.
- "Reviews" appears in a dean's navigation. An earlier test asserted it must
  not; that assertion was correct when the dean reviewed nothing and is now
  updated rather than deleted.
- Verification and bookings remain absent from a dean's navigation: they are
  departmental acts, and a dean oversees no department.

## What was deliberately not done

No approval threshold by value, and no new workflow state. The project
workflow still has one review step; who may perform it simply depends on
whether the work is departmental or institutional. Adding a second gate would
have made every cross-department project wait for two people.

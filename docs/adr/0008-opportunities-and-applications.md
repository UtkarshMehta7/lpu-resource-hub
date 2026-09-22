# ADR 0008: Step 7 opportunities and applications

- **Status:** Accepted
- **Date:** 2026-09-22
- **Context:** Step 7 adds an opportunity board (openings on research projects, or department-wide) and an application workflow with decisions, withdrawal and team onboarding.

## Decisions

1. **Two transition tables.** `opportunities/policies.py: TRANSITIONS` (DRAFT → OPEN → CLOSED, DRAFT → CLOSED, OPEN → FILLED) and `applications/policies.py: TRANSITIONS` (SUBMITTED → UNDER_REVIEW/SHORTLISTED/REJECTED, UNDER_REVIEW → SHORTLISTED/ACCEPTED/REJECTED, SHORTLISTED → ACCEPTED/REJECTED, and applicant withdrawal from any non-final status). Nothing else writes `status`. Accepting requires a review step first: you can't accept a SUBMITTED application straight away.
2. **Opportunities start as drafts; `POST /opportunities/{id}/publish` opens them.** The roadmap lists only `close`, but `status` must never be client-writable, so publishing is an explicit action sub-resource (the pattern in docs/architecture.md). Publishing re-checks the deadline and that the project is still ACTIVE.
3. **FILLED is a "system" transition.** It happens inside the accept transaction when the accepted count reaches `positions`; no endpoint can request it.
4. **Who may post.** `opportunity:create` is a FACULTY grant (coordinators inherit it). Faculty must attach an opportunity to a project they own that is ACTIVE (`422` without a project, `403` for someone else's, `409` if not active). Coordinators may also post on a project in their department, or department-wide with no project. `department_id` comes from the project or the coordinator's scope and is never client-writable.
5. **Who may apply.** `application:submit` goes to STUDENT and FACULTY (so coordinators inherit it); the service then restricts students to the four student opening types and faculty/coordinators to COLLABORATION (`403`). You can't apply to your own opening (`403`), to one that isn't OPEN or is past its deadline (`409`), or twice (`409`).
6. **The unique constraint is the double-apply guard.** The service doesn't check first and insert second; it inserts and turns the `UNIQUE(opportunity_id, applicant_id)` violation into `409`, so two concurrent submits can't both succeed. A withdrawn application still counts, so you can't re-apply.
7. **Deciding is a resource policy, not a permission.** Only the opportunity's creator changes application status. The coordinator whose department it is and admins can read applications (`GET /opportunities/{id}/applications`, `GET /applications/{id}`) but get `403` on decisions. Other users who can see the opportunity get `403` on its applicant list and `404` on an individual application.
8. **Accepting is one transaction.** Status + decision fields + timeline event + optional `project_members` row (`add_to_project`) + the FILLED transition + the audit row commit together.
9. **An applicant-visible timeline.** `application_events` records every status change with its note. The audit log also records reviewer decisions (`application.<status>`) but isn't readable by applicants.
10. **Deadlines are dates, checked in UTC.** Applying is allowed through the end of the deadline day.

## Consequences

- An opportunity whose project is later archived stays readable, and its project title is shown only to viewers who can still see the project.
- Once FILLED, an opportunity stays filled even if an accepted applicant later leaves the team. Reopening is left for a later step.

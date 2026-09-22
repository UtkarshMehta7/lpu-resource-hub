# ADR 0006: Step 5 research projects and review workflow

- **Status:** Accepted
- **Date:** 2026-09-22
- **Context:** Step 5 adds faculty-owned research projects with a mandatory coordinator review before they go public, plus team members.

## Decisions

1. **One transition table.** `app/modules/projects/policies.py: TRANSITIONS` maps `(from, to)` to the actors allowed to make that move (`owner`, `reviewer`, `admin`). Every status change in the service goes through `assert_transition`; nothing else writes `project.status`. The workflow is readable in one place and can't drift across endpoints.
2. **Invalid transitions are `409`, not `422`.** The request is well-formed; it conflicts with the project's current state (e.g. completing a draft, reviewing something not pending, editing while under review). `422` stays reserved for malformed input (bad dates, rejection without a comment, unknown tag ids).
3. **Visibility lives in the query.** `visibility_filter(viewer)` is part of every `SELECT`: `ACTIVE`/`COMPLETED` are public to signed-in users; `DRAFT`/`PENDING_REVIEW`/`ARCHIVED` are visible only to the owner, team members, the coordinator whose department scope matches, and admins. Hidden rows never leave the database, which also makes `/search` safe for free.
4. **404 / 403 / 409 are distinct on purpose.** A project you can't see is `404` — including a coordinator acting outside their department, which reuses the same visibility filter as the scope check. A project you can see but may not act on is `403` (not the owner; reviewing your own project; submitting while unverified). A valid actor asking for an invalid move is `409`.
5. **Submitting requires a verified researcher profile.** Creating drafts does not — faculty can prepare a project while verification is pending (Step 3).
6. **Reviewers can never approve their own project**, including admins and coordinators who also own projects. Rejection returns the project to `DRAFT` with a required comment, shown to the owner.
7. **Delete is soft and only for drafts.** `DELETE` on a draft sets `deleted_at`; on anything else it archives instead, so an approved project's history is never destroyed.
8. **Project search uses a real generated column.** Unlike researcher profiles (ADR 0005), every input (title A, summary B, description + objectives C) is on the row itself, so `search_document` is a `GENERATED ALWAYS … STORED` tsvector with a GIN index — no rebuild hooks needed.
9. **`department_id` is copied from the owner at creation.** It is what scopes coordinator review; moving the owner to another department later does not move their existing projects.
10. **`project:create` is a FACULTY grant (inherited by coordinators); admins don't author projects.** `project:review` is granted to coordinators and admins.
11. **Reviews and admin archives are audited** (`project.approved`, `project.rejected`, `project.archived`), with the reviewer's comment in the audit payload.

## Consequences

- Editing tags on an existing project replaces them only if new ones are picked; the read schema returns tag names, not ids, so the edit form can't pre-fill the picker.
- There is no UI yet to add team members by searching users (the API supports it); members are added via the API or seed data for now. Opportunities in Step 7 are the main way people will join projects.

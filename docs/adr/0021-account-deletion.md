# ADR 0021: Accounts can be deleted, down the hierarchy, with the cascade shown first

- **Status:** Accepted
- **Date:** 2026-09-24
- **Builds on:** [ADR 0019](0019-account-provisioning-hierarchy.md) (provisioning
  hierarchy), [ADR 0020](0020-identity-on-screen-and-derived-coordinator-scope.md)
  (derived coordinator scope).

## Context

Until now an account could be deactivated but never deleted. That was a
deliberate choice — deleting a coordinator would orphan every verification
they issued — but it left no answer for the case that actually keeps coming
up on a real instance: an account that **should never have existed**. A
mistyped registration number, a duplicate, an account created while testing.
Deactivating it leaves the row in every list forever, and, worse, leaves the
registration number permanently taken, so the person it belongs to can never
be given it.

Deletion is genuinely dangerous here, and not for the obvious reason. Of the
31 foreign keys pointing at `users.id`, **21 cascade**: projects, project
memberships, opportunities, publications, applications, bookings,
collaboration requests, content reports, notifications, saved items, profiles,
skills. Deleting a faculty member silently deletes their projects, and every
application anyone ever made to them. The remaining 10 are `SET NULL`, and
they are exactly the rows that record a *decision about somebody else* —
verifications, project reviews, booking approvals, audit entries.

## Decision

**Removal runs down the same hierarchy as creation, with one asymmetry.**
Creation is limited to a single rung (`CREATABLE_ROLE`): an admin appoints
coordinators, a coordinator appoints faculty, faculty enrol students. Removal
uses `DELETABLE_ROLES`, which is not limited to one rung, because an
administrator answers for the whole platform:

| Actor | May delete |
|---|---|
| Administrator | anyone, at any level, except themselves |
| Research coordinator | faculty and students of the department they oversee |
| Faculty | students of their department, once their own profile is verified |
| Student | nobody |

Scope is the same rule provisioning uses: a coordinator's authority is the
scope an admin gave them, not the department they happen to work in; an
unverified faculty member's self-declared department is not authority over the
people in it.

**Nobody deletes their own account.** This is also what keeps the platform
administrable: only an administrator may delete an administrator, so the last
one could only ever be deleted by themselves — which is refused. A separate
"last administrator" check would be unreachable code, so there isn't one.

**The cascade is counted before it happens.** `GET /users/{id}/deletion-impact`
returns how many projects, opportunities, publications, applications,
memberships, requests, bookings and reports would go with the account, and the
confirmation dialog lists them. It runs the *same* authority check as the
deletion, so it cannot be used to count somebody else's work. Accounts the
person provisioned are reported separately, because those survive — they
simply stop recording who created them.

**The audit entry carries the person, not just their id.** The row is gone
afterwards, so `user.deleted` records the registration number, name, role and
department alongside the impact counts. An id alone would point at nothing.

**A scoped list, so the authority is reachable.** `GET /api/v1/users` returns
the people the caller may remove — a coordinator's department, a faculty
member's students. The list and the buttons on it come from the same rule, so
no row can show a button that answers 403. Without it, coordinators and
faculty would have had the permission and nowhere to use it, since
`GET /admin/users` is admin-only.

## Consequences

- Deleting is now the right answer for a mistyped account, and **the
  registration number becomes free again** — tested explicitly, because that
  is the main reason to prefer it over deactivating.
- Deactivation remains the right answer for a person who has left, and both
  the dialog and the endpoint docstring say so. The distinction is the one
  thing a user could get wrong here at real cost.
- There is a new page, `/people`, for coordinators and faculty. Administrators
  keep the fuller console at `/admin/users`, which gained the same button.
- No schema change and no migration: the cascade rules were already in the
  database, this only exposes them.
- The frontend mirror of the hierarchy (`features/admin/hierarchy.ts`) decides
  only whether to *show* the button; the browser cannot evaluate department
  scope, so an appearing button is not a promise, and a refusal is displayed
  if it comes.

## Alternatives considered

- **Refuse to delete anything with content attached** (409 with a list, delete
  the content first). Safest, and useless for the actual job: an admin
  clearing demo accounts would hit a wall on nearly every row. Showing the
  cost and letting a person decide respects them more than refusing does.
- **Soft delete** (a `deleted_at` column). That is deactivation with extra
  steps: the row stays, so the registration number stays taken, which is the
  problem we set out to solve.
- **Admin-only deletion.** Simpler, and it would mean a coordinator who can
  create a faculty account by mistake cannot undo it — the hierarchy already
  says that appointment is theirs to make.
- **Reassign content to the actor instead of cascading.** Attributing someone
  else's project to whoever deleted them falsifies the record. If the work
  should survive, the account should be deactivated, not deleted.

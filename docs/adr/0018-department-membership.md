# ADR 0018: Who decides which department someone belongs to

- **Status:** Accepted
- **Date:** 2026-09-23
- **Supersedes:** nothing. Extends [ADR 0015](0015-registration-number-sign-in.md).

## Context

`users.department_id` decides a great deal: which coordinator reviews your
work, whose verification queue you land in, which equipment you can book, and
— through `POST /api/v1/users` — which department you may create student
accounts in.

Until now it could only be set **at account creation, by an admin**. Faculty
self-register (ADR 0015) and that path never asks for a department, so every
self-registered researcher had `department_id = NULL` permanently:

- "Add a person" always failed with *"You can only add people to your own
  department"* — the creator had no department to add into.
- Nothing in the API could repair it. `PATCH /api/v1/admin/users/{id}`
  accepted `full_name` and coordinator scope only.

So the platform could produce accounts that no one, including an admin, could
place. That is the bug this ADR resolves.

The obvious fix — let people state their own department — creates a privilege
escalation: a self-registered faculty member could claim any department and
immediately start creating student accounts in it.

## Decision

**A department is self-declared as a claim, and becomes a record when a
coordinator verifies the profile.**

1. **Anyone may state their own department** through `PUT /api/v1/me/profile`
   (`department_id` on both profile shapes). This is the form where you
   already say who you are.

2. **Verification locks it.** Once a researcher profile is `VERIFIED`, the
   holder can no longer move themselves: `409`, with `department_locked: true`
   in the profile response so the UI can explain rather than fail. Students
   never lock, because nothing a student does is department-scoped.

3. **An admin can always set or clear it**, on anyone, verified or not, via
   `PATCH /api/v1/admin/users/{id}` with `department_id`. The change is
   audited as `user.department_changed`.

4. **A claimed department does not by itself grant anything.** Faculty must
   hold a **verified** researcher profile before `POST /api/v1/users` will
   create an account in their department (`403` otherwise). Verification is
   already the human check that this person is who they say they are, in the
   department they say they are in — so it is the right gate.

5. **A coordinator's authority is only the scope an admin gave them.**
   `_creator_department` no longer falls back to a coordinator's own
   `department_id`; an unscoped coordinator gets `403` rather than acting on a
   possibly self-declared value.

Separately, and for the same "an admin must be able to repair an account"
reason: `POST /api/v1/admin/users/{id}/temporary-password` issues a
replacement temporary password (shown once, sessions revoked, account walled
off behind the change-password gate again, audited as `user.password_reset`).
Before this, a lost temporary password could not be replaced at all, although
the UI claimed otherwise.

## Consequences

**Good**

- A self-registered researcher can get themselves unstuck, and an admin can
  fix any account.
- The escalation is closed by a check that already existed and already has a
  human in the loop.
- Both new powers are audited, like every other sensitive action.

**Costs**

- Faculty now need verification before they can add students. That is a new
  wait for a genuinely new researcher, and it is the point.
- `department_locked` is a computed field on the profile response, not a
  column — one extra lookup per profile read.
- An admin may still place someone in a department they don't belong to.
  Nothing detects that; the audit log records who did it.

## Alternatives rejected

- **Ask for a department at registration.** Still self-declared, still
  unverified, and it can never repair the accounts that already exist.
- **Admin-only department assignment.** Safe, but it makes every new
  researcher wait on an administrator for something they know and the admin
  doesn't.
- **A `department_source` column** distinguishing declared from assigned.
  More precise, but it needs a migration and a second concept to reason
  about, when "verified or not" already carries the same information.

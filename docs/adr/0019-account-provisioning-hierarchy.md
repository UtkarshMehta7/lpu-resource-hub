# ADR 0019: Accounts are provisioned down the institutional hierarchy

- **Status:** Accepted
- **Date:** 2026-09-23
- **Supersedes:** the self-registration half of [ADR 0015](0015-registration-number-sign-in.md).
  Everything else in 0015 (registration-number sign-in, temporary passwords,
  the change-password gate) stands. Builds on
  [ADR 0018](0018-department-membership.md).

## Context

This is a university's internal research platform, not a public network. Who
belongs to it, and in what capacity, is an institutional fact — yet the
platform let people assert it themselves:

- `POST /api/v1/auth/register` was public and created a `FACULTY` account for
  anyone who filled in the form. A `/register` page was linked from the
  landing page twice, the header and the login page.
- `POST /api/v1/users` took a `role` field. An admin could pass any role, and
  the endpoint's job was to check whether the caller was allowed that value —
  a guard standing in front of an open door.

Two things follow. A stranger could become "faculty" at LPU by typing a
registration number, with nothing but a coordinator's later verification
standing between them and the directory. And every account-creation request
carried a client-supplied privilege level, which is the shape of problem that
only stays solved while every branch of the check stays correct.

## Decision

**Nobody signs themselves up. Each role provisions exactly the role below it,
and the role of a new account is derived from its creator rather than
requested.**

```
ADMIN ──appoints──▶ RESEARCH_COORDINATOR ──appoints──▶ FACULTY ──enrols──▶ STUDENT
```

1. **Self-registration is gone**, not disabled: the route, the request schema,
   the service function, the React page, the router entry and every link to it
   are deleted. `POST /api/v1/auth/register` returns `404` because nothing is
   mounted there, and the OpenAPI document advertises no such path. There is
   no dormant endpoint left to re-enable by accident.

2. **`CREATABLE_ROLE` in `app/core/permissions.py` is the single authority**
   on who may create whom. One table, consulted by one service.

3. **`AccountCreateRequest` has no `role` field.** The role comes from
   `creatable_role(creator.role)`. A request cannot ask for a role at all, so
   there is no forged role to reject — the escalation class is removed rather
   than guarded. A `STUDENT` maps to `None` and gets `403`.

4. **Scope is unchanged and still enforced.** An admin names the department a
   new coordinator will oversee (required: a coordinator with no scope
   oversees nothing, and the appointment sets `coordinator_scope_*` in the
   same breath). A coordinator provisions into the department they oversee and
   nowhere else. A faculty member provisions into their own department, and
   only once their researcher profile is verified (ADR 0018). A department
   someone doesn't own is refused, not quietly ignored.

5. **`users.created_by`** (migration 0016) records the chain, so the database
   answers "who let this person in" without a second table. `SET NULL` on
   delete: removing a coordinator must never remove the faculty they
   appointed.

6. **The frontend names the act, not the abstraction.** One route, but the
   navigation and heading read "Add coordinator", "Add faculty" or "Add
   student" depending on who is looking. There is no role dropdown to get
   wrong. These labels mirror `CREATABLE_ROLE`; they decide wording only, and
   the backend would refuse regardless.

## What the admin actually sees

The hierarchy is only real if the person at the top can act on it, so this
step also added the pages that were missing:

- **`/admin` — Administration.** The admin's home: the provisioning chain with
  their place in it, one primary action ("Add coordinator"), live counts per
  role, and every privilege they hold, grouped and linked. Each privilege is
  re-checked on the server; the page lists them, it does not grant them.
- **`/admin/coordinators`.** Who oversees which department, which is the whole
  of a coordinator's authority.
- **`/admin/organisation`.** Schools and departments. These endpoints existed
  from Step 3 but had no UI at all, which — once a coordinator must be
  appointed *to* a department — left a fresh install unable to create anyone
  without curl.

## Administering the administrators

Two later additions, driven by the same question — who is allowed to hand out
power, and what stops one stolen session from doing it:

- **`/admin/login`.** A separate entrance for administrators, landing on
  `/admin` rather than a dashboard. It is a distinct door, not a stronger
  lock: same credentials, same endpoint, same rate limit. The page says so,
  so nobody mistakes the URL for a boundary.
- **`/admin/accounts/new` — the override.** `POST /api/v1/admin/users` is the
  one endpoint where a role may be named, admin-only, for what the hierarchy
  cannot serve: a department with no coordinator yet, a correction, a second
  administrator. It is audited as `user.created_by_admin`, so an override
  never reads as an ordinary appointment.
- **`/admin/administrators` — promotion takes two people.** An admin opens a
  challenge; a six-digit code goes to the *target's* notification inbox, never
  the requester's; the promotion completes only when the admin enters what the
  target reads back. The code is stored as a SHA-256 hash, expires in ten
  minutes, works once, and dies after five wrong guesses. An admin may also
  **step down**, refused while they are the last active one — so a handover is
  promote-then-stand-down, and the platform is never left without an
  administrator.

The code rides the existing notification system, so there is no email or SMS
provider and no cost. That also means its security rests on the target's
account, not on a second device: it proves *the target participated*, not that
a phone was in someone's hand. That is the property worth having here — it is
what stops one compromised admin session from quietly minting another admin.

## Consequences

**Good**

- The privilege-escalation surface on account creation is gone rather than
  defended: there is no field to attack.
- The authorization rule lives in one table instead of being spread across
  branches in a service.
- The provisioning chain is queryable, which is what an institution wants when
  asking how an account came to exist.
- The UI stops asking people to pick a role they shouldn't be choosing.

**Costs**

- **An admin can no longer create a faculty member or student directly.** They
  appoint a coordinator, who appoints faculty. For a correction, the existing
  audited `POST /admin/users/{id}/role` still exists. This is deliberate: the
  alternative is an admin-shaped hole in the hierarchy the ADR exists to
  establish.
- The first admin still has to come from `scripts/create_admin.py`. There is no
  way to bootstrap one through the API, by design.
- Existing self-registered accounts keep working and keep their roles; they
  simply have no `created_by`. Nothing is deleted.

## Alternatives rejected

- **Keep `role` in the request and validate it** against a matrix. This is what
  was there. It works until one branch is wrong, and it means every request
  still carries a privilege claim.
- **Three endpoints** (`/coordinators`, `/faculty`, `/students`). Explicit, but
  three routers, three schemas and three sets of scope checks to keep in step,
  for a distinction the caller's role already makes.
- **Keep public registration behind an invite code.** Another secret to
  distribute and revoke, and it still lets the holder choose when and as whom
  to appear.

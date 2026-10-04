# ADR 0028: Reconciling the role model with the specification

- **Status:** Accepted
- **Date:** 2026-10-04

## Context

The specification names six kinds of person:

> **Faculty Researcher** — own profile, projects, openings, bookings,
> collaboration interests. **Research Student** — browse openings, apply,
> participate in assigned projects. **Facility Custodian** — facility records,
> approve bookings, log utilisation. **Research Office** — verify profiles,
> maintain funding calls, run reports. **Dean of Research** — institutional
> analytics, at-risk projects. **Administrator** — expertise taxonomy,
> matching configuration.

This platform had four: `STUDENT`, `FACULTY`, `RESEARCH_COORDINATOR`, `ADMIN`.

The temptation is to add the two missing names and be done. That would be
wrong in one case and a real omission in the other two, so each was decided
separately.

## Decisions

### Research Office is the existing Research Coordinator. Not added.

The specification's Research Office *"verifies profiles, maintains funding
calls, runs reports"*. `RESEARCH_COORDINATOR` already holds exactly
`PROFILE_VERIFY`, `FUNDING_MANAGE` and `ANALYTICS_READ`, scoped to its
department.

Adding `RESEARCH_OFFICE` would create two names for one responsibility, and
every future permission decision would have to be made twice and kept in step.
The brief's own warning applies: *"Do not blindly add duplicate roles if the
existing role model already represents the same responsibility under another
name."*

Where the two genuinely differ is scope — a Research Office might be
institution-wide where a coordinator is departmental. That distinction is
already expressible: `coordinator_scope_type` admits `SCHOOL` and
`UNIVERSITY` as well as `DEPARTMENT`. It needs no new role.

### Facility Custodian is added, and it exposed a real hole.

`Permission.FACILITY_MANAGE` said a person may manage *a* facility. Nothing
said **which**. With only coordinators and admins holding it that was
tolerable — a coordinator was scoped by department — but it meant the
permission alone conferred authority over every facility in reach.

The role is therefore added **with** `facilities.custodian_id`, and facility
and equipment changes now go through an object-level check against the loaded
row rather than a department comparison. A custodian of the Soil Lab cannot
edit the Electron Microscopy Suite, and a booking in a facility that is not
theirs is a **404** rather than a 403 — being refused should not teach them
which bookings exist elsewhere.

Equipment inherits its facility's custodian: whoever looks after the room
looks after what is in it.

### Dean of Research is added, read-only.

The specification says institutional analytics *"are easily misused and access
should be restricted to the Dean of Research"*. There was no role that rule
could bind to.

`DEAN_OF_RESEARCH` holds exactly one permission, `ANALYTICS_READ`, and
`scope_for` treats it as institution-wide. The point of the role is that
senior figures can see the institution's numbers **without** acquiring the
ability to edit the records behind them, so it creates nobody, verifies
nobody, reviews nothing and manages no facility.

### Neither role inherits from Faculty

`ROLE_HIERARCHY` maps both to `None`. A custodian is not a researcher who also
keeps a store room, and a dean is not a coordinator with a wider view —
inheriting the faculty grants would hand either the ability to create student
accounts and publish projects.

### Appointment goes through the admin override, not the hierarchy

`CREATABLE_ROLE` maps each role to **one** successor, which is what lets the
new account's role be *derived* from its creator and never read from the
request. The moment a role has two possible successors, the role has to be
named in the request — reintroducing exactly the client-supplied role the
design exists to avoid.

So custodians and deans are appointed through `POST /api/v1/admin/users`, the
override that already exists for naming a role and is audited under its own
action.

That route was also **tightened**: an administrator may now appoint any role
*except* another administrator. Promotion to admin remains the two-person
ceremony of ADR 0019; before this, the override was a one-click way around it.

### The at-risk board moved from PROJECT_REVIEW to ANALYTICS_READ

A board of slipping projects is something to read, not an action on a project.
Gating it behind the review permission would have meant a dean could only see
at-risk work by also being able to approve and reject it. No existing holder
lost access: coordinators and admins have both permissions.

## Consequences

- Migration `0026` adds the two `user_role` values by hand (autogenerate never
  sees enum members) and the `facilities.custodian_id` column. Its downgrade
  **refuses to run** while any account still holds one of the new roles —
  dropping the enum value is impossible and such an account would become
  unreadable.
- The booking queue is now filtered by `manageable_facility_filter` — the same
  rule `may_manage_facility` enforces per row, expressed as a query predicate —
  rather than by a department comparison. Two code paths over one rule is how
  a queue ends up offering a request the approve call refuses, or hiding one
  that is waiting for nobody; both directions are tested.
- `INSTITUTION_WIDE_ROLES` lets an administrator and a dean exist without a
  department. Everyone else still needs one, or no scoped rule can reach them.
- The interface follows the permissions rather than the other way round: a
  custodian reaches the booking queue and the equipment form (the server
  scopes both to the facilities they hold) and nothing else in Review; a dean
  reaches analytics, the research report and the at-risk board and no queue
  that acts on somebody's work. Creating a facility stays department-level, so
  a custodian — who holds facilities, not a department — is not offered it.
- Both new roles sign in at the ordinary entrance; only administrators use
  `/admin/login` (ADR 0020), and that is asserted.
- The role matrix in `docs/rbac-matrix.md` is updated, and
  `tests/test_role_model.py` tests every boundary against the API directly —
  hiding a menu item is not a permission.

## Correction, same day: the role was enforced but unassignable

The first version of this shipped `facilities.custodian_id` and enforced it
everywhere -- the object-level check, the queue filter, the 404s -- but
provided **no way to set it**. It was absent from `FacilityUpdate` and from
`FacilityRead`, so no endpoint could write it and no page could show it. The
tests passed because the fixture wrote the column with raw SQL under a
comment deferring the endpoint to "Phase 6".

The effect was a role that could be created and never used: an administrator
could appoint a custodian, but nobody could give them a room, so their scope
stayed empty for ever. Enforcing a permission is not the same as making it
reachable, and a test fixture that reaches past the API hides exactly that
difference.

Assignment is therefore `PUT /facilities/{id}/custodian`, with
`GET /facilities/{id}/custodian-candidates` behind the same gate to populate
the choice. Four decisions worth recording:

- **Its own endpoint, not a `FacilityUpdate` field.** A custodian passes the
  object-level check for their own facility, so an assignment folded into the
  ordinary edit would let them hand the room to somebody else, or take a
  colleague's. Deciding *who holds* a facility is a different act from
  renaming it.
- **Gated at department level** (`assert_can_manage`), deliberately not at the
  object level the rest of the module uses. Only an admin, or the coordinator
  of the department that runs the facility, may decide who holds it -- and a
  custodian holds no department, so they are excluded by construction rather
  than by a role check somebody can forget.
- **The target must be an active account holding the role**, and must belong to
  the department that runs the facility. Pointing the column at a faculty
  member would leave a facility looking looked-after by somebody with no
  `facility:manage` at all; pointing it outside the department would put the
  custodian beyond the reach of the coordinator who oversees those rooms --
  the "coordinator oversees nothing" bug in a new place.
- **Audited both ways**, `facility.custodian_assigned` and
  `facility.custodian_cleared`. A change of authority, not of a label.

The candidate list is filtered by the same rules the assignment enforces, so
the picker cannot offer somebody the assignment would then refuse -- the same
reasoning as `manageable_facility_filter` and the booking queue.

The interface carried the same conflation: `canManage` on the facility page
was `coordinator || admin`, which hid the management controls from a custodian
on their own facility. It is now the object-level rule, with assignment kept
separate.

## What was deliberately not done

No permission was widened to make a role fit. Where the specification's
wording did not match an existing capability — "log utilisation", for
instance, which this platform derives from approved bookings rather than
recording by hand — the capability was left as it is and the difference noted
rather than a new write path invented for the sake of the word.

# ADR 0030: A coordinator appoints facility custodians

- **Status:** Accepted
- **Date:** 2026-10-04

## Context

ADR 0028 added `FACILITY_CUSTODIAN` and made it appointable only through the
admin override. In use that turned out to be a dead end: a research
coordinator can **assign** a custodian to a facility (ADR 0028's correction)
and can **see** the picker say *"No facility custodian accounts exist for this
department yet"* — and could do nothing about it. The next step was always an
administrator's inbox.

The obvious fix is to let `CREATABLE_ROLE` map a coordinator to two
successors. That cannot be done.

`CREATABLE_ROLE` maps each role to **exactly one** successor, and that
property is load-bearing: it is what lets a new account's role be *derived
from the caller* and never read from the request. `AccountCreateRequest` has
no `role` field at all, deliberately, and ADR 0028 says so in as many words —
*"the moment a role has two possible successors, the role has to be named in
the request"*. Reintroducing it would undo the thing the design exists for.

## Decision

The role becomes a **constant of the route** instead of a field in the body.

`POST /api/v1/facility-custodians` can only ever create a
`FACILITY_CUSTODIAN`. The request carries `registration_number`, `full_name`,
`department_id` and `email` — and no role. A caller still names nothing; the
path does.

`CUSTODIAN_APPOINTERS` (`RESEARCH_COORDINATOR`, `ADMIN`) says who may call it.
A separate, explicit table rather than an inference from permissions, for the
same reason `DELETABLE_ROLES` and `APPOINTABLE_BY_ADMIN` are tables: the
answer should be readable in one place.

**A custodian is deliberately absent from it.** Somebody who looks after rooms
must not be able to mint peers who look after other rooms; that is an
institutional act, not a facilities one.

Scope is unchanged and reuses the existing branch: a coordinator appoints only
within the department they oversee — the same rule that governs them
appointing faculty — and a department they try to name that is not theirs is
rejected rather than quietly ignored. An administrator appoints anywhere.

### Removing, too

`DELETABLE_ROLES[RESEARCH_COORDINATOR]` gains `FACILITY_CUSTODIAN`. Creating
without removing is the same dead end in the other direction, and the scope
check that already governs a coordinator deleting faculty applies unchanged.

## Consequences

- `CREATABLE_ROLE` is untouched, and a test asserts every role still has at
  most one successor. The derived-role invariant holds.
- A `role` sent in the body of the new route is ignored rather than honoured,
  which is tested — the schema has no such field, and silently accepting one
  would be the beginning of the thing this avoids.
- `/people/custodians/new` is in `components/layout/navigation.ts` for both
  roles, and linked from the facility picker's empty state, which is where
  somebody actually discovers they need it.
- The page offers no role to choose, because there is nothing to choose.

## What was deliberately not done

No change to the provisioning chain itself. A coordinator still creates
faculty by the ordinary derived path, and the two mechanisms stay distinct:
one derives a role from who you are, the other is a named appointment with its
own route and its own audit trail.

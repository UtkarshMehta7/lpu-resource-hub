# RBAC matrix

The full role → permission design for the platform. `app/core/permissions.py`
only ever contains what a built module actually enforces (no speculative
code) — this document is the forward-looking picture: every permission any
step is expected to introduce, marked with the step that adds it. Once a
step is implemented, `ROLE_PERMISSIONS` in code should match this table for
everything up to and including that step.

## Roles and hierarchy

`STUDENT`, `FACULTY`, `RESEARCH_COORDINATOR`, `FACILITY_CUSTODIAN`,
`DEAN_OF_RESEARCH`, `ADMIN` (`docs/architecture.md` §1). The first three and
`ADMIN` form the provisioning chain; the other two are narrow, non-inheriting
appointments described in their own section below (ADR 0028).

`RESEARCH_COORDINATOR` inherits every `FACULTY` permission plus its own
(coordinator-specific: review/approve actions, scoped to their department —
see "Coordinator scope" below). `ADMIN` has its own explicit operational and
moderation powers; it does not automatically inherit `FACULTY`'s or
`RESEARCH_COORDINATOR`'s permissions (an admin acting on a research resource
would do so through the same permission a coordinator uses, granted to
`ADMIN` explicitly where that's the intended design).

## Coordinator scope

A `RESEARCH_COORDINATOR` acts within a scope: `coordinator_scope_type`
(`department` | `school` | `university`) + `coordinator_scope_id` on the
`users` row (Step 2). Department-level is what's actually used today; the
type exists so scope can widen later without a schema change. A permission
check alone (`require_permission`) only proves the role *can* perform the
action in general — the resource policy layer (loaded-resource ownership +
scope match, `docs/architecture.md` §6 layer 2) is what enforces *this
specific* department/project/etc., introduced per-module starting Step 3.

## Account provisioning (ADR 0019)

`user:create` says *whether* you may bring someone in; **who** you create is
decided by `CREATABLE_ROLE` in `app/core/permissions.py` and never by the
request, which carries no role field at all.

| Signed in as | Creates | Scope |
|---|---|---|
| `ADMIN` | `RESEARCH_COORDINATOR` | any department; it becomes the new coordinator's scope |
| `RESEARCH_COORDINATOR` | `FACULTY` | the department they oversee |
| `FACULTY` | `STUDENT` | their own department, verified profile required |
| `STUDENT` | — | — |

`FACILITY_CUSTODIAN` and `DEAN_OF_RESEARCH` create nobody, and nobody's
ordinary chain creates them: they are appointed through the admin override
(`POST /api/v1/admin/users`), whose permitted set is `APPOINTABLE_BY_ADMIN`.
That set is every role except `ADMIN` — promotion to administrator stays the
two-person ceremony at `/admin/administrators` (ADR 0019), and allowing it in
the override would be a one-click route around it.

There is no public registration endpoint. Nobody, at any level, can change
their own role: that is `user:update_role`, an admin action on someone else,
refused on self and audited.

## Implemented (Steps 2–13)

| Permission | STUDENT | FACULTY | COORDINATOR | ADMIN | Step |
|---|:-:|:-:|:-:|:-:|:-:|
| `user:create` | | ✅ → students, own dept, verified profile only | ✅ → faculty, assigned scope only | ✅ → coordinators | 13+ |
| `user:list` | | | | ✅ | 2 |
| `user:update` | | | | ✅ | 2 |
| `user:update_role` | | | | ✅ | 2 |
| `user:activate` | | | | ✅ | 2 |
| `user:deactivate` | | | | ✅ | 2 |
| *(no permission)* conversation threads | participant only | participant only | participant only | participant only | 22 |
| `user:delete` | | ✅ → students, own dept, verified profile only | ✅ → faculty + students, assigned scope only | ✅ → anyone but themselves | 21 |
| `audit:read` | | | | ✅ | 2 |
| `school:manage` | | | | ✅ | 3 |
| `department:manage` | | | | ✅ | 3 |
| `taxonomy:manage` | | | ✅ | ✅ | 3 |
| `profile:verify` | | | ✅ (own dept) | ✅ (any) | 3 |
| `student:discover` | | ✅ | ✅ (inherited) | ✅ | 4 |
| `project:create` | | ✅ | ✅ (inherited) | | 5 |
| `project:review` | | | ✅ (own dept, never own project) | ✅ (never own project) | 5 |
| `publication:create` | | ✅ | ✅ (inherited) | | 6 |
| `opportunity:create` | | ✅ (own active project) | ✅ (inherited; also department-wide) | | 7 |
| `application:submit` | ✅ (student openings) | ✅ (collaborations) | ✅ (inherited) | | 7 |
| `collaboration:send` | ✅ | ✅ | ✅ (inherited) | | 8 |
| `report:moderate` | | | ✅ | ✅ | 10 |
| `facility:manage` | | | ✅ (own dept) | ✅ (any) | 11 |
| `booking:approve` | | | ✅ (own dept) | ✅ (any) | 11 |
| `funding:manage` | | | ✅ (university-wide) | ✅ | 12 |
| `analytics:read` | | | ✅ (own dept figures) | ✅ (platform) | 14 |
| `publication:deduplicate` | | | ✅ | ✅ | 29 |
| `announcement:post` | | | ✅ (own department) | ✅ (institution) | 38 |
| *(no permission)* reading the notice board | ✅ | ✅ | ✅ | ✅ | 38 |

Every authenticated, active user (any role) can read their own profile via
`GET /api/v1/me`, read their own `GET/PUT /me/profile`, set their own
`/me/skills` and `/me/research-areas`, search the taxonomy
(`GET /skills`, `GET /research-areas`) and suggest a tag
(`POST /tags/suggestions`) — those aren't permission checks, just
authentication.

`profile:verify` is the first permission where the permission check alone
isn't the whole story: a coordinator passes it for *any* researcher, and the
resource policy (`app/modules/researchers/policies.py`) then restricts them
to their own department — returning `404`, not `403`, so they can't probe
for profiles outside their scope.

Deciding an application isn't a permission: it's a resource policy. Only
the opportunity's creator may change an application's status; the scoped
coordinator and admins can read applications but not decide them.

## Planned (later steps)

Not yet in `core/permissions.py`. Listed here so the shape of the eventual
map is visible; each will be added by its own step, with `COORDINATOR`
picking it up automatically via inheritance wherever `FACULTY` has it.

| Permission | STUDENT | FACULTY | COORDINATOR | ADMIN | Step |
|---|:-:|:-:|:-:|:-:|:-:|
| `project:archive` | | ✅ (own) | | ✅ | 5 |

## Two scoped, non-inheriting roles (ADR 0028)

Both exist because a permission was being used to mean more than it says.
Neither inherits anything, and neither appears in `CREATABLE_ROLE`, so
appointing one cannot happen by accident.

| | `FACILITY_CUSTODIAN` | `DEAN_OF_RESEARCH` |
|---|---|---|
| Holds | `facility:manage`, `booking:approve` | `analytics:read` |
| Scope | the facilities whose `custodian_id` is them | the whole institution |
| Department | required, like everyone but a dean | none (`INSTITUTION_WIDE_ROLES`) |
| Creates | nobody | nobody |
| Deletes | nobody | nobody |
| Signs in at | `/login` | `/login` |

**Assignment is department-level, not object-level.**
`PUT /facilities/{id}/custodian` is gated by `assert_can_manage`, so only an
admin or the department's coordinator decides who holds a facility. A
custodian passes the *object* check for their own facility, so reusing it
would let them hand the room away or seize a colleague's; they hold no
department, so the department-level gate excludes them by construction. The
target must be an active `FACILITY_CUSTODIAN` in the facility's own
department, and both assigning and clearing are audited.

`facility:manage` says a person may manage *a* facility; it never said
*every* facility, and before this role nothing needed the distinction because
the only holders were scoped by department. A custodian's scope is a **set of
rows**, so it is enforced object-level against the loaded facility
(`facilities/policies.py: may_manage_facility`) rather than by a column
comparison in the dependency. `manageable_facility_filter` is the same rule as
a query filter, used by the booking queue so a listing can never show a
request the approve call would then refuse. A booking on somebody else's
facility is a `404`.

A dean changes no record. `analytics:read` is the reading grant, and
`insights.scope_for` puts them in the same institution-wide scope as an
admin. They reach `/analytics`, `/analytics/report` and the at-risk board
(whose gate moved from `project:review` to `analytics:read`, since looking at
the board is reading, not reviewing) — and no other queue, because every
other one is an action on somebody's work.

They also hold **`announcement:post`** (ADR 0038), which is the one thing the
role writes. A notice is not a record: it creates no publication, patent,
project or profile and alters none. The role exists so somebody senior can see
the whole institution, and being unable to tell it anything was the other half
of that job missing. A dean's notice is institution-wide, because
`INSTITUTION_WIDE_ROLES` is what `reach_of` keys on.

## Curating publication records (ADR 0029)

`publication:deduplicate` is the duplicate review queue: scanning for
suspected duplicate publications and deciding each pair. Held by
`RESEARCH_COORDINATOR` and `ADMIN`.

Separate from `publication:create` because writing your own record and merging
somebody else's are different powers. A **dean is excluded deliberately** —
they read the institution's figures and change nothing, and a merge changes
the records behind the figures.

A merge deletes the losing record rather than hiding it, because publications
are read in fifteen places across eight modules and one query that forgot to
exclude a hidden row would be a ghost publication still answering searches.
The deleted record is snapshotted on the review row, so the merge is
reversible; an undo recreates it with a new id.

## Status codes

`401` — missing or invalid token (`get_current_user`, before any permission
check runs). `403` — authenticated but `require_permission` denies it, or a
resource policy denies it. `404` — the user must not learn the resource
exists at all (e.g. a student requesting another student's private draft).

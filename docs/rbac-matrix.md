# RBAC matrix

The full role → permission design for the platform. `app/core/permissions.py`
only ever contains what a built module actually enforces (no speculative
code) — this document is the forward-looking picture: every permission any
step is expected to introduce, marked with the step that adds it. Once a
step is implemented, `ROLE_PERMISSIONS` in code should match this table for
everything up to and including that step.

## Roles and hierarchy

`STUDENT`, `FACULTY`, `RESEARCH_COORDINATOR`, `ADMIN` (`docs/architecture.md`
§1). `RESEARCH_COORDINATOR` inherits every `FACULTY` permission plus its own
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

## Status codes

`401` — missing or invalid token (`get_current_user`, before any permission
check runs). `403` — authenticated but `require_permission` denies it, or a
resource policy denies it. `404` — the user must not learn the resource
exists at all (e.g. a student requesting another student's private draft).

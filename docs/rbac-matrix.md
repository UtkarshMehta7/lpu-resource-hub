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

## Implemented (Step 2)

| Permission | STUDENT | FACULTY | COORDINATOR | ADMIN |
|---|:-:|:-:|:-:|:-:|
| `user:list` | | | | ✅ |
| `user:update` | | | | ✅ |
| `user:update_role` | | | | ✅ |
| `user:activate` | | | | ✅ |
| `user:deactivate` | | | | ✅ |
| `audit:read` | | | | ✅ |

Every authenticated, active user (any role) can read their own profile via
`GET /api/v1/me` — that isn't a permission check, just authentication.

## Planned (later steps)

Not yet in `core/permissions.py`. Listed here so the shape of the eventual
map is visible; each will be added by its own step, with `COORDINATOR`
picking it up automatically via inheritance wherever `FACULTY` has it.

| Permission | STUDENT | FACULTY | COORDINATOR | ADMIN | Step |
|---|:-:|:-:|:-:|:-:|:-:|
| `profile:verify` | | | ✅ (own dept) | ✅ | 3 |
| `taxonomy:manage` | | | ✅ | ✅ | 3 |
| `project:create` | | ✅ (verified) | ✅ | | 5 |
| `project:review` | | | ✅ (own dept, never own project) | ✅ | 5 |
| `project:archive` | | ✅ (own) | | ✅ | 5 |
| `publication:create` | | ✅ | ✅ | | 6 |
| `opportunity:create` | | ✅ (own active project) | ✅ | | 7 |
| `application:decide` | | ✅ (own opportunity) | ✅ | | 7 |
| `application:submit` | ✅ | | | | 7 |
| `collaboration:send` | ✅ | ✅ | ✅ | | 8 |
| `facility:manage` | | | ✅ | ✅ | 11 |
| `booking:approve` | | | ✅ | ✅ | 11 |
| `funding:manage` | | | ✅ | ✅ | 12 |
| `report:moderate` | | | ✅ | ✅ | 14 |

## Status codes

`401` — missing or invalid token (`get_current_user`, before any permission
check runs). `403` — authenticated but `require_permission` denies it, or a
resource policy denies it. `404` — the user must not learn the resource
exists at all (e.g. a student requesting another student's private draft).

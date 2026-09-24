# Architecture: LPU Research Intelligence & Collaboration Hub

This is the living source of truth for the approved architecture. Change it through reviewed commits, and record significant decisions as ADRs in [`adr/`](adr/).

> Prototype platform for the LPU ecosystem. It is not an official LPU system unless formally adopted or authorized. All data is fictional demo data.

## 1. Approved product decisions

| Decision | Outcome |
|---|---|
| Submission scope | MVP, then facilities/equipment/booking, then funding/notifications/deadline reminders. Semantic AI, analytics and advanced moderation are advanced scope. |
| Roles | `STUDENT`, `FACULTY` (researcher), `RESEARCH_COORDINATOR`, `ADMIN` |
| Faculty onboarding | A Research Coordinator provisions the faculty of the department they oversee. The coordinator must then verify the researcher profile before that faculty member can publish projects or opportunities, or enrol students. |
| Accounts and sign-in | Everyone signs in with their LPU registration number (UMS-style); email is optional contact information. **Nobody self-registers**: accounts are provisioned down the hierarchy — admin → coordinator → faculty → student — each with a temporary password the new user must replace before using anything (ADR 0015, ADR 0019). The first admin comes from `scripts/create_admin.py`. |
| Coordinator scope | Department-level initially. Stored so it can extend to school-level or university-wide without schema redesign. The service layer keeps it equal to the coordinator's department (`admin/service.py::_sync_coordinator_scope`), because a coordinator with no scope oversees nothing: an empty verification queue and 403 on every decision. Migration 0018 repaired the coordinators appointed before that, and the users page shows each coordinator's scope so a missing one is visible rather than silent. |
| Collaborating | One relationship per unordered pair of people, stored normalised behind a unique constraint so a second one is impossible rather than merely guarded (ADR 0023). Requests are events against it. States: none → requested → active → ended, and ended → requested again; declining or cancelling returns to none, because a question answered no is not a relationship. One conversation per pair for the life of the pair, so collaborating again reopens the same thread instead of splitting two people's history. A request may name a project as context, but the relationship stays pair-level. |
| Ending a collaboration | It takes two to start one and one to stop it: either party may end an ACCEPTED request, because requiring both to agree would mean nobody could ever leave. The thread stays readable and takes no new messages -- what was said still happened. Project threads never close this way; a project has its own lifecycle (ADR 0022). |
| Talking to each other | Conversation threads are scoped to a relationship that already exists: one per accepted collaboration request, one per project team. No open inbox, so no new way to reach somebody who never agreed to be reachable, and `can_contact` still governs who may be approached in the first place. A non-participant gets 404, never 403 -- a 403 on a thread id would confirm that two named people are talking. New messages arrive by polling (10s while the thread is open, paused when the tab is hidden), not over a socket: sync SQLAlchemy, no Redis, and a free instance that sleeps (ADR 0022). Moderation hides a message and never deletes it, so a thread keeps its shape. |
| Removing an account | Deactivation and deletion are different answers. Deactivation: the person has left; the account stops working, their work and their name on decisions stay. Deletion: the account should never have existed; the row goes and the registration number is free again. Removal follows the creation hierarchy, except that an administrator may remove anyone but themselves (`DELETABLE_ROLES`, ADR 0021). 21 of the 31 foreign keys to `users.id` cascade, so `GET /users/{id}/deletion-impact` counts what would be destroyed and the confirmation shows it. `GET /api/v1/users` lists the people a caller may remove, so the list and the buttons cannot disagree. |
| Showing who someone is | A name alone does not identify a person at university scale, so every place the interface names a student, researcher, coordinator or administrator also shows their registration number (`components/ui/Uid`), and the directory search matches on it as well as on names. Every person-bearing API response therefore carries `registration_number`. |
| Student discoverability | Opt-in. Faculty and coordinators can discover opted-in students; only public profile fields are exposed. |
| Project approval | Every project passes coordinator review (`PENDING_REVIEW`) before it becomes `ACTIVE` and can accept applications. |
| Development OS | macOS. The repository itself stays platform-neutral. |
| Cost | ₹0: local PostgreSQL, local open-source ML, no paid APIs, Docker optional. |

## 2. System architecture

```
Browser: React + TypeScript SPA (Vite, Tailwind, React Router, Axios)
   │  HTTPS / JSON
   ▼
FastAPI modular monolith
   routers → dependencies (auth, permissions) → services → SQLAlchemy
   domain events → notifications / audit
   recommendation engine (pluggable strategy)
   in-process scheduler (deadline reminders)
   storage interface (local disk now, S3-compatible later)
   │
   ▼
PostgreSQL: relational data, full-text search, pg_trgm, btree_gist, pgvector (later)
```

Key choices:

- **Modular monolith.** One deployable. Clear module boundaries allow the ML layer to be split out later.
- **No Redis or Celery.** In-memory rate limiting, an in-process scheduler and synchronous events, all behind interfaces so they can be replaced later.
- **Sync SQLAlchemy 2.0 + psycopg 3.** FastAPI runs sync endpoints in a threadpool. Simpler to write and test; async can be adopted per module later.

## 3. Backend structure

```
backend/app/
  main.py        create_app() factory, lifespan, middleware, router mounting
  core/          config, logging, errors (and later: security, deps, permissions, events, pagination, storage)
  db/            declarative base, engine/session
  modules/<name>/
    router.py      HTTP only: parse input, call service, return schema
    schemas.py     Pydantic request/response models (no ORM leakage)
    models.py      SQLAlchemy models
    service.py     business rules, state transitions, domain events
    repository.py  non-trivial queries (optional)
    policies.py    ownership and scope checks
```

Rules:

- Routers contain no business logic.
- Services never import FastAPI.
- Workflow transitions live in one table per workflow.

Planned modules: auth, users, profiles, taxonomy, researchers, projects, publications, opportunities, applications, collaborations, recommendations, search, facilities, bookings, funding, notifications, analytics, admin, audit, reports.

Added after v1.0.0: **messages** (conversation threads, ADR 0022). Not a
variant of collaborations -- a project thread has no request behind it --
and not a variant of notifications, which are one-way.

Two Step 10 features land inside existing modules rather than new ones:
saved items live in `profiles` (personal collections under `/me/...`) and
the role dashboards live in `analytics` (`GET /me/dashboard`), which is the
module that later grows the Step 14 analytics.

**Implemented in Step 0:** only `modules/health`.

## 4. Frontend structure

```
frontend/src/
  app/            App, router, layouts, (later) providers
  components/     layout/ and ui/ design-system primitives
  features/<name>/ api.ts, hooks, components, pages, types
  lib/            config, api client, error normalisation
  types/          (Step 1) generated OpenAPI types
```

- Server state will use TanStack Query (added in Step 1), with local state for everything else. No Redux.
- Forms will use React Hook Form with Zod (Step 1). The backend stays authoritative for validation.
- One Axios instance. Feature modules call typed functions and never use Axios directly.
- Route guards (`ProtectedRoute`, `RoleRoute`) only hide UI; **security is enforced on the backend**.

## 5. Authentication (Step 1)

- Argon2id password hashing.
- Access JWT: 15 minutes, held in memory only.
- Refresh token: opaque, 7 days, in an `httpOnly; Secure; SameSite` cookie scoped to `/api/v1/auth`. Stored as a SHA-256 hash, rotated on every use, with reuse detection that revokes the whole token family.
- Every request reloads the user from the database, so role and `is_active` come from trusted data, never from the client.

## 6. Authorization (Step 2)

Three backend layers:

1. **Permission check.** A route dependency: `require_permission("project:approve")` against a code-defined role→permission map.
2. **Resource policy.** Ownership and coordinator scope, checked after loading the resource. Includes "never approve own project".
3. **Query scoping.** Hidden rows never leave the database.

Status codes: `401` for a missing or invalid token; `403` when the user may see the resource but not perform the action; `404` when the user must not learn it exists. Authorization tests are generated from the permission matrix.

## 7. Database conventions

- UUID primary keys (`gen_random_uuid()`); `created_at` and `updated_at` as `timestamptz`.
- PostgreSQL enums for workflow statuses; CHECK constraints for invariants.
- Deterministic constraint names (naming convention in `app/db/base.py`).
- Every schema change is an Alembic migration. `create_all()` is never used.
- Extensions are enabled by the migration of the step that first needs them: `pg_trgm` and FTS (Step 4), `btree_gist` (Step 11, booking exclusion constraint), `vector` (Step 13).

The full ER design (profiles, taxonomy with aliases, projects, publications, opportunities, applications, collaborations, facilities, bookings, funding, saved items, notifications, refresh tokens, reports, audit logs, embeddings) is in the approved blueprint. Each table is introduced in the step that needs it.

## 8. API conventions

- Business APIs live under `/api/v1`. Health probes stay at the root.
- Plural nouns, `?page=&page_size=` capped at 100, `?sort=-created_at`.
- State transitions are explicit action sub-resources, e.g. `POST /projects/{id}/submit`, `POST /applications/{id}/withdraw`. Personal collections live under `/me/...`.
- One error envelope for every error:

  ```json
  { "error": { "code": "not_found", "message": "Not Found", "details": null } }
  ```

## 9. AI and recommendations

- **Phase 1 (MVP):** tag and skill overlap, research-area Jaccard with a hierarchy boost, and TF-IDF cosine similarity. Combined with a weighted hybrid score, business filters, and explanations derived from the actual score components.
- **Phase 4:** `all-MiniLM-L6-v2` embeddings stored in pgvector (HNSW index), with two-stage retrieval re-ranked by Phase 1 scores. Semantic search merges with full-text search via reciprocal rank fusion.
- Every phase must beat the previous one on a hand-labelled evaluation set (precision@5, nDCG@10).

## 10. Security baseline

OWASP-aligned throughout:

- No secrets in the repository; `.env` is git-ignored.
- Strict settings validation in production.
- Separate create, update and response schemas to prevent mass assignment.
- ORM-bound parameters only.
- Rate limiting on authentication and search.
- Audit log for sensitive actions.
- Secure file handling when uploads arrive.

## 11. Roadmap

See the table in the [README](../README.md#development-roadmap). Steps are merged one at a time. Nothing is built ahead of its step.

# CLAUDE.md: LPU Research Intelligence & Collaboration Hub

## What this is
Prototype research discovery & collaboration platform for the LPU ecosystem.
NOT an official LPU system unless formally adopted or authorized.
All data is fictional demo data. Never present fabricated data as real LPU data.

## Source of truth
- docs/architecture.md (approved architecture): follow it, don't redesign it.
- docs/adr/: record every significant decision as a new ADR (000N-title.md).
- README roadmap table: one step at a time. NEVER build ahead of the current step.
- lpu-roadmap-prompts.md: the full step-by-step roadmap and per-step prompts.

## Stack (do not replace)
Backend: Python 3.12+, FastAPI, Pydantic v2 / pydantic-settings, SQLAlchemy 2.0 (sync) + psycopg 3, Alembic
DB: PostgreSQL 16+ only (never SQLite). Uses FTS, pg_trgm, btree_gist, pgvector later.
Frontend: React 19 + TypeScript strict, Vite, Tailwind 4, React Router, Axios, TanStack Query, RHF + Zod
AI: scikit-learn (TF-IDF) now; sentence-transformers + pgvector later. Local only, no paid APIs.
Tooling: ruff, mypy --strict, pytest | eslint, prettier, tsc

## Hard rules
- Zero cost. No paid APIs, no mandatory cloud, Docker optional only.
- RBAC is enforced on the BACKEND. Frontend guards only hide UI.
- Role/active status always loaded from the DB, never trusted from token/client.
- 401 = not authenticated; 403 = authenticated but not allowed; 404 = must not know it exists.
- Never commit secrets or .env. All config via env vars; .env.example has placeholders only.
- Every schema change = reviewed Alembic migration with sequential rev id (--rev-id 000N).
  Never use Base.metadata.create_all().
- Separate Create/Update/Response Pydantic schemas. role, owner_id, status are never client-writable.
- Routers: HTTP only. Services: business rules, no FastAPI imports. Policies: ownership/scope.
- Workflow status transitions defined in ONE table per workflow and enforced in services.
- Business APIs under /api/v1. Errors use envelope {"error":{"code","message","details"}}.
- Sensitive actions (role change, approvals, deletions, admin actions) write to audit log (from Step 2).
- No new dependency without a stated purpose. No `any`, no broad `# type: ignore`,
  no disabling lint rules to pass checks.
- Tests use a real PostgreSQL test DB (TEST_DATABASE_URL), each test rolled back.
- Don't claim something works unless you ran it. Unverified = say "NOT VERIFIED".

## Where this actually is (read before planning anything)
All 16 roadmap steps are done (v1.0.0), plus the corrections after them:
department placement (ADR 0018), the provisioning hierarchy (ADR 0019), the
admin console, and the deployment configuration.
**Do not restart the roadmap or rebuild working modules.**

Current shape: ~128 API operations, 40 tables, 19 migrations, 22 ADRs,
~780 backend tests, ~158 frontend tests, 14 Playwright flows.

## Accounts and provisioning (the part most often got wrong)
- Nobody self-registers. `POST /auth/register` does not exist and must not
  come back; a test asserts the OpenAPI document has no such path.
- `CREATABLE_ROLE` in `app/core/permissions.py` is the only authority on who
  creates whom: admin -> coordinator -> faculty -> student.
- The create-account request has **no `role` field**. The role is derived
  from the caller. Never add one back "to validate it".
- `POST /api/v1/admin/users` is the admin override, audited under its own
  action. That is the only place a role may be named.
- Promoting to admin takes two people: a code goes to the *target's* inbox.
- **A coordinator's scope IS their department.** `_sync_coordinator_scope`
  keeps them in step whenever the role or department changes; they must never
  be set independently by hand again, or the coordinator oversees nothing.
- **Two sign-in pages, enforced on the server.** `LoginRequest.portal`
  ("admin" | "main"): administrators only at /admin/login, everyone else only
  at /login. The check runs *after* the password, so the admin page can never
  become an oracle for which numbers are administrators.
- **The registration number is the UID and is shown wherever a person is
  named** -- via `components/ui/Uid`, never a hand-rolled span. Every
  person-bearing response schema carries `registration_number`; search matches
  it as a case-insensitive prefix, not through the language analyser -- an
  identifier is not prose.
- **Deleting is not deactivating, and both are needed.** `DELETABLE_ROLES`
  in `app/core/permissions.py` says who may remove whom: admin anyone but
  themselves, coordinator their department's faculty and students, faculty
  their students, student nobody. Nobody deletes their own account, which is
  also why no "last administrator" check exists -- it would be unreachable.
  21 of the 31 FKs to `users.id` CASCADE, so a deletion is always costed
  first (`GET /users/{id}/deletion-impact`) and shown before it is confirmed.
  Deactivate for someone who has left; delete for an account that should
  never have existed (it frees the registration number).
- **Threads are scoped, and there is no endpoint that creates one.** A
  conversation belongs to an accepted collaboration request or a project
  team; it appears when that happens. Never add a create-conversation
  route, or the student opt-in (`can_contact`) is repealed by the back
  door. A non-participant always gets 404, never 403 -- admins included.
  New messages arrive by polling, not sockets (ADR 0022): the cursor is a
  keyset over (created_at, id), never an offset.
- A fix to the service layer does not fix the rows already in the deployed
  database. The coordinators appointed before `_sync_coordinator_scope` needed
  migration 0018 as well, and the users page now shows each coordinator's
  scope so a missing one is visible instead of silent.

## UI conventions (white + LPU orange, tokens in frontend/src/index.css)
- **One button recipe:** `components/ui/buttonClass` + `Button`/`ButtonLink`.
  Never hand-write `rounded-md bg-brand-700 px-3 py-2 ...` again.
- **One page top:** `components/ui/PageHeader` (title, one-sentence
  description, actions). 50 pages had rolled their own.
- **`components/layout/navigation.ts` is the single list of destinations.** It
  drives the top bar, the grouped "All pages" menu and the command palette, so
  a role can never reach a page through one and not another. Add a page there
  or it is unreachable from two of the three.
- **Cmd/Ctrl+K (or "/") opens the command palette.** 28 destinations, six fit
  on the bar; the palette is how people actually get around. It only offers
  pages the signed-in role can reach.
- Loading shows `SkeletonList`, not the word "Loading".

## Gotchas that cost real time here
- **Autogenerate does not see enum values.** It compares tables, not enum
  members, so `ALTER TYPE ... ADD VALUE IF NOT EXISTS` is written by hand
  (migrations 0017, 0019). A test DB already stamped at that revision will
  not pick it up -- rebuild it rather than debugging the enum error.
- **Tests passing is not the screen working.** The OTP code was delivered and
  invisible because `describeNotification` had no case for it, and every test
  passed. Drive new UI in a browser before calling it done.
- **Walk it from empty.** Every deadlock found here was a bootstrapping gap,
  not a permission bug. `tests/test_bootstrap_walkthrough.py` is the guard.
- **`getByLabel` substring-matches.** "Search" matched the brand link;
  "Name" matched a "Rename X" button. Use `{ exact: true }` or a role.
- **The frontend TS types are hand-written mirrors of the Pydantic schemas**
  and have drifted twice. When adding a backend field, update
  `frontend/src/features/*/types.ts` in the same change.
- E2E runs against the *development* database, so its state matters. A
  local run needs `scripts/seed_demo_data.py` first, or every flow fails
  at sign-in for want of DEMOADMIN -- CI seeds it, a dev box may not.
- **The E2E sign-in helper has to use the right entrance.** Administrators
  are refused at /login (ADR 0020), so `sessionFor` sends DEMOADMIN to
  /admin/login. This is what turned CI red for six commits, unnoticed
  because the other five jobs stayed green. Anchor the URL assertion
  (`/\/admin$/`): an unanchored `/\/admin/` also matches /admin/login, so
  a failed sign-in passes and the test dies later, somewhere confusing.
- **Check `gh run list` after pushing.** Backend and frontend passing is
  not the suite passing.

## Deployment (configured, never yet performed)
Free path: Neon (Postgres + pgvector) -> Render (API from source, reads
`render.yaml`) -> Netlify (static, reads root `netlify.toml`, proxies /api
so the refresh cookie stays first-party).
- `netlify.toml` MUST be at the repo root; Netlify never finds it elsewhere.
- Render's Docker runtime looks for `./Dockerfile` at the configured root
  directory -- set that to `backend`, or use the Blueprint for a source build.
- Migrations are a release step: `backend/scripts/release.sh`, run from a
  workstation. Never on container start.
- Do not install the `ml` extra in production; it exceeds a free instance.
- **Deployed 24 Sep 2026.** API live on Render (Docker service, root
  directory `backend`) against Neon; health, readiness, login and the
  production headers all verified. Netlify still to do.
- The Docker images HAVE now been built, by Render. Never built locally.

## Commands
Backend (backend/, venv active): ruff check . && ruff format --check . && mypy && pytest
Run: uvicorn app.main:create_app --factory --reload
Migrate: alembic upgrade head
Frontend (frontend/): npm run typecheck && npm run lint && npm run format:check && npm run test && npm run build
Run: npm run dev

## Workflow for every step
1. Read CLAUDE.md, docs/architecture.md, and the step prompt.
2. Give a concise PLAN (files, models, endpoints, migrations, tests, deviations). STOP for approval.
3. Implement only that step on branch feat/step-N-<name>.
4. Run all checks + the step's verification list. Fix root causes.
5. Update README status/roadmap, docs/architecture.md if needed, add ADR if a decision was made.
6. Report: summary, files, deps, migrations, endpoints, checks (PASSED/FAILED/NOT VERIFIED),
   deviations, commands to run, next step. Then STOP.

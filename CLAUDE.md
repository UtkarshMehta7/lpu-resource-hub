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

Current shape: 161 API operations over 130 paths, 44 tables, 27 migrations,
29 ADRs, 27 backend modules, 1059 backend tests, 252 frontend tests,
14 Playwright flows.

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
- **Demo accounts carry LPU-shaped registration numbers** in the 125xxxxx
  block (`demo.faculty07@example.com` -> `12500207`), derived from the email
  by `_demo_registration_number` so the seed stays idempotent and the rebrand
  script agrees with it. They used to be `DEMOFACULTY07`, which was obviously
  fake on purpose; `users.is_demo` carries that meaning now. Hand-made
  accounts live in 124xxxxx, so the blocks never collide. **The E2E flows sign
  in with these numbers** -- change the scheme and `frontend/e2e/flows.spec.ts`
  changes with it, or CI goes red at sign-in.
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
- **Chat must never break collaboration.** Opening a thread on acceptance
  runs in a savepoint and swallows SQLAlchemyError: the acceptance is the
  older, more important act. Shipping the code before its migration made
  every acceptance answer 500 -- an additive feature took down an
  existing one. A new dependency from old code to new code gets the same
  treatment.
- **A collaboration is a PAIR, not a request** (ADR 0023). `collaborations`
  stores user_a_id < user_b_id under a unique constraint, so a duplicate is
  impossible in the database rather than guarded in a service somebody can
  forget. One conversation per pair, for the life of the pair: collaborating
  again after ending reopens the same thread. Never key a thread or a
  relationship to a request again.
- **Threads are scoped, and there is no endpoint that creates one.** A
  conversation belongs to an accepted collaboration request or a project
  team; it appears when that happens. Never add a create-conversation
  route, or the student opt-in (`can_contact`) is repealed by the back
  door. A non-participant always gets 404, never 403 -- admins included.
  New messages arrive by polling, not sockets (ADR 0022): the cursor is a
  keyset over (created_at, id), never an offset.
- **An academic year is not a calendar year.** July to June by default,
  `ACADEMIC_YEAR_START_MONTH` configurable. "2025-27" is refused as a typo
  rather than reinterpreted -- a wrong period on a signed report is worse
  than an error message. See app/modules/analytics/academic_year.py.
- **The institutional report has ONE aggregation, three renderings** (JSON,
  CSV, PDF from the same `InstitutionalReport`). Never add a second
  aggregation for a format; the numbers would drift.
- **A metric that cannot be computed reads "not applicable", never 0.** No
  decided applications is not a 0% success rate. Every rate returns None
  rather than dividing by zero, and every table carries its definition --
  see docs/analytics.md for the formulas.
- **An administrator needs no verification, ever.** Verification means
  somebody senior vouched for a record, and nobody is senior to an admin --
  a PENDING admin was asking a coordinator to vouch for their own senior, and
  the queue had no role filter so they really appeared there. Four guards,
  because any one alone leaves a gap: the profile verifies itself on save,
  the queue excludes admins whatever their stored status, `/verify` refuses
  them (409, and rejecting is the dangerous half), and an import does not
  reset them. Migration 0025 fixed the rows already deployed.
- **A name search NEVER picks a person** (ADR 0027). It offers candidates
  with their institution, metrics and a link to the record, and the
  researcher chooses; the choice comes back as `openalex_author_id` and beats
  any matching. Taking `results[0]` is how a live user imported Nitish
  Srivastava of Google as themselves.
- **Importing sends a verified profile back to PENDING.** A tick means
  somebody here checked the record; after an import it holds claims nobody
  here has seen. Never let an import preserve verification.
- **Every imported work links to its DOI** so it can be checked before it is
  accepted, not audited afterwards. `WorkCandidate.url` is the fallback.
- **Nudges never name their recipient.** `POST /nudges` takes a kind and an
  entity; the service resolves who hears about it from the thing being
  chased. A recipient field would make it a way to message anyone in the
  institution, and a test asserts the schema has exactly two fields. One
  nudge per thing per day, enforced in the service, not the interface.
- **A milestone's risk is DERIVED on every read, never stored** (ADR 0026).
  `milestones/risk.py` is a pure function of status, due date, today and what
  it waits on; the analytics view calls that same function rather than
  reimplementing the rules in SQL. Never add an `at_risk` column -- a stored
  flag is wrong between job runs, and the board would disagree with the
  project page. The scheduled job exists only to notify exactly once.
- **Milestones have two actors, not one.** Members may move work along
  (`in_progress`, `done`); only the owner may create, edit, delete or cancel.
  `milestones/policies.py:TRANSITIONS` is the single table both are checked
  against.
- **Milestone visibility is composed, not restated.** A milestone is visible
  exactly when its project is, so the service calls
  `projects.service._load_visible`; one on an invisible project is a 404.
  Don't grow a second copy of the visibility rule.
- **Dependency cycles are refused in the service**, not the database: no
  constraint can express acyclicity, and a cycle makes the risk walk
  non-terminating. Self-dependency is the one case a CHECK does catch.
- **The seed script creates projects and milestones now.** It previously
  created none, so any plan that says "add X to the demo projects" should
  check they exist first.
- **Profile import pulls from four public sites, and none of them is the one
  the brief names** (ADR 0025). ORCID resolves identity, OpenAlex supplies
  breadth in place of Scopus, Crossref canonicalises metadata by DOI, and
  Semantic Scholar adds abstracts best-effort. Scopus and Web of Science need
  a paid licence; ResearchGate answers a server-side request with 403 and a
  CAPTCHA; JSTOR has no profiles to import and no API; DBLP serves an anti-bot
  page. All four rejections were tested, not assumed -- don't re-litigate them
  from the brief's list.
- **Import is preview-then-apply, and apply re-reads the sources.** Never
  change it to trust the payload the browser sends back: that would let any
  account post arbitrary publications labelled as imported from Crossref.
- **A DOI is normalised before it is compared or stored** (`normalise_doi`).
  OpenAlex percent-encodes the slash on some records, and one malformed DOI
  makes Crossref reject the entire 40-item batch it appears in. Found live.
- **Two different DOIs are never merged, however alike the titles.** An
  erratum, a preprint and its version of record are separate works. The
  de-duplication rules and their known failure cases are written up in
  `docs/publication-deduplication.md`.
- **The duplicate review queue is the band between the two thresholds**
  (ADR 0029). The importer merges unattended at `TITLE_MATCH_THRESHOLD` (92);
  the queue *suggests* from `TITLE_SUGGEST_THRESHOLD` (84). It reuses
  `merge.py`'s rules rather than growing a second opinion, so the DOI veto
  holds in both places.
- **A merge DELETES the losing publication; it does not hide it.**
  Publications are read in fifteen places across eight modules, and a
  hidden-row flag would have to be honoured by every one -- one missed query
  is a ghost publication that still answers a search. The deleted row is
  snapshotted on the review row, which is what makes the merge reversible; an
  undo recreates it with a **new id**. Never add a `merged_into_id` column to
  `publications`.
- **A decided duplicate pair is never raised again by a later scan.** If
  "these are different works" came back next week, the queue would never empty
  and people would stop reading it.
- **Six roles, and two of them inherit nothing.** `FACILITY_CUSTODIAN` and
  `DEAN_OF_RESEARCH` (ADR 0028) sit outside `CREATABLE_ROLE` entirely: they are
  appointed only through the admin override, whose permitted set is
  `APPOINTABLE_BY_ADMIN` -- every role but `ADMIN`, because promotion stays the
  two-person ceremony. A custodian's scope is a **set of facility rows**, not a
  department, so `facility:manage` is checked object-level against the loaded
  facility (`facilities/policies.py: may_manage_facility`); the same rule as a
  query filter is `manageable_facility_filter`, and the booking queue uses it so
  a listing can never show a request the approve call would then refuse. A dean
  holds `analytics:read` and nothing else, and `INSTITUTION_WIDE_ROLES` is why
  they alone need no department.
- **Enforcing a permission is not the same as making it reachable.** The
  custodian role shipped fully enforced and *unassignable*: `custodian_id` was
  in no schema and no endpoint wrote it, so the role could be created and
  never used. The tests passed because the fixture wrote the column with raw
  SQL. A fixture that reaches past the API hides exactly that gap -- if a
  helper needs SQL to set something up, ask which endpoint is missing.
- **Holding a facility and deciding who holds it are different powers.**
  `PUT /facilities/{id}/custodian` is gated at DEPARTMENT level
  (`assert_can_manage`), never object level: a custodian passes the object
  check for their own facility, so folding the assignment into
  `FacilityUpdate` would let them hand the room away or take a colleague's.
  The candidate list (`/custodian-candidates`) is filtered by the same rules
  the assignment enforces, so the picker can never offer somebody the
  assignment would refuse. Both directions audited.
- **A facility's department decides who can manage it ever after**, so the
  create form makes it an explicit choice and refuses to submit without one.
  It used to send `user.department_id` for an administrator -- which is null,
  because an administrator belongs to no department -- so every facility an
  admin created came out university-wide, reachable by no coordinator and
  counted in no department's figures. "University-wide" is still offered, as a
  deliberate option that says what it costs.
- **The demo seed creates facilities and equipment now**, and assigns the
  first to `demo.custodian01` (12500401); `demo.dean01` (12500501) has no
  department, as a dean must not. Before this the catalogue, the booking queue
  and the custodian role were all empty on a fresh install.
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
- **A new module's models must go in `app/db/model_registry.py`** or
  autogenerate produces an **empty migration** and says nothing is wrong. It
  did exactly that for `publication_duplicates` the first time.
- **A nested path loses to a path parameter registered before it.**
  `/publications/duplicates` was swallowed by `/publications/{publication_id}`
  and "duplicates" was parsed as a UUID, because FastAPI matches in
  registration order. Give a new resource its own top-level path
  (`/publication-duplicates`) rather than relying on include order in
  `app/main.py`, which breaks silently when somebody reorders it.
- **A mutation calls its `mutationFn` with more than one argument.** Passing
  an api function by reference (`mutationFn: undoDuplicateMerge`) forwards all
  of them; wrap it (`(id) => undoDuplicateMerge(id)`) or a
  `toHaveBeenCalledWith` assertion fails for reasons that look like the click
  never happened.
- **Don't reuse a label for a filter and an action on the same screen.**
  "Different works" was both a status chip and a button, so four tests matched
  the wrong element -- and a reader would have had the same trouble.
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
  at sign-in for want of the seeded admin (12500001) -- CI seeds it, a dev
  box may not.
- **The E2E sign-in helper has to use the right entrance.** Administrators
  are refused at /login (ADR 0020), so `sessionFor` sends the seeded admin
  (12500001) to /admin/login. This is what turned CI red for six commits, unnoticed
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
- **The deployed instance migrates itself at boot** and starts degraded if
  that fails, reporting why on /health/ready (ADR 0024,
  on by default in production). No advisory lock: DATABASE_URL is Neon's
  *pooler*, PgBouncer in transaction mode, where a session-level
  pg_advisory_lock is never released -- the container hung before binding its
  port and the deploy was cancelled. Nothing that runs before the port is
  bound may be able to block.
- Still run **destructive or data-rewriting** migrations deliberately with
  `backend/scripts/release.sh` before merging the code that needs them.
  Unattended is fine for adding a table; it is not fine for merging rows.
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

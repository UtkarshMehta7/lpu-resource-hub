# LPU Research Hub: Full Roadmap & Claude Code Prompts

How to use this file:

1. **Copy Part A into `CLAUDE.md` at the repo root** and commit it. Claude Code reads that file automatically in every session, so the project rules never need repeating.
2. **Run one step per session.** Paste that step's prompt from Part C. Claude plans, you approve, Claude implements, verifies and reports.
3. **Review and test each step before starting the next one.** Every step ends with one focused commit, or a short series of them.

---

## PART A: `CLAUDE.md` (put this in the repo root)

```markdown
# CLAUDE.md: LPU Research Intelligence & Collaboration Hub

## What this is
Prototype research discovery & collaboration platform for the LPU ecosystem.
NOT an official LPU system unless formally adopted or authorized.
All data is fictional demo data. Never present fabricated data as real LPU data.

## Source of truth
- docs/architecture.md (approved architecture): follow it, don't redesign it.
- docs/adr/: record every significant decision as a new ADR (000N-title.md).
- README roadmap table: one step at a time. NEVER build ahead of the current step.

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

## Commands
Backend (backend/, venv active): ruff check . && ruff format --check . && mypy && pytest
Run: uvicorn app.main:create_app --factory --reload
Migrate: alembic upgrade head
Frontend (frontend/): npm run typecheck && npm run lint && npm run format:check && npm run build
Run: npm run dev

## Workflow for every step
1. Read CLAUDE.md, docs/architecture.md, and the step prompt.
2. Give a concise PLAN (files, models, endpoints, migrations, tests, deviations). STOP for approval.
3. Implement only that step on branch feat/step-N-<name>.
4. Run all checks + the step's verification list. Fix root causes.
5. Update README status/roadmap, docs/architecture.md if needed, add ADR if a decision was made.
6. Report: summary, files, deps, migrations, endpoints, checks (PASSED/FAILED/NOT VERIFIED),
   deviations, commands to run, next step. Then STOP.
```

---

## PART B: Roadmap at a glance

| Step | Name | Key output | Depends on |
|---|---|---|---|
| 0 | Foundation | Repo, FastAPI/React shells, DB, Alembic, `/health` | ✅ done |
| 1 | Auth | users table, Argon2id, JWT + rotating refresh cookie, login/register UI | 0 |
| 2 | RBAC core | permission map, `require_permission`, policies, audit log, authz test scaffold | 1 |
| 3 | Org, taxonomy, profiles | schools/departments, skills/areas + aliases, student & researcher profiles, faculty verification, onboarding, seed data | 2 |
| 4 | Directory & search | researcher directory, opt-in student discovery, FTS + pg_trgm, filters | 3 |
| 5 | Projects | project CRUD, DRAFT→PENDING_REVIEW→ACTIVE workflow, coordinator review queue, team members | 3 |
| 6 | Publications | publications with internal/external authors, link to projects | 3, 5 |
| 7 | Opportunities & applications | opportunity board, apply/withdraw, faculty review workflow | 5 |
| 8 | Collaboration requests | send/accept/decline/cancel, inbox/sent | 3 |
| 9 | Recommendations v1 | tag + skill + TF-IDF hybrid, explanations, evaluation set | 4–8 |
| 10 | Dashboards & polish | role dashboards, saved items, UI states, E2E flows → **MVP complete** | 1–9 |
| 11 | Facilities, equipment, booking | catalogue, calendar, approvals, DB-level no double-booking | 10 |
| 12 | Funding, notifications, reminders | funding listings, in-app notifications, deadline reminder job | 10 |
| 13 | Semantic AI | embeddings, pgvector, hybrid semantic search & recs | 9 |
| 14 | Analytics & admin | analytics dashboards, collaboration network, audit-log UI, reports/moderation | 10–12 |
| 15 | Deploy & hardening | optional Docker, CI, free-tier deploy, security hardening | all |

Milestones:
- **MVP** = Steps 1–10.
- **Submission scope** = MVP + Steps 11–12. This covers every item in problem statement #25.
- **Advanced** = Steps 13–15.

---

## PART C: Step prompts (paste one per session)

### Common header (start every step prompt with this)

```
Read CLAUDE.md and docs/architecture.md first. They are the source of truth.
We are implementing STEP N ONLY. Do not build ahead.
First give me a concise implementation plan (files, models, migrations, endpoints,
UI pages, tests, any deviation with reason). Then STOP and wait for my approval.
After approval: implement on branch feat/step-N-<name>, run every check, report using
PASSED / FAILED / NOT VERIFIED, and stop. Do not start the next step.
```

---

### STEP 1: Users & Authentication

```
<common header, N=1, name=auth>

GOAL: Secure user accounts and authentication.

BACKEND
- Migration 0002: users (id UUID pk default gen_random_uuid(), email unique on lower(email),
  password_hash, full_name, role enum STUDENT|FACULTY|RESEARCH_COORDINATOR|ADMIN,
  is_active bool, created_at, updated_at timestamptz). Enable pgcrypto only if needed.
- refresh_tokens (id, user_id FK, token_hash sha256, family_id, expires_at, revoked_at, created_at).
- Model registry module imported by alembic/env.py so autogenerate sees all models.
- core/security.py: Argon2id (argon2-cffi), min password length 10 + small common-password list.
- Access JWT 15 min (HS256, JWT_SECRET from env; app refuses to start if missing or < 32 chars).
  Claims: sub, role, type=access, iat, exp, jti.
- Refresh token: opaque random, 7 days, httpOnly Secure(prod) SameSite=Lax cookie, path /api/v1/auth.
  Stored hashed. Rotate on every refresh. Reuse of a revoked token revokes the whole family.
- Endpoints /api/v1/auth: register (self-register as STUDENT or FACULTY only; never COORDINATOR/ADMIN),
  login, refresh, logout, change-password. GET /api/v1/me.
- Refresh endpoint also requires a custom header (X-Requested-With) as CSRF defence.
- deps.get_current_user: validate JWT, then LOAD USER FROM DB; reject inactive users.
- Login rate limit (in-memory, e.g. 5/min per IP+email), generic "invalid credentials" errors.
- CORS allow_credentials=True with explicit origins.
- scripts/create_admin.py: CLI to create the first admin (password prompted, never hardcoded).

FRONTEND
- Add TanStack Query, React Hook Form, Zod, openapi-typescript (generated types in src/types/).
- AuthContext: access token in memory only; silent refresh on 401 (single in-flight refresh, queue).
- Pages: Login, Register (role choice Student/Faculty), minimal "Me" page. ProtectedRoute.
- Vitest + React Testing Library: tests for ProtectedRoute and login form validation.

TESTS (backend)
register/login/refresh/logout happy paths; duplicate email (case-insensitive); weak password;
tampered JWT; expired JWT; edited role claim has no effect; deactivated user rejected;
refresh rotation; refresh reuse revokes family; registering as ADMIN is rejected; mass-assignment
of role ignored/rejected; rate limit triggers.

OUT OF SCOPE: permissions/RBAC beyond "authenticated", profiles, email verification, password reset.
COMMIT: feat: implement authentication
```

---

### STEP 2: RBAC Core & Audit Log

```
<common header, N=2, name=rbac>

GOAL: Backend-enforced role-based access control derived from the approved permission matrix.

- core/permissions.py: Permission strings "resource:action" and ROLE_PERMISSIONS map
  generated from the matrix in docs/architecture.md (write the full matrix into docs/rbac-matrix.md).
  Hierarchy: COORDINATOR inherits FACULTY capabilities; ADMIN has operational/moderation powers.
- Dependency require_permission("x:y") -> 403 on failure, 401 if unauthenticated.
- Policy base pattern (policies.py per module): ownership + coordinator scope checks after loading.
- Coordinator scope: add users.coordinator_scope_type (DEPARTMENT|SCHOOL|UNIVERSITY) and scope id
  columns (nullable) - department-level used now, extensible later. (Department FK arrives in Step 3;
  add the column there if FK needed - explain in plan.)
- Admin user management: GET/PATCH /api/v1/admin/users, POST /admin/users/{id}/role,
  /activate, /deactivate. Guards: no self-role-change, cannot remove the last active admin.
- audit_logs table (actor_id, action, entity_type, entity_id, before jsonb, after jsonb, ip, created_at),
  append-only audit service; log role changes, activation changes.
- GET /api/v1/admin/audit-logs (admin only, paginated, filters).
- Pagination helper (page, page_size<=100) + standard list response shape.
- Authorization test suite: parametrized role x endpoint table asserting expected status codes
  (e.g. student POST /api/v1/admin/users -> 403). This table grows every step.
- Frontend: RoleRoute (hides UI only), basic Admin Users page (list, change role, activate/deactivate)
  with confirmation dialogs.

OUT OF SCOPE: profiles, domain resources.
COMMIT: feat: implement RBAC   (+ test: add backend authorization tests)
```

---

### STEP 3: Organisation, Taxonomy, Profiles & Faculty Verification

```
<common header, N=3, name=profiles>

GOAL: Schools/departments, a shared research taxonomy, student and researcher profiles,
faculty verification, onboarding, and fictional seed data.

- schools 1-N departments; users.department_id (nullable for admin). Admin CRUD for both.
- Taxonomy: skills, research_areas (self-FK parent_id, 2 levels), tag_aliases (alias -> canonical).
  Coordinator/admin manage taxonomy + merge tags; others can POST /tags/suggestions.
- user_skills (proficiency 1-5), user_research_areas (is_expertise bool).
- student_profiles (program, year, bio, interests, is_discoverable default FALSE).
- researcher_profiles (designation, bio, availability enum, links jsonb validated URLs,
  verification_status UNVERIFIED|PENDING|VERIFIED|REJECTED, verified_by, verified_at).
- Endpoints: GET/PUT /me/profile, PUT /me/skills, PUT /me/research-areas, GET /skills?q=,
  GET /research-areas, coordinator: GET /coordinator/verification-queue,
  POST /researchers/{id}/verify {decision, comment} (scope = own department, audited).
- Onboarding: require >=3 research areas and >=3 skills before recommendations (store completeness flag).
- Privacy: public schemas never expose email or private fields; student profile visible only
  if is_discoverable (enforced in queries).
- scripts/seed_demo_data.py: idempotent, clearly FICTIONAL names, is_demo flag, e.g. 3 schools,
  8 departments, ~60 skills, ~40 areas (+aliases like ML -> Machine Learning), 25 faculty,
  80 students, 2 coordinators, 1 admin. Passwords from env/prompt, never hardcoded.
- Frontend: onboarding wizard, My Profile edit page, tag picker (autocomplete, aliases),
  coordinator verification queue page.
- Tests: verification only by coordinator in same department; faculty can't self-verify;
  unverified faculty flagged (publishing blocked in Step 5); privacy of student fields; authz table rows.

COMMIT: feat: implement researcher profiles
```

---

### STEP 4: Researcher Directory & Search

```
<common header, N=4, name=directory-search>

GOAL: Searchable, filterable directory across departments.

- Migration: enable pg_trgm; weighted tsvector generated columns + GIN indexes on researcher
  profiles (name A, expertise/tags B, bio C); trigram GIN on names.
- GET /api/v1/researchers filters: q, school, department, research_area (incl. child areas),
  skill, availability, verified_only; sort; pagination. GET /researchers/{id} public profile
  (profile, expertise, skills; projects/publications sections filled in later steps).
- GET /api/v1/students (FACULTY+ only, is_discoverable=true only, public fields only).
- GET /api/v1/search?q=&types= unified endpoint (researchers now; extended by later steps),
  websearch_to_tsquery + trigram fallback for typos.
- Rate-limit search endpoints.
- Frontend: Researchers directory (filters sidebar, cards, URL-synced filters, empty/loading/error
  states), Researcher detail page, Discover Students page (faculty/coordinator), global search bar.
- Tests: filters, typo tolerance, students never returned unless opted in, students role gets 403
  on /students, pagination caps.

COMMIT: feat: implement researcher directory and search
```

---

### STEP 5: Research Projects & Review Workflow

```
<common header, N=5, name=projects>

GOAL: Projects owned by faculty, with mandatory coordinator review.

- projects (title, summary, description, objectives, owner_id, department_id, status enum
  DRAFT|PENDING_REVIEW|ACTIVE|COMPLETED|ARCHIVED, start_date, end_date CHECK start<=end,
  review_comment, reviewed_by, reviewed_at, deleted_at), project_skills, project_research_areas,
  project_members (UNIQUE project_id,user_id; member_role).
- Transition table: DRAFT->PENDING_REVIEW (owner, VERIFIED faculty only), PENDING_REVIEW->ACTIVE|DRAFT
  (coordinator of same department, NEVER own project, comment required on reject),
  ACTIVE->COMPLETED|ARCHIVED (owner), any->ARCHIVED (admin moderation).
- Endpoints: GET/POST /projects, GET/PATCH/DELETE /projects/{id} (delete only DRAFT, else archive),
  POST /projects/{id}/submit, /review {decision, comment}, /archive, /complete,
  GET/POST/DELETE /projects/{id}/members, GET /coordinator/review-queue.
- Visibility: students/others see ACTIVE+COMPLETED only; DRAFT/PENDING visible to owner, scoped
  coordinator, admin; others get 404. Enforce in queries.
- Extend FTS + /search to projects. Audit approvals/rejections.
- Frontend: Projects list + filters, project detail, My Projects, create/edit form, submit button,
  coordinator review queue with approve/reject dialog.
- Tests: full workflow; unverified faculty cannot submit; coordinator cannot approve own or
  other-department project; faculty A cannot edit faculty B's project (403); student sees 404 for drafts;
  invalid transitions rejected (409 or 422 - decide and document).

COMMIT: feat: implement research projects
```

---

### STEP 6: Publications

```
<common header, N=6, name=publications>

GOAL: Publications on researcher profiles and projects (feeds TF-IDF later).

- publications (title, abstract, venue, year CHECK sane range, doi unique nullable, url, pub_type,
  created_by), publication_authors (user_id nullable, external_name nullable,
  CHECK one present, author_order, UNIQUE(publication_id, author_order)),
  project_publications (N-M).
- Endpoints: GET/POST /publications, GET/PATCH/DELETE /publications/{id}; filters (author, year,
  area via linked projects, q). Owner = creator; internal co-authors can view in their profile.
- Researcher detail + project detail now show publications. Extend FTS/search.
- Frontend: My Publications (CRUD with author list editor), publication list/detail.
- Tests: ownership, author constraints, DOI uniqueness, authz rows.

COMMIT: feat: implement publications
```

---

### STEP 7: Research Opportunities & Applications

```
<common header, N=7, name=opportunities>

GOAL: Opportunity board and application workflow.

- opportunities (title, description, type enum RESEARCH_ASSISTANT|STUDENT_RESEARCHER|
  PROJECT_ASSISTANT|RESEARCH_INTERNSHIP|COLLABORATION, project_id nullable, created_by,
  department_id, eligibility, positions CHECK >0, deadline, status DRAFT|OPEN|CLOSED|FILLED),
  opportunity_skills (is_required).
  Faculty may create only on their own ACTIVE projects; coordinator within scope.
- applications (opportunity_id, applicant_id, statement, status SUBMITTED|UNDER_REVIEW|SHORTLISTED|
  ACCEPTED|REJECTED|WITHDRAWN, UNIQUE(opportunity_id, applicant_id), decided_by, decided_at, note).
  Transition table; withdraw only by applicant before final decision; cannot apply after deadline,
  to non-OPEN, or twice. Students apply to student-type openings; faculty only COLLABORATION.
  On ACCEPTED: optionally add applicant to project_members (transactional). Close when positions filled.
- Endpoints: GET/POST /opportunities, GET/PATCH /opportunities/{id}, POST /opportunities/{id}/close,
  POST /opportunities/{id}/applications, GET /opportunities/{id}/applications (owner/scoped coordinator
  read-only), GET /me/applications, GET /applications/{id}, POST /applications/{id}/status,
  POST /applications/{id}/withdraw.
- Extend search. Audit decisions.
- Frontend: Opportunity board (filters: type, dept, skill, deadline), detail + apply form,
  My Applications tracker (status timeline), faculty applicant review table + detail drawer.
- Tests: all rules above, student cannot change status (403), faculty cannot view others' applications,
  race: double apply blocked by unique constraint.

COMMIT: feat: implement opportunities   (+ feat: implement applications)
```

---

### STEP 8: Collaboration Requests

```
<common header, N=8, name=collaboration>

GOAL: Direct collaboration requests between users.

- collaboration_requests (sender_id, recipient_id CHECK different, project_id nullable, message,
  status PENDING|ACCEPTED|DECLINED|CANCELLED, responded_at),
  partial UNIQUE(sender, recipient, project) WHERE status='PENDING'.
- Endpoints: POST /collaborations, GET /me/collaborations?box=inbox|sent, GET /collaborations/{id},
  POST /collaborations/{id}/accept|decline (recipient only), /cancel (sender only).
- Students may only message researchers or opted-in students; admin cannot send.
- Basic per-user rate limit on sending.
- Frontend: "Request collaboration" button on researcher/student/project pages, inbox/sent page.
- Tests: only recipient responds, only sender cancels, duplicate pending blocked, privacy rules.

COMMIT: feat: implement collaboration
```

---

### STEP 9: Explainable Recommendations v1

```
<common header, N=9, name=recommendations>

GOAL: Real, explainable AI matching (Phase 1: structured + lexical). No chatbot. Local only.

- app/ml/: preprocessing, tfidf (scikit-learn), scoring, explain. Interface:
  Recommender.recommend(user, target_type, k) -> [ScoredItem(item, score, reasons[])].
- Scores: skill_score (weighted overlap, required > optional, proficiency-aware),
  area_score (weighted Jaccard + parent-area partial credit), text_score (TF-IDF cosine of
  bio/interests vs description/objectives/publication titles+abstracts).
  score = w1*skill + w2*area + w3*text; weights in settings (default 0.40/0.35/0.25).
- Business filters: OPEN, deadline not passed, eligible, not already applied, not self, visibility rules.
- Explanations derived ONLY from actual score components, e.g. "Matches 3 of 4 required skills:
  Python, Docker, AWS", "Shared areas: Cloud Computing", "Related terms: containers, scheduling".
- Cold start: incomplete profile -> newest/popular items labelled as such.
- TF-IDF matrix cached in memory, rebuilt on content change (simple invalidation).
- GET /api/v1/recommendations?type=researchers|projects|opportunities|collaborators&limit=
- Evaluation: fixtures/eval set (hand-labelled relevance on seed data), script computing
  precision@5 and nDCG@10; report numbers in docs/ai-evaluation.md.
- Frontend: recommendation cards with "Why this?" reasons.
- Tests: deterministic scoring on fixtures, filters respected, no hidden items leaked.

COMMIT: feat: implement AI recommendations
```

---

### STEP 10: Role Dashboards, Saved Items & MVP Polish

```
<common header, N=10, name=dashboards>

GOAL: Complete, polished MVP.

- saved_items (user_id + exactly one of project_id/opportunity_id/researcher_id; CHECK num_nonnulls=1,
  partial uniques). GET/POST/DELETE /me/saved. (funding_id added in Step 12.)
- GET /me/dashboard returning role-specific aggregates:
  Student: recommended faculty/projects/opportunities, saved, applications, collaboration requests,
  upcoming deadlines. Faculty: my projects, open opportunities, pending applications, team members,
  collaborators, publications. Coordinator: pending verifications + project reviews, dept activity.
  Admin: users by role, departments, platform counts, recent audit entries.
- Content reports: content_reports (reporter, target_type, target_id, reason, status) +
  POST /reports; coordinator/admin review queue.
- UI polish: consistent design system, skeletons, empty states with next action, error states,
  confirmation dialogs, accessible forms (WCAG 2.1 AA basics), responsive layout, role-based nav.
- Playwright E2E for the 4 flows: student (login->dashboard->find project->apply->track),
  faculty (create project->submit->create opportunity->review->accept), coordinator (review->approve/
  reject), admin (manage users/roles->view stats).
- README: update status to "MVP complete", screenshots optional.

COMMIT: feat: implement dashboards  -> tag v0.1.0-mvp
```

---

### STEP 11: Facilities, Equipment & Booking

```
<common header, N=11, name=facilities-booking>

GOAL: Facility catalogue and booking calendar with guaranteed no double-booking.

- Migration: enable btree_gist.
- facilities (name, description, department_id, location, contact), equipment (facility_id, name,
  description, category, maintenance_status AVAILABLE|MAINTENANCE|RETIRED, booking_rules:
  students_allowed, requires_approval, max_hours, min_lead_hours).
- bookings (equipment_id, user_id, period tstzrange, purpose, status PENDING|APPROVED|REJECTED|
  CANCELLED|COMPLETED, decided_by), CHECK lower<upper,
  EXCLUDE USING gist (equipment_id WITH =, period WITH &&) WHERE (status='APPROVED').
  PENDING may overlap; approval fails cleanly (409) if it would overlap.
- Endpoints: facilities/equipment CRUD (coordinator scope/admin), GET /equipment/{id}/availability?from&to,
  POST /bookings (rules enforced), POST /bookings/{id}/approve|reject|cancel, GET /me/bookings,
  coordinator booking-approval queue. Auto-approve when requires_approval=false (still constraint-safe).
- Frontend: facility directory, equipment detail with week calendar, booking request form,
  My Bookings, coordinator approvals page.
- Tests: CONCURRENCY test proving two overlapping approvals cannot both succeed; rules (students_allowed,
  max_hours, lead time, maintenance blocks booking); cancel only before start; authz rows.

COMMIT: feat: implement facilities  (+ feat: implement booking)
```

---

### STEP 12: Funding, Notifications & Deadline Reminders

```
<common header, N=12, name=funding-notifications>

GOAL: Funding calls, in-app notifications, reminders.

- funding_opportunities (organization, title, description, eligibility, amount_text or min/max,
  deadline, official_source_url, status OPEN|CLOSED, is_demo), funding_research_areas.
  Seed ONLY clearly fictional funding calls labelled demo. Coordinator/admin manage.
- saved_items: add funding_id (migration updates CHECK + unique).
- Domain events (core/events.py, in-process pub/sub): application.submitted/decided,
  collaboration.requested/responded, booking.decided, project.reviewed, profile.verified.
- notifications (user_id, type, payload jsonb, read_at); NotificationService subscribes to events.
  GET /me/notifications, POST /me/notifications/{id}/read, POST /me/notifications/read-all.
  Channel interface (InAppChannel now; EmailChannel stub logging to console).
- Deadline reminders: APScheduler in-process job (disable-able via env) that notifies users about
  saved opportunities/funding with deadlines in 7 and 1 days; idempotent (no duplicate reminders).
- "New relevant opportunity" notification using Step 9 scores above a threshold.
- Frontend: funding list/detail/save, notification bell with unread count, notifications page,
  upcoming deadlines widget on dashboard.
- Tests: events create correct notifications, users only read own notifications, reminder job
  idempotency, authz rows.

COMMIT: feat: implement funding  (+ feat: implement notifications)  -> tag v0.2.0
```

---

### STEP 13: Semantic Embeddings, pgvector & Hybrid Search

```
<common header, N=13, name=semantic-ai>

GOAL: Semantic discovery that measurably beats Step 9.

- Optional install extra: pip install -e ".[ml]" (sentence-transformers, all-MiniLM-L6-v2, CPU).
  App must still run without it (falls back to Phase 1).
- Migration: CREATE EXTENSION vector; entity_embeddings (entity_type, entity_id, model_name,
  content_hash, embedding vector(384), UNIQUE(entity_type, entity_id, model_name)), HNSW index.
- Embedding pipeline: build text per entity, skip if content_hash unchanged, background task on save,
  scripts/backfill_embeddings.py.
- Hybrid recommender: top-N by vector similarity -> re-rank with Phase 1 structured score;
  explanations combine semantic similarity + concrete tag overlaps.
- Natural-language search ("researchers working on AI and cloud computing"): embed query,
  pgvector search, merge with FTS via reciprocal rank fusion.
- Evaluation: rerun eval set; must beat Step 9 on precision@5 / nDCG@10; record in docs/ai-evaluation.md.
  If it doesn't, report honestly and keep Phase 1 as default.
- Frontend: "semantic" toggle/indicator in search, improved reasons.

COMMIT: feat: implement semantic search
```

---

### STEP 14: Analytics, Collaboration Network, Audit UI & Moderation

```
<common header, N=14, name=analytics>

GOAL: Insight and administration.

- Coordinator (scoped) + admin (platform) analytics endpoints: projects by status/area, opportunities
  and application funnel, equipment utilisation, funding saves, verification backlog, trends over time.
  Aggregation queries with indexes; no raw PII.
- Collaboration network: nodes = researchers/students (opted-in), edges = co-authorship,
  project membership, accepted collaborations. Endpoint returns graph JSON (scoped).
- Frontend: analytics dashboards (Recharts), network visualisation (lightweight graph lib),
  audit-log viewer with filters (admin), moderation queue for content_reports with actions
  (hide/archive/dismiss, audited), platform settings page (admin).
- Tests: scope limits (coordinator sees only own department), admin-only endpoints, no PII leaks.

COMMIT: feat: implement analytics
```

---

### STEP 15: Docker (optional), CI/CD, Deployment & Hardening

```
<common header, N=15, name=deploy>

GOAL: Reproducible, deployable, hardened prototype. Everything stays optional and provider-agnostic.

- Optional docker-compose.yml (postgres+pgvector, backend, frontend) - local dev must still work without it.
- GitHub Actions: backend (ruff, mypy, pytest with postgres service), frontend (typecheck, lint,
  format, build, vitest), optional Playwright job.
- Security hardening: security headers + CSP, SameSite/Secure cookie config for cross-site deploy
  (or same-site via rewrite proxy - document choice in ADR), dependency audit (pip-audit, npm audit),
  secret scanning, rate-limit review, error responses never leak internals, /docs off in prod.
- Free-tier deployment guide (verify current free-tier terms first): frontend Vercel/Netlify,
  backend Render (or similar), Postgres Neon/Supabase with pgvector; ML memory note
  (precompute embeddings or keep Phase 1 in prod).
- Final docs: README complete (all sections), ER diagram, system diagram, RBAC matrix,
  API docs link, roadmap, demo accounts (fictional), disclaimer.

COMMIT: chore: add CI and deployment  -> tag v1.0.0
```

---

## PART D: Useful follow-up prompts

- **Verify a step:** "Run the full verification for Step N again from a clean state and report PASSED/FAILED/NOT VERIFIED for each item. Fix nothing yet; just report."
- **Fix failures:** "Fix the failed checks from your last report at the root cause. Don't disable rules or skip tests. Re-run everything."
- **Review before merge:** "Review the diff of feat/step-N against main for security issues, RBAC gaps, missing tests, and scope creep. List the findings, then wait."
- **Resume after interruption:** "Read CLAUDE.md, the README roadmap and `git log`. Tell me which step we're on, what's done and what's left in it, then continue with the remaining plan items only."

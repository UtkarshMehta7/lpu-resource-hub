# LPU Research Intelligence & Collaboration Hub

> **Prototype disclaimer:** This is a proposed/prototype research platform and is not an official LPU system unless formally adopted or authorized. It is not connected to any real LPU system or data. All people, projects, publications, facilities and funding records it shows are fictional demo data.

## Project overview

A role-based research discovery and collaboration platform designed for the Lovely Professional University (LPU) ecosystem. It connects students, faculty/researchers, research projects, opportunities, publications, facilities, equipment and funding calls, and ranks those connections for each user with explainable, locally run matching.

The platform is built to run entirely on a local machine at zero cost: React, FastAPI, PostgreSQL and open-source ML. No paid APIs, no mandatory cloud services and no mandatory Docker.

## Problem statement

Faculty research expertise, ongoing projects and available lab facilities are invisible across department boundaries. As a result, potential collaborators and interested students can't find each other, equipment goes under-used, and funding-call deadlines are frequently missed.

The planned solution: researcher profiles with expertise tags and publications, a searchable expertise directory across departments, a research-opportunity board where students can browse and apply, funding-call listings with deadline reminders, a facility catalogue with a booking calendar, and tag-based collaboration suggestions.

## Current development status

**Step 11: facilities, equipment and booking.** What exists today:

| Area | Status |
|---|---|
| FastAPI backend skeleton with settings, logging, error envelope and CORS | Done |
| PostgreSQL connection (SQLAlchemy 2.0 + psycopg 3) | Done |
| Alembic migrations (baseline, then `users`/`refresh_tokens`, then coordinator scope + `audit_logs`) | Done |
| `GET /health` (liveness) and `GET /health/ready` (readiness) | Done |
| React + TypeScript + Vite + Tailwind shell with a backend status card | Done |
| Registration, login, silent-refresh, logout with Argon2id + rotating refresh tokens | Done |
| Frontend auth UI (register/login, protected `/account` page, silent session restore) | Done |
| Permission map + `require_permission`, admin user management, append-only audit log | Done |
| Admin Users page (role changes, activate/deactivate) behind a role-gated route | Done |
| Schools/departments, shared skill + research-area taxonomy with aliases and suggestions | Done |
| Student/researcher profiles, skills, research areas, onboarding-completeness tracking | Done |
| Faculty verification: department-scoped coordinator queue, verify/reject, audited | Done |
| Onboarding wizard, profile page, tag picker, coordinator verification queue (UI) | Done |
| Fictional demo seed data (`scripts/seed_demo_data.py`) | Done |
| Researcher directory (full-text + typo-tolerant search, filters), researcher detail, opt-in student discovery, unified search | Done |
| Research projects: draft → coordinator review → active → completed/archived, team members, visibility rules, review queue | Done |
| Publications: ordered internal/external author lists, DOI de-duplication, project links, shown on researcher and project pages | Done |
| Opportunity board (draft → open → closed/filled) and application workflow with status timeline, applicant review, auto-add to project team | Done |
| Direct collaboration requests (send/accept/decline/cancel) with inbox/sent, privacy rules and a per-user send limit | Done |
| Explainable recommendations (skills + research areas + TF-IDF text) with per-suggestion reasons, cold start and an offline evaluation | Done |
| Role dashboards (student, faculty, coordinator, admin), saved items, content reports with a moderation queue | Done |
| Browser end-to-end tests (Playwright) covering the four MVP flows | Done |
| Facility and equipment catalogue with a week calendar, booking requests, approvals, and double-booking prevented by the database | Done |
| Lovely Professional University branding across the frontend (full name, LPU shortform in tight spaces) | Done |
| Funding, notifications and all other domain features | **Not implemented yet** (see [roadmap](#development-roadmap)) |

## Technology stack

| Layer | Technology |
|---|---|
| Frontend | React 19, TypeScript (strict), Vite, Tailwind CSS 4, React Router, Axios |
| Backend | Python 3.12+, FastAPI, Pydantic / pydantic-settings, SQLAlchemy 2.0, Alembic |
| Database | PostgreSQL 16+ (psycopg 3 driver) |
| Quality | Ruff (lint + format), mypy (strict), pytest · ESLint, Prettier, `tsc` |
| Planned AI | scikit-learn (TF-IDF), Sentence Transformers, pgvector, all running locally |

## Local prerequisites (macOS)

| Tool | Version | Install |
|---|---|---|
| Homebrew | latest | <https://brew.sh> |
| Python | 3.12 or newer | `brew install python@3.12` |
| Node.js | 22.12 or newer (LTS) | `brew install node@22` (or use nvm) |
| PostgreSQL | 16 or newer | see [PostgreSQL setup](#postgresql-setup) |
| Git | any recent | ships with Xcode Command Line Tools: `xcode-select --install` |

Check them:

```bash
python3.12 --version
node --version
npm --version
psql --version
git --version
```

## PostgreSQL setup

Pick **one** option.

### Option A: Homebrew PostgreSQL

```bash
brew install postgresql@17
brew services start postgresql@17

# postgresql@17 is keg-only; put its tools on your PATH (zsh):
echo 'export PATH="$(brew --prefix postgresql@17)/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
psql --version
```

Homebrew creates a superuser with your macOS username, so the commands below work without `sudo`.

To stop the server later: `brew services stop postgresql@17`.

### Option B: Postgres.app

1. Download Postgres.app from <https://postgresapp.com>, move it to **Applications** and open it.
2. Click **Initialize** to create and start a server (PostgreSQL 16 or 17).
3. Add its command-line tools to your PATH:

   ```bash
   sudo mkdir -p /etc/paths.d
   echo /Applications/Postgres.app/Contents/Versions/latest/bin | sudo tee /etc/paths.d/postgresapp
   ```

4. Open a new terminal and check: `psql --version`.

Postgres.app also creates a superuser with your macOS username.

### Create the application role and databases (both options)

```bash
# Create a login role; you will be asked to choose a password.
createuser --pwprompt lpu_hub

# Development and test databases, owned by that role
createdb --owner=lpu_hub lpu_research_hub
createdb --owner=lpu_hub lpu_research_hub_test

# Verify you can connect (enter the password you chose)
psql -h localhost -U lpu_hub -d lpu_research_hub -c "SELECT version();"
```

Put the password you chose into `backend/.env` (next section). Never commit it.

## Environment variables

Each app has a committed `.env.example` with safe placeholders. Copy it to `.env`, which is git-ignored, and fill in real values.

### Backend: `backend/.env`

| Variable | Required | Example | Purpose |
|---|---|---|---|
| `APP_ENV` | yes | `development` | `development`, `test` or `production` |
| `DATABASE_URL` | yes | `postgresql+psycopg://lpu_hub:PASSWORD@localhost:5432/lpu_research_hub` | Main database. The `postgresql+psycopg://` prefix is required. |
| `TEST_DATABASE_URL` | for DB tests | `postgresql+psycopg://lpu_hub:PASSWORD@localhost:5432/lpu_research_hub_test` | Used only by `pytest -m db` |
| `CORS_ORIGINS` | yes | `http://localhost:5173` | Comma-separated allowed browser origins |
| `LOG_LEVEL` | no | `INFO` | `DEBUG` … `CRITICAL` |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | no | `5` / `5` | Connection pool size |
| `DB_CONNECT_TIMEOUT` | no | `5` | Seconds before a connection attempt fails |
| `JWT_SECRET_KEY` | yes | (generate one, see below) | Signs access-token JWTs. At least 32 characters. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | no | `15` | Access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | no | `7` | Refresh token (cookie) lifetime |
| `REFRESH_COOKIE_SAMESITE` | no | `lax` | `lax`, `strict` or `none` (`none` needs HTTPS; for a cross-domain deploy) |

Generate `JWT_SECRET_KEY` with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

The backend refuses to start with a clear message naming the variable when a required value is missing or invalid. With `APP_ENV=production` it also rejects wildcard or `localhost` CORS origins, disables `/docs`, and exits if the database is unreachable at startup.

If your password contains special characters (`@`, `:`, `/`, `%`, `#`), URL-encode them in `DATABASE_URL`, e.g. `@` becomes `%40`.

### Frontend: `frontend/.env`

| Variable | Required | Example |
|---|---|---|
| `VITE_API_BASE_URL` | yes | `http://localhost:8000` |

Every `VITE_*` variable is embedded in the public JavaScript bundle. **Never put secrets in the frontend.**

## Backend setup

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"

cp .env.example .env
# edit .env: set the lpu_hub password in DATABASE_URL and TEST_DATABASE_URL

alembic upgrade head      # applies the empty baseline revision 0001
alembic current           # should print: 0001 (head)
```

## Frontend setup

```bash
cd frontend
npm install
cp .env.example .env
```

## How to run the backend

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:create_app --factory --reload
```

- API: <http://localhost:8000>
- Interactive docs (development only): <http://localhost:8000/docs>

The startup log shows either `Database connection OK (...)` or a clear error with a hint. In development the API still starts when the database is down, and `/health/ready` reports the problem.

## How to run the frontend

```bash
cd frontend
npm run dev
```

Open <http://localhost:5173>. The **Backend connection** card calls `GET /health/ready` and shows **Connected**, **Degraded** (API up, database down) or **Unreachable** (API down), with a **Check again** button.

Production build and local preview:

```bash
npm run build
npm run preview      # http://localhost:4173
```

The preview runs on port 4173. To call the backend from it, add that origin to `CORS_ORIGINS`, for example `http://localhost:5173,http://localhost:4173`.

## How to verify `/health`

With the backend running:

```bash
curl -i http://localhost:8000/health
# HTTP/1.1 200 OK
# {"status":"ok"}

curl -i http://localhost:8000/health/ready
# HTTP/1.1 200 OK
# {"status":"ok","database":"ok"}
```

To see failure behaviour, stop PostgreSQL (`brew services stop postgresql@17`, or **Stop** in Postgres.app):

```bash
curl -i http://localhost:8000/health/ready
# HTTP/1.1 503 Service Unavailable
# {"status":"degraded","database":"unavailable"}

curl -i http://localhost:8000/health     # still 200: liveness never touches the DB
```

| Endpoint | Meaning | Touches DB |
|---|---|---|
| `GET /health` | Liveness: the process is up | No |
| `GET /health/ready` | Readiness: API → PostgreSQL chain works | Yes (`SELECT 1`) |

## Authentication API

All business APIs live under `/api/v1`. Self-registration is limited to
`student` and `faculty` (`admin` and `research_coordinator` accounts are
created later, by an administrator — see the roadmap). The refresh token is
never returned in a JSON body: it travels only as an `httpOnly` cookie scoped
to `/api/v1/auth`, rotated on every use, with reuse detection that revokes
the whole token family (see [ADR 0002](docs/adr/0002-authentication.md)).

| Endpoint | Auth | Notes |
|---|---|---|
| `POST /api/v1/auth/register` | none | `{email, password, full_name, role}`, `role` is `student` or `faculty`. Password: 10+ characters, not a common password. Sets the refresh cookie. |
| `POST /api/v1/auth/login` | none | `{email, password}`. Sets the refresh cookie. |
| `POST /api/v1/auth/refresh` | refresh cookie + `X-Requested-With` header | Rotates the refresh token, returns a new access token. |
| `POST /api/v1/auth/logout` | refresh cookie + `X-Requested-With` header | Revokes the session and clears the cookie. |
| `POST /api/v1/auth/change-password` | `Authorization: Bearer` | `{current_password, new_password}`. Revokes every existing session. |
| `GET /api/v1/me` | `Authorization: Bearer <access_token>` | Current user's profile. |

`/auth/register` and `/auth/login` are rate-limited (5 requests/minute per
IP+email, in-memory). `/auth/refresh` and `/auth/logout` require a
`X-Requested-With` header (any non-empty value) as CSRF defence, since a
cross-site HTML form cannot set custom headers.

```bash
curl -s -c cookies.txt -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"jane@example.com","password":"correcthorsebattery","full_name":"Jane Doe","role":"student"}'

curl -s -b cookies.txt -c cookies.txt -X POST http://localhost:8000/api/v1/auth/refresh \
  -H "X-Requested-With: XMLHttpRequest"
```

### Creating the first admin account

`admin` and `research_coordinator` accounts can't self-register. Create the
first admin from the command line:

```bash
cd backend && source .venv/bin/activate
python -m scripts.create_admin
```

It prompts for email, full name and password (never pass the password as a
CLI argument or environment variable that could end up in shell history).

## RBAC & admin API

Backend-enforced role-based access control: `require_permission("resource:action")`
checks the caller's role against a permission map (`app/core/permissions.py`,
full design in [`docs/rbac-matrix.md`](docs/rbac-matrix.md)). `401` = not
authenticated, `403` = authenticated but not allowed, `404` = you must not
learn the resource exists. `RESEARCH_COORDINATOR` inherits everything
`FACULTY` can do, plus `taxonomy:manage` and `profile:verify` of its own.

| Endpoint | Notes |
|---|---|
| `GET /api/v1/admin/users` | Paginated, filter by `role`/`is_active`. |
| `PATCH /api/v1/admin/users/{id}` | `full_name`, `coordinator_scope_type`, `coordinator_scope_id` only — role and activation are never mass-assignable here. A `department` scope id must name a real department. |
| `POST /api/v1/admin/users/{id}/role` | `{role}`. Rejects changing your own role, and rejects any change that would leave zero active admins. |
| `POST /api/v1/admin/users/{id}/activate` / `/deactivate` | Deactivating revokes every refresh token for that user. Rejects removing the last active admin. |
| `GET /api/v1/admin/audit-logs` | Paginated, filter by `entity_type`/`entity_id`/`actor_id`/`action`. Role/activation changes and verification decisions are recorded here. |
| `GET/POST /api/v1/admin/schools`, `PATCH/DELETE .../{id}` | Admin only. Deleting a school cascades to its departments. |
| `GET/POST /api/v1/admin/departments`, `PATCH/DELETE .../{id}` | Admin only. Deleting a department clears its users' `department_id`. |

## Profiles, taxonomy, verification & directory API

| Endpoint | Auth | Notes |
|---|---|---|
| `GET/PUT /api/v1/me/profile` | any signed-in user | Shape depends on your role (student vs researcher); responses carry a `profile_type` discriminator. `GET` is `404` until you create one. Saving a *researcher* profile submits it for verification. |
| `PUT /api/v1/me/skills` | any signed-in user | `[{skill_id, proficiency}]`, replaces the whole set. |
| `PUT /api/v1/me/research-areas` | any signed-in user | `[{research_area_id, is_expertise}]`, replaces the whole set. |
| `GET /api/v1/skills?q=`, `GET /api/v1/research-areas?q=&parent_id=` | any signed-in user | Name search; an exact alias hit (`ML`) also returns its canonical tag. |
| `POST /api/v1/tags/suggestions` | any signed-in user | Suggest a new skill/area for coordinator review. |
| `POST /api/v1/taxonomy/skills` / `research-areas` / `aliases` | `taxonomy:manage` | Coordinator or admin. Research areas nest at most two levels. |
| `GET /api/v1/admin/tag-suggestions`, `POST .../{id}/approve` / `/reject` | `taxonomy:manage` | Approving creates the real skill/research area. |
| `GET /api/v1/coordinator/verification-queue` | `profile:verify` | Coordinators see only their own department; admins see everything. |
| `POST /api/v1/researchers/{id}/verify` | `profile:verify` | `{decision: verified\|rejected, comment}`. Outside your department scope returns `404`. You can never verify yourself. |

| `GET /api/v1/researchers` | any signed-in user | `q` (full-text + misspelled-name tolerant), `school_id`, `department_id`, `research_area_id` (includes child areas), `skill_id`, `availability`, `verified_only`, `sort`, pagination. No email in results. |
| `GET /api/v1/researchers/{id}` | any signed-in user | Public profile with research areas and skills. |
| `GET /api/v1/students` | `student:discover` (faculty, coordinator, admin) | Opted-in students only (`is_discoverable`), public fields only. |
| `GET /api/v1/search?q=&types=researchers` | any signed-in user | Unified search; more `types` arrive in later steps. |
| `GET /api/v1/schools`, `GET /api/v1/departments` | any signed-in user | Read-only lists for filters. |

| `GET/POST /api/v1/projects` | any signed-in user / `project:create` | List with `q`, `status`, `mine`, `owner_id`, `department_id`, `research_area_id`, `skill_id`. Only projects you may see are returned. |
| `GET/PATCH/DELETE /api/v1/projects/{id}` | owner for writes | Hidden projects are `404`. Owner may edit in draft or active. `DELETE` removes a draft, archives anything else. |
| `POST /api/v1/projects/{id}/submit` / `/complete` / `/archive` | owner (admin may archive any) | Submit requires a verified researcher profile. Invalid transitions are `409`. |
| `POST /api/v1/projects/{id}/review` | `project:review` | `{decision: approve\|reject, comment}` — comment required to reject. Own-department only; never your own project. Audited. |
| `GET/POST /api/v1/projects/{id}/members`, `DELETE …/members/{user_id}` | owner for writes | Team members can see the project even while it's a draft. |
| `GET /api/v1/coordinator/review-queue` | `project:review` | Pending projects in your department (admin: all). |
| `GET/POST /api/v1/facilities`, `GET/PATCH/DELETE /api/v1/facilities/{id}` | any signed-in user reads / `facility:manage` writes | Filters `q`, `department_id`. A coordinator manages only facilities in the department they oversee (`403` outside it); admins manage any. |
| `GET/POST /api/v1/equipment`, `GET/PATCH/DELETE /api/v1/equipment/{id}` | same | Each item carries its own booking rules: `students_allowed`, `requires_approval`, `max_hours`, `min_lead_hours`, `maintenance_status`. |
| `GET /api/v1/equipment/{id}/availability?from&to` | any signed-in user | Approved bookings in the window plus the equipment's rules. Only the periods are returned — who holds a slot isn't public. |
| `POST /api/v1/bookings` | any signed-in user | Rules enforced server-side (`403` students where not allowed, `409` under maintenance, `422` too long / too soon / in the past). Equipment with `requires_approval=false` is booked outright, still subject to the overlap constraint. |
| `GET /api/v1/me/bookings`, `GET /api/v1/bookings/{id}` | owner / scoped coordinator / admin | Others get `404`. |
| `POST /api/v1/bookings/{id}/approve` / `/reject` | `booking:approve` (own department) | **Approving a slot that overlaps an approved booking is `409`** — decided by a PostgreSQL `EXCLUDE` constraint, not application logic. Audited. |
| `POST /api/v1/bookings/{id}/cancel` / `/complete` | owner (cancel: before it starts) | Cancelling after the start is `409`; completing before the end is `409`. |
| `GET /api/v1/coordinator/booking-queue` | `booking:approve` | Pending requests for equipment in your department (admin: all). |
| `GET /api/v1/me/dashboard` | any signed-in user | Role-specific sections: a student's applications, deadlines and matches; a faculty member's projects, openings and pending applications; a coordinator's queues and department activity; an admin's platform counts and recent audit entries. Coordinators get the faculty section too. Every count is scoped like the matching list endpoint. |
| `GET/POST /api/v1/me/saved`, `DELETE /api/v1/me/saved/{id}` | any signed-in user | Bookmarks of a project, opportunity or researcher (exactly one per row). Saving something you can't see is `404`; a bookmark never widens visibility, so an item that later becomes private simply stops appearing. |
| `POST /api/v1/reports` | any signed-in user | Report content you can see (`404` otherwise, so reports can't probe for hidden items). One open report per person per item. |
| `GET /api/v1/admin/reports`, `POST /api/v1/admin/reports/{id}/resolve` | `report:moderate` (coordinator, admin) | Moderation queue; resolving is audited. |
| `GET /api/v1/recommendations?type=&limit=` | any signed-in user | `type` is `opportunities` (default), `projects`, `researchers` or `collaborators`. Returns cards with a match score and the reasons behind it. Business filters (visibility, eligibility, deadlines, already applied, self) run in SQL before scoring. A sparse profile returns the newest items with `cold_start: true`. |
| `POST /api/v1/collaborations` | `collaboration:send` (student, faculty, coordinator) | `{recipient_id, project_id?, message}`. Researchers are always reachable; students only if discoverable; admins never (`404`). One pending request per person per project (`409`). Limited to 10 sends per hour per user. |
| `GET /api/v1/me/collaborations?box=inbox\|sent&status=` | any signed-in user | Your own requests, either direction. |
| `GET /api/v1/collaborations/{id}` | sender or recipient | Anyone else gets `404`. A referenced project's title is shown only to viewers who can see the project. |
| `POST /api/v1/collaborations/{id}/accept` / `/decline` | recipient only | The sender gets `403`; a non-pending request is `409`. |
| `POST /api/v1/collaborations/{id}/cancel` | sender only | Same rules, mirrored. |
| `GET/POST /api/v1/opportunities` | any signed-in user / `opportunity:create` | Filters `q`, `type`, `status`, `department_id`, `skill_id`, `project_id`, `deadline_after`, `deadline_before`, `mine`. Drafts are visible only to the poster, the scoped coordinator and admins. Faculty post on their own **active** projects; coordinators also department-wide. |
| `GET/PATCH /api/v1/opportunities/{id}` | poster for edits | Editable while draft or open. `positions` can't drop below accepted applicants. |
| `POST /api/v1/opportunities/{id}/publish` / `/close` | poster (close: also scoped coordinator, admin) | New opportunities start as drafts; publishing opens them. Non-poster closes are audited. |
| `POST /api/v1/opportunities/{id}/applications` | `application:submit` | Students → student openings; faculty/coordinators → collaborations only. Not after the deadline, not unless open, never twice (`409`). |
| `GET /api/v1/opportunities/{id}/applications` | poster; scoped coordinator & admin read-only | Anyone else who can see the opportunity gets `403`. |
| `GET /api/v1/me/applications`, `GET /api/v1/applications/{id}` | applicant / poster / scoped coordinator / admin | Includes the status timeline. Others get `404`. |
| `POST /api/v1/applications/{id}/status` | poster only | `{status, note, add_to_project}`. Accepting can add the applicant to the project team and marks the opportunity `filled` when the last position goes — all in one transaction. Audited. |
| `POST /api/v1/applications/{id}/withdraw` | applicant only | Only before a final decision. |
| `GET/POST /api/v1/publications` | any signed-in user / `publication:create` | List with `q`, `author_id` (authored or created), `year`, `project_id`, `research_area_id` (via linked projects). Linked projects you can't see are omitted. |
| `GET/PATCH/DELETE /api/v1/publications/{id}` | creator for edits; creator or admin for delete | Authors are an ordered list of `{user_id}` or `{external_name}`. Duplicate DOI (case/prefix-insensitive) is `409`. Admin deletes are audited. |

Directory, project list and search endpoints are rate-limited to 60 requests/minute per IP; sending collaboration requests is limited to 10 per hour per user. `/search` now covers researchers, projects, publications and opportunities.

Setting `>= 3` skills and `>= 3` research areas flips
`onboarding_complete` on `GET /api/v1/me`, which is what gates
recommendations later (Step 9).

### Demo data

```bash
cd backend && source .venv/bin/activate
python -m scripts.seed_demo_data     # prompts for a password, or set SEED_DEMO_PASSWORD
```

Creates fictional demo data — 3 schools, 8 departments, 60 skills, 40
research areas (with aliases such as `ML` → Machine Learning), 1 admin, 2
coordinators, 25 faculty and 80 students, every account named
`Demo Faculty 07`-style and flagged `is_demo`. Re-running it creates
nothing new.

## Quality checks and tests

```bash
# Backend (inside backend/, venv active)
ruff check .
ruff format --check .
mypy
pytest                    # includes DB tests when TEST_DATABASE_URL is set
pytest -m "not db"        # skip tests that need PostgreSQL

# Frontend (inside frontend/)
npm run typecheck
npm run lint
npm run format:check
npm run test
npm run build
```

## Project structure

```
lpu-research-hub/
├── backend/
│   ├── app/
│   │   ├── main.py              # create_app() factory, lifespan, middleware
│   │   ├── core/                # config, logging, error envelope, security, deps, rate_limit, permissions, pagination
│   │   ├── db/                  # declarative base, engine/session, model_registry
│   │   └── modules/
│   │       ├── health/          # /health and /health/ready
│   │       ├── auth/            # register, login, refresh, logout, change-password
│   │       ├── users/           # /me
│   │       ├── admin/           # admin user management, schools, departments
│   │       ├── audit/           # append-only audit log
│   │       ├── taxonomy/        # skills, research areas, aliases, suggestions
│   │       ├── profiles/        # student/researcher profiles, skills, areas
│   │       ├── researchers/     # verification, directory, search
│   │       └── projects/        # projects, review workflow, members
│   ├── alembic/                 # migration environment + versions/ (0001 baseline … 0006 research projects)
│   ├── scripts/                 # create_admin.py, seed_demo_data.py
│   ├── tests/                   # pytest suite (db tests marked `db`)
│   ├── alembic.ini
│   ├── pyproject.toml
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── app/                 # App, router, layouts
│   │   ├── components/          # layout/ (header, banner), ui/ (primitives)
│   │   ├── features/            # home/, system-status/, auth/, admin/, taxonomy/, profiles/, onboarding/, researchers/, directory/, projects/
│   │   ├── test/                # Vitest setup
│   │   └── lib/                 # config, api client + error normalisation
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts, tsconfig*.json, eslint.config.js, .prettierrc
│   └── .env.example
├── docs/
│   ├── architecture.md          # approved architecture (source of truth)
│   ├── development.md           # day-to-day workflow and conventions
│   ├── rbac-matrix.md           # full role -> permission design
│   └── adr/0001-foundation-decisions.md … 0006-research-projects.md
├── CLAUDE.md
├── lpu-roadmap-prompts.md
├── .editorconfig
├── .gitignore
├── LICENSE
└── README.md
```

## End-to-end tests

Playwright drives the four MVP flows (faculty → coordinator → student →
admin) in a real browser against the development stack and the seeded demo
accounts:

```bash
cd backend && python -m scripts.seed_demo_data      # once, if not already seeded
cd frontend && E2E_PASSWORD='<seed password>' npx playwright test
```

The config starts the Vite dev server and the API for you (and reuses them
if they're already running). The flows create their own timestamp-suffixed
project and opportunity, so they can be run repeatedly.

## Development roadmap

| Step | Scope |
|---|---|
| 0 | Project foundation |
| 1 | Users, authentication, JWT with rotating refresh tokens |
| 2 | RBAC core: permission map, policies, audit hook, authorization test scaffold |
| 3 | Schools, departments, taxonomy, student and researcher profiles, faculty verification, demo seed data |
| 4 | Researcher directory and full-text search |
| 5 | Research projects with coordinator review workflow and team members |
| 6 | Publications |
| 7 | Research opportunities and applications |
| 8 | Collaboration requests |
| 9 | Explainable tag + TF-IDF recommendations with an evaluation set |
| 10 | Role-specific dashboards, saved items, moderation and UI polish: MVP complete |
| **11** | **Facilities, equipment and booking calendar, double-booking prevented in the database (this commit)** |
| 12 | Funding opportunities, notifications, deadline reminders |
| 13 | Embeddings, pgvector, hybrid semantic search |
| 14 | Research analytics, collaboration network, audit-log UI, moderation |
| 15 | Optional Docker, CI/CD, free-tier deployment, hardening |

Full details: [`docs/architecture.md`](docs/architecture.md).

## Deployment

Not yet. Deployment (Step 15) will stay provider-agnostic: static frontend hosting (e.g. Vercel or Netlify), a Python web service (e.g. Render) and any PostgreSQL host with pgvector. Everything is configured through environment variables; no provider SDKs in application code.

## License

[MIT](LICENSE). Replace it if your university or course requires a different licence.

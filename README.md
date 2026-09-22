# LPU Research Intelligence & Collaboration Hub

> **Prototype disclaimer:** This is a proposed/prototype research platform and is not an official LPU system unless formally adopted or authorized. It is not connected to any real LPU system or data. All people, projects, publications, facilities and funding records it shows are fictional demo data.

## Project overview

A role-based research discovery and collaboration platform designed for the Lovely Professional University (LPU) ecosystem. It connects students, faculty/researchers, research projects, opportunities, publications, facilities, equipment and funding calls, and ranks those connections for each user with explainable, locally run matching.

The platform is built to run entirely on a local machine at zero cost: React, FastAPI, PostgreSQL and open-source ML. No paid APIs, no mandatory cloud services and no mandatory Docker.

## Problem statement

Faculty research expertise, ongoing projects and available lab facilities are invisible across department boundaries. As a result, potential collaborators and interested students can't find each other, equipment goes under-used, and funding-call deadlines are frequently missed.

The planned solution: researcher profiles with expertise tags and publications, a searchable expertise directory across departments, a research-opportunity board where students can browse and apply, funding-call listings with deadline reminders, a facility catalogue with a booking calendar, and tag-based collaboration suggestions.

## Current development status

**Step 2: RBAC core & audit log.** What exists today:

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
| Profiles, projects and all other domain features | **Not implemented yet** (see [roadmap](#development-roadmap)) |

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
authenticated, `403` = authenticated but not allowed. `RESEARCH_COORDINATOR`
inherits everything `FACULTY` can do; today neither has any permissions yet
(no domain resources exist), so only `ADMIN` can call these endpoints.

| Endpoint | Notes |
|---|---|
| `GET /api/v1/admin/users` | Paginated, filter by `role`/`is_active`. |
| `PATCH /api/v1/admin/users/{id}` | `full_name`, `coordinator_scope_type`, `coordinator_scope_id` only — role and activation are never mass-assignable here. |
| `POST /api/v1/admin/users/{id}/role` | `{role}`. Rejects changing your own role, and rejects any change that would leave zero active admins. |
| `POST /api/v1/admin/users/{id}/activate` / `/deactivate` | Deactivating revokes every refresh token for that user. Rejects removing the last active admin. |
| `GET /api/v1/admin/audit-logs` | Paginated, filter by `entity_type`/`entity_id`/`actor_id`/`action`. Role and activation changes are recorded here. |

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
│   │       ├── admin/           # admin user management
│   │       └── audit/           # append-only audit log
│   ├── alembic/                 # migration environment + versions/ (0001 baseline, 0002 users/refresh_tokens, 0003 coordinator scope + audit_logs)
│   ├── scripts/                 # create_admin.py
│   ├── tests/                   # pytest suite (db tests marked `db`)
│   ├── alembic.ini
│   ├── pyproject.toml
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── app/                 # App, router, layouts
│   │   ├── components/          # layout/ (header, banner), ui/ (primitives)
│   │   ├── features/            # home/, system-status/, auth/, admin/ (one folder per feature)
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
│   └── adr/0001-foundation-decisions.md, 0002-authentication.md, 0003-rbac-core.md
├── CLAUDE.md
├── lpu-roadmap-prompts.md
├── .editorconfig
├── .gitignore
├── LICENSE
└── README.md
```

## Development roadmap

| Step | Scope |
|---|---|
| 0 | Project foundation |
| 1 | Users, authentication, JWT with rotating refresh tokens |
| **2** | **RBAC core: permission map, policies, audit hook, authorization test scaffold (this commit)** |
| 3 | Schools, departments, taxonomy, student and researcher profiles, faculty verification, demo seed data |
| 4 | Researcher directory and full-text search |
| 5 | Research projects with coordinator review workflow and team members |
| 6 | Publications |
| 7 | Research opportunities and applications |
| 8 | Collaboration requests |
| 9 | Explainable tag + TF-IDF recommendations with an evaluation set |
| 10 | Role-specific dashboards and UI polish: **MVP complete** |
| 11 | Facilities, equipment and booking calendar (double-booking prevented in the database) |
| 12 | Funding opportunities, notifications, deadline reminders |
| 13 | Embeddings, pgvector, hybrid semantic search |
| 14 | Research analytics, collaboration network, audit-log UI, moderation |
| 15 | Optional Docker, CI/CD, free-tier deployment, hardening |

Full details: [`docs/architecture.md`](docs/architecture.md).

## Deployment

Not yet. Deployment (Step 15) will stay provider-agnostic: static frontend hosting (e.g. Vercel or Netlify), a Python web service (e.g. Render) and any PostgreSQL host with pgvector. Everything is configured through environment variables; no provider SDKs in application code.

## License

[MIT](LICENSE). Replace it if your university or course requires a different licence.

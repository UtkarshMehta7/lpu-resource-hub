# Development guide

Setup instructions are in the [README](../README.md). This page covers day-to-day work.

## Daily commands

```bash
# Backend
cd backend && source .venv/bin/activate
uvicorn app.main:create_app --factory --reload
ruff check . && ruff format --check . && mypy && pytest

# Frontend
cd frontend
npm run dev
npm run typecheck && npm run lint && npm run format:check && npm run build
```

Auto-fix formatting: `ruff format .` and `ruff check --fix .` in the backend, `npm run format` in the frontend.

## Git workflow

- `main` always runs. Work on short-lived branches such as `feat/auth` or `chore/tooling`.
- Use [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`.
- Keep each commit focused on one step or concern. Don't mix unrelated changes.
- Before committing, run all quality checks and `git status`. Never commit `.env`, `.venv`, `node_modules` or `dist`.

## Database migrations

```bash
cd backend && source .venv/bin/activate

# After changing or adding models:
alembic revision --autogenerate --rev-id 0002 -m "create users"
# Review the generated file in alembic/versions/ carefully, then:
alembic upgrade head

alembic downgrade -1      # roll back one revision
alembic history           # list revisions
```

Rules:

- Every schema change is a reviewed migration. Never call `Base.metadata.create_all()`.
- Use sequential four-digit revision IDs (`--rev-id 0002`, `0003`, …) so file names sort in order.
- Enable PostgreSQL extensions (`CREATE EXTENSION IF NOT EXISTS ...`) in the migration of the step that first needs them.
- New model modules must be imported where `alembic/env.py` can see them (a model registry is introduced in Step 1).

## Adding a backend module

1. Create `app/modules/<name>/` with `router.py`, `schemas.py`, `service.py`, and later `models.py`, `repository.py` and `policies.py`.
2. Keep HTTP concerns in the router and business rules in the service. Services never import FastAPI.
3. Mount the router in `create_app()` under `/api/v1`.
4. Add tests under `tests/` and a migration if the schema changed.

## Adding a frontend feature

1. Create `src/features/<name>/` with `api.ts` (typed calls through `@/lib/api/client`), hooks, components and pages.
2. Put reusable primitives in `src/components/ui/`, not inside features.
3. Every data view handles loading, error and empty states.
4. Never put secrets in `VITE_*` variables. They are public.

## Tests

- Backend tests build `Settings` explicitly, so they don't depend on your `.env`.
- Tests marked `db` need `TEST_DATABASE_URL`, pointing at the separate `lpu_research_hub_test` database. They are skipped, with the reason printed, when it isn't set. `pytest -m "not db"` runs everything else.
- Frontend component tests (Vitest + React Testing Library) arrive with the first real components in Step 1.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Field required` / `validation error for Settings` at startup | A required variable is missing from `backend/.env`. The message names it. |
| `must use the 'postgresql+psycopg://' scheme` | Change the `DATABASE_URL` prefix to `postgresql+psycopg://`. |
| `Database connection FAILED ... Is PostgreSQL running?` | Start PostgreSQL (`brew services start postgresql@17`, or Postgres.app) and check the credentials. |
| `password authentication failed` | The password in `DATABASE_URL` doesn't match the one set by `createuser --pwprompt`. |
| Status card says **Unreachable** | The backend isn't running, or `VITE_API_BASE_URL` is wrong. |
| Browser console shows a CORS error | Add the frontend origin (e.g. `http://localhost:5173`) to `CORS_ORIGINS` and restart the backend. |
| `VITE_API_BASE_URL is not set` | Run `cp frontend/.env.example frontend/.env` and restart `npm run dev`. |

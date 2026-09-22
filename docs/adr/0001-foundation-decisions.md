# ADR 0001: Step 0 foundation decisions

- **Status:** Accepted
- **Date:** 2026-09-22
- **Context:** Step 0 establishes the repository, tooling and the minimum runtime needed to prove the browser → FastAPI → PostgreSQL chain, without any business functionality.

## Decisions

1. **Two health endpoints.** `GET /health` is liveness and returns exactly `{"status": "ok"}` without touching dependencies. `GET /health/ready` is readiness: it runs `SELECT 1` and returns `200 {"status":"ok","database":"ok"}` or `503 {"status":"degraded","database":"unavailable"}`. Hosting platforms want a liveness probe that does not fail on a database blip, and the frontend needs to prove the full chain.
2. **Health routes at the root**, not under `/api/v1`, because probes conventionally live there. All business APIs will be mounted under `/api/v1` from Step 1.
3. **`app/modules/health/` is the first module.** It sets the per-module pattern.
4. **App factory run with `uvicorn --factory`.** `app.main` exposes `create_app()` and no module-level `app` object. *Deviation from the plan*, which proposed `uvicorn app.main:app`. Importing `app.main` therefore never reads `.env` or creates an engine, so tests can build apps with explicit settings. The command is `uvicorn app.main:create_app --factory --reload`.
5. **Engine per app instance.** The lifespan creates the engine and session factory and stores them on `app.state`, instead of import-time globals. Each app (including test apps) owns its pool, and it is disposed on shutdown. `get_db()` reads the factory from `app.state`.
6. **Startup behaviour when the database is down.** Development and test log a clear error (host, database and user; password never logged) and start anyway, with `/health/ready` reporting 503. Production fails fast.
7. **Settings.** pydantic-settings. `APP_ENV`, `DATABASE_URL` and `CORS_ORIGINS` are required with no defaults. The `postgresql+psycopg://` driver prefix is enforced. In production, wildcard and local CORS origins are rejected and `/docs` is disabled. `DB_CONNECT_TIMEOUT` (default 5 s) was added so readiness checks cannot hang.
8. **Config tests added.** `tests/test_config.py` was not in the original plan's file list. It implements checklist item 9 (clear failure on missing configuration) as an automated test.
9. **CORS credentials disabled for now.** `allow_credentials=False` until Step 1 introduces the refresh-token cookie.
10. **Error envelope from day one.** `{"error": {"code", "message", "details"}}` for HTTP errors, validation errors (422), database outages (503) and unexpected errors (500, no stack trace in the response).
11. **Empty baseline migration `0001`.** Proves the Alembic pipeline without premature tables. The database URL comes from `Settings`, never from `alembic.ini`. PostgreSQL extensions are deferred to the steps that need them.
12. **Omitted directories.** `backend/scripts/` and `frontend/src/types/` are not created until they have content (Steps 1 and 3).
13. **Tooling.**
    - Backend: pip + venv (no extra tools on macOS; `pyproject.toml` also works with uv), Ruff for both lint and format, mypy in strict mode with the pydantic plugin, pytest.
    - Frontend: ESLint with type-aware typescript-eslint rules, Prettier, and `tsc -b` in strict mode.
    - No Makefile or task runner.
14. **Axios now, TanStack Query later.** Axios is the approved client and has one instance with error normalisation. TanStack Query, React Hook Form, Zod and Vitest arrive in Step 1 with the features that need them.
15. **Direct cross-origin calls in development.** No Vite proxy. This exercises the same CORS path a separately hosted frontend will use.
16. **MIT licence.** Replace it if the course or university requires another.

## Consequences

- The backend can be imported and tested without a database or a `.env` file.
- Adding a module means adding a folder under `app/modules/` and one `include_router` call.
- Contributors must use the factory command to run the server; this is documented in the README.

# ADR 0017: Step 15 deployment, CI and hardening

- **Status:** Accepted
- **Date:** 2026-09-23
- **Context:** The final step makes the prototype reproducible and deployable without committing to a provider, and closes the hardening items that only matter once something is exposed to the internet.

## Decisions

1. **Docker is optional and stays optional.** `docker-compose.yml` (PostgreSQL with pgvector, API, nginx-served frontend) exists for people who would rather not install Postgres and Node, but the documented path is still local processes. The compose file carries a throwaway secret and says so.
2. **Migrations never run on container start.** The Dockerfile's `CMD` starts the server only; `alembic upgrade head` is a release step. Two instances booting together would otherwise race on the same schema.
3. **CI runs the same commands a developer runs**: `ruff check`, `ruff format --check`, `mypy`, `pytest` against a real PostgreSQL service (the `pgvector/pgvector:pg17` image, because `vector` is not a trusted extension), plus a migration round-trip (`upgrade → downgrade base → upgrade → check`). The frontend job runs typecheck, lint, format check, vitest and build.
4. **The ML extra gets its own job.** The main backend job installs *without* it, which is also a test: the suite must pass with semantic search absent, because that is how it will run on a small instance. A second job installs the extra and runs the semantic tests with a cached model.
5. **Playwright is opt-in in CI** (on `main`, or on a PR labelled `e2e`): it needs both halves running and seeded data, and it is slow. It seeds its own fictional demo data with a CI-only password.
6. **Security headers are middleware, outermost**, so they also cover error responses. The API's CSP is `default-src 'none'` — this service returns JSON and nothing should ever load, run or frame it. The docs pages get a looser policy (they pull Swagger UI from jsDelivr) and are disabled in production anyway. HSTS is production-only: sending it in development would pin `localhost` to HTTPS in the developer's own browser.
7. **Cookies: the rewrite proxy is the recommended deployment.** Serving the API under the frontend's domain keeps the refresh cookie `SameSite=Lax` and avoids third-party cookies entirely, which matters because browsers increasingly block them — a blocked refresh cookie silently signs people out. `SameSite=None; Secure` remains supported by configuration for a genuinely cross-site deployment; CSRF is covered either way by the `X-Requested-With` header requirement plus an explicit CORS allowlist.
8. **Dependency audits and secret scanning run on a schedule, not just on push.** Advisories appear after code is merged, so `pip-audit` and `npm audit` (production dependencies, high and above) also run weekly, and gitleaks scans the full history — a secret that was committed and later removed is still leaked.
9. **Free-tier guidance is dated and sourced.** `docs/deployment.md` records what was true in September 2026 with links, and says plainly that terms change. It also warns that Render's own free Postgres expires 30 days after creation, which makes it the wrong choice for anything worth keeping.

## Consequences

- The `e2e` CI job runs against seeded demo data on a throwaway database, so it is not a smoke test of a real deployment. A post-deploy health check is the remaining gap.
- `npm audit` is restricted to production dependencies; a dev-only advisory won't block a prototype, at the cost of a slower reaction to tooling vulnerabilities.
- Nothing here provisions infrastructure. There is no Terraform and no provider lock-in — the trade-off is that a deploy involves following a document rather than running one command.

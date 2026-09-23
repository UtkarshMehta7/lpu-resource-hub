# Deployment

Provider-agnostic, with one worked free-tier example. Nothing here is
required to run the project locally (see the README).

> **Free-tier terms change.** The specifics below were checked in September
> 2026 and are linked to their sources. Re-check before you rely on them.

## What has to be true wherever you deploy

1. **PostgreSQL 16+ with `pg_trgm`, `btree_gist` and (for semantic search)
   `pgvector`.** `vector` is not a *trusted* extension, so a plain database
   owner cannot create it — the provider must offer it, and it may need to be
   enabled once by a superuser before migration `0013` runs.
2. **Migrations run as a release step**, not on container start:
   `alembic upgrade head`. Two instances starting at once would otherwise race.
3. **Secrets come from the environment.** `JWT_SECRET_KEY` (32+ characters,
   unique per environment), `DATABASE_URL`, `CORS_ORIGINS`. Never commit them.
4. **`APP_ENV=production`**, which switches on HSTS, secure cookies, and
   switches *off* the interactive API docs.
5. **HTTPS everywhere.** The refresh cookie is `Secure` in production, so
   plain HTTP simply won't keep anyone signed in.

## The cookie decision: proxy (recommended) or cross-site

The refresh token lives in an httpOnly cookie, and where you put the frontend
decides how it behaves. Both options are supported by configuration alone —
the trade-off is explained in [ADR 0017](adr/0017-deployment-and-hardening.md).

**Option A — same-site via a rewrite proxy (recommended).** Serve the API
under the frontend's own domain, e.g. `https://app.example.org/api/*` →
`https://api.example.org/*`. The cookie stays `SameSite=Lax`, and nothing
depends on third-party cookies, which browsers increasingly block.

```toml
# frontend/netlify.toml — proxy /api/* to the backend
[[redirects]]
  from = "/api/*"
  to = "https://YOUR-BACKEND/api/:splat"
  status = 200
  force = true
```

Then build the frontend with `VITE_API_BASE_URL=/` (same origin — a path
prefix, see `src/lib/config.ts`) and set `CORS_ORIGINS` to the site's URL.

**Option B — cross-site.** Frontend and API on different domains:

```
REFRESH_COOKIE_SAMESITE=none      # requires Secure, i.e. HTTPS
CORS_ORIGINS=https://app.example.org
```

CSRF is still covered: every request carries the `X-Requested-With` header,
which a cross-site form cannot set, and the CORS allowlist is explicit. The
risk you accept is browser policy: some browsers already block third-party
cookies by default, and a blocked refresh cookie means people get signed out
when their access token expires.

## The adopted pathway: Neon + Render + Netlify, no cost

This is the path the repository is configured for. Two files do most of the
work: [`render.yaml`](../render.yaml) and
[`frontend/netlify.toml`](../frontend/netlify.toml).

```
Neon      Postgres + pgvector          free tier
Render    FastAPI, built from source   free web service
Netlify   static bundle + /api proxy   free tier
```

No Docker, no registry, no card. Docker remains available and is also free on
Render's Docker runtime -- it simply buys nothing here and costs build
minutes, so the Blueprint builds from source. See [Docker](#docker-optional).

### Step by step

1. **Neon.** Create a project. Run `CREATE EXTENSION vector;` once. Copy the
   connection string and change the scheme to `postgresql+psycopg://`.

2. **Migrate and create the first admin from your own machine**, pointed at
   Neon. The API image deliberately does not migrate on start, and Render's
   pre-deploy hook is not on the free tier, so this is the release step:

   ```bash
   cd backend
   DATABASE_URL="postgresql+psycopg://…neon…" alembic upgrade head
   DATABASE_URL="postgresql+psycopg://…neon…" python -m scripts.create_admin
   ```

   **Do not seed demo data into production.** Production starts with one
   administrator; every other account is provisioned from it through the UI
   (ADR 0019).

3. **Render.** New Blueprint from the repository -- it reads `render.yaml`.
   Paste `DATABASE_URL` and `CORS_ORIGINS` when prompted; `JWT_SECRET_KEY` is
   generated for you and never appears in the repository. Note the service
   hostname it gives you.

4. **Netlify.** New site from the repository -- it reads
   `frontend/netlify.toml`. Replace both occurrences of `REPLACE-ME` with the
   Render hostname from step 3, commit, and let it rebuild.

5. **Close the loop.** Set `CORS_ORIGINS` on Render to the Netlify URL.

Because Netlify proxies `/api` to Render, the browser only ever talks to one
origin: the refresh cookie stays first-party, `SameSite=lax` is correct, and
none of the third-party-cookie rules apply. That is Option A above, and it is
why it is the recommended one.

## Service notes (September 2026)

| Piece | Service | What to know |
|---|---|---|
| Frontend | Netlify | Static build plus proxy redirects; `netlify.toml` sets `VITE_API_BASE_URL=/`. |
| Backend | Render (free web service) | Spins down after **15 minutes** of inactivity and takes ~1 minute to wake; 750 instance-hours per workspace per month. |
| Database | Neon (free) | ~0.5 GB storage, compute auto-suspends after ~5 minutes idle and resumes in well under a second. pgvector available. |
| Database (alternative) | Supabase (free) | pgvector on all plans; projects **pause after 7 days of inactivity**, and only two active free projects per organisation. |

Render's own free Postgres is the one to avoid for anything you care about:
it **expires 30 days after creation** (plus a 14-day grace period), so use
Neon or Supabase for the database even when the API runs on Render.

### Backend on Render

`render.yaml` encodes this, so there is nothing to type:

```
Build:   pip install --upgrade pip && pip install -e "."
Start:   uvicorn app.main:create_app --factory --host 0.0.0.0 --port $PORT
Health:  /health          (liveness only -- it never touches the database)
Release: alembic upgrade head, run from your machine (see step 2 above)
```

Environment: `APP_ENV=production`, `DATABASE_URL`, `JWT_SECRET_KEY`,
`CORS_ORIGINS`, and `REFRESH_COOKIE_SAMESITE=none` only if you abandon the
proxy and split the domains.

### Memory, and what to do about the ML extra

The optional `[ml]` extra pulls in sentence-transformers and PyTorch —
several hundred MB of wheels plus the model in RAM. That does not fit
comfortably in a 512 MB free instance. Two honest options:

- **Leave it out in production.** Without the extra the app runs normally:
  `/search/semantic` answers with the lexical ranking and reports
  `semantic_used: false`, and recommendations are unaffected (they use the
  Step 9 scoring by default anyway — see [ai-evaluation.md](ai-evaluation.md)).
- **Precompute embeddings elsewhere.** Run `python -m scripts.backfill_embeddings`
  against the production database from a machine that has the extra
  installed. The vectors live in `entity_embeddings`, so *query-time* search
  still needs the model to embed the incoming question — meaning this only
  helps if you also keep a small worker that can embed queries.

## Docker (optional)

`docker-compose.yml` brings up PostgreSQL with pgvector, the API and the
frontend behind nginx:

```bash
docker compose up --build
docker compose exec backend alembic upgrade head
docker compose exec backend python -m scripts.seed_demo_data
```

The frontend lands on <http://localhost:8080>, the API on
<http://localhost:8000>. The compose file is for local convenience: it
contains a throwaway `JWT_SECRET_KEY` and is not a production deployment.

## After deploying — a short checklist

- [ ] `GET /health/ready` returns 200 (it checks the database).
- [ ] `/docs` returns 404 (production disables it).
- [ ] Response headers include `Content-Security-Policy`,
      `X-Content-Type-Options`, `Strict-Transport-Security`.
- [ ] Sign in, reload the page, and confirm you stay signed in (this is what
      proves the cookie decision above is configured correctly).
- [ ] Create an admin with `python -m scripts.create_admin`, then sign in.
- [ ] Only seed demo data if this is a demo: it creates fictional accounts
      that share one password.

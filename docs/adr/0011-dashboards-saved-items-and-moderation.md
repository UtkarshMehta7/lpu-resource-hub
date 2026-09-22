# ADR 0011: Step 10 dashboards, saved items, moderation and MVP polish

- **Status:** Accepted
- **Date:** 2026-09-22
- **Context:** Step 10 completes the MVP: role dashboards, saved items, content reports with a moderation queue, UI polish and browser end-to-end tests.

## Decisions

1. **No new modules for saved items or dashboards.** Saved items live in `profiles` (personal collections belong under `/me/...`) and the dashboard lives in `analytics`, the planned module that Step 14 will grow into full analytics. Only `reports` is new, and it was already on the planned-module list.
2. **One dashboard endpoint with role sections**, not four endpoints. `GET /me/dashboard` returns `student`, `faculty`, `coordinator` and `admin` sections; the ones a caller has no business seeing are absent. A coordinator gets the faculty section too, because coordinators inherit faculty abilities.
3. **Dashboard aggregates are scoped exactly like the list endpoints they summarise.** A coordinator's counts cover their department, a faculty member's cover their own work. Nothing aggregates across a boundary the caller couldn't already browse item by item.
4. **Saved items never widen visibility.** Targets are re-checked against the usual visibility filters when the list is read, so a project that later becomes private silently drops out rather than leaking a title. Saving something invisible is `404`.
5. **Exactly one target per saved row** (`CHECK num_nonnulls(project_id, opportunity_id, researcher_id) = 1`), with a partial unique index per kind so one person can't save the same thing twice. Step 12 adds `funding_id` to the same row.
6. **Reports are polymorphic but verified.** `content_reports` stores `target_type` + `target_id` with no FK (the target can be four different tables), and the service resolves the target through the reporter's own visibility filter before writing — so a report can't be used to discover hidden content. One *open* report per reporter per item, enforced by a partial unique index.
7. **`report:moderate` is granted to coordinator and admin now** (the planned matrix had it at Step 14), because Step 10 ships the review queue. Moderators see the whole queue rather than a department-scoped slice: reports are about content, the queue is small, and resolving is audited.
8. **Polish is structural, not cosmetic:** shared `Skeleton`/`EmptyState` components (every empty list names the next action), one role-based nav list driving both the desktop bar and a working mobile menu, and the signed-in landing page now goes to the dashboard.

## What the end-to-end tests found

Playwright drove the four MVP flows in a real browser for the first time, and two real bugs surfaced immediately — neither was visible to the API tests:

- **CORS blocked every browser request.** `allow_headers` listed only `Authorization` and `Content-Type`, but the frontend sends `X-Requested-With` on every request as its CSRF guard, so each preflight returned `400` and the app could never reach the API. Fixed, with a regression test (`tests/test_app.py`) that preflights *with* that header.
- **React StrictMode signed users out on reload.** The bootstrap silent refresh bypassed the API client's single-flight guard, so StrictMode's double-invoked effect fired two concurrent `POST /auth/refresh` calls with the same rotating cookie; the backend correctly treated the second as token reuse and revoked the family. The bootstrap now goes through the same deduplicated `refreshAccessToken`, covered by `lib/api/refresh.test.ts`.

## Consequences

- The E2E suite runs against the **development** stack and seeded demo accounts, not a throwaway database, so it needs the seed password (`E2E_PASSWORD`) and leaves behind the projects and opportunities it creates (timestamp-suffixed, so reruns don't collide). A dedicated E2E database is a Step 15 concern.
- The flows share one signed-in page per role: logging in per test would trip the Step 1 login rate limiter (5/minute per IP+email).
- Moderators see reports across departments; if that becomes a problem, scoping needs a rule for targets that have no department (publications), which is why it isn't scoped today.

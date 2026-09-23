# ADR 0016: Step 14 analytics, collaboration network and moderation

- **Status:** Accepted
- **Date:** 2026-09-23
- **Context:** Step 14 adds the reporting layer: analytics for coordinators and admins, a collaboration network, an audit-log viewer, moderation actions and a settings page.

## Decisions

1. **Scope is a query concern, not a parameter.** `insights.scope_for(user)` returns the department a coordinator oversees or "the whole platform" for an admin, and every aggregate applies it inside the SQL. There is no `department_id` parameter to tamper with, and a coordinator with no department scope gets an impossible scope (a zero UUID) rather than accidentally seeing everything.
2. **Aggregates return counts, never people.** The only near-exception is the verification backlog's "oldest waiting since", which is a timestamp — enough to see a queue going stale without naming anyone.
3. **The network graph is built from the three relationships the platform actually records**: co-authorship, shared projects, and accepted collaboration requests. Nodes carry name, role and department only. Students appear solely if they opted in to discovery (`is_discoverable`), matching the Step 4 rule that opting out means invisible.
4. **The graph is drawn without a graph library.** People sit on a circle ordered by degree, so the busiest collaborators end up adjacent and edges stay short. It renders identically for identical data (no simulation), reads fine at department scale, and adds no dependency. A force layout is the natural upgrade if the graph outgrows a few hundred nodes.
5. **Charts use Recharts** — the one new frontend dependency, and only for the dashboards.
6. **Moderation can hide content, using states that already exist.** `hide_target` archives a reported project or closes a reported opening: reversible, visible to the owner, and recorded in the audit row (`hidden: true/false`). Publications and profiles have no equivalent state, so it is a deliberate no-op there rather than an invented "hidden" flag.
7. **Platform settings are read-only.** They come from environment variables, so a mutable settings screen would be a lie about where configuration lives; the page shows behaviour (weights, scheduler, token lifetimes) and never secrets.
8. **The audit viewer is admin-only and read-only**, over the existing append-only log, with filters by action and entity type.

## Consequences

- `MAX_NODES` caps the network at 150 people per request. Beyond that the picture stops being readable anyway, and a paged or clustered view would be the honest next step rather than a bigger payload.
- Trends are bucketed by calendar month over six months in Python from grouped SQL counts; a longer window or daily granularity would want a proper time-series query.
- Analytics run against live tables with no materialised views. That is fine at this size; the queries are grouped counts over indexed columns, and caching can come when it is actually slow. A post-merge verification found two of those columns unindexed (`users.department_id`, `researcher_profiles.verification_status`) — migration 0015 adds them.

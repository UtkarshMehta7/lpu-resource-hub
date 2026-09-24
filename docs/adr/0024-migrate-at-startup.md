# ADR 0024: The deployed instance migrates itself at boot

- **Status:** Accepted
- **Date:** 2026-09-24
- **Supersedes:** the "migrations are a release step, never on container
  start" rule in [ADR 0017](0017-deployment-and-hardening.md).

## Context

The old rule was sound in theory: two instances booting at once could run the
same migration concurrently, so migrating was a human step run from a
workstation before deploying.

In practice it failed twice in three days, the same way each time. Code that
needed a migration reached production before the migration did, because the
code ships automatically on a push to `main` and the migration does not.

1. Chat shipped without migration 0019. Every collaboration **acceptance**
   answered 500, and the acceptance was lost with it.
2. The pair model shipped without migration 0021. **Sending** a collaboration
   request answered "An unexpected error occurred" for real users on the live
   site, and stayed broken until somebody with the connection string was
   available.

The second failure is the telling one: the fix required a credential only one
person had. The system could not repair itself, and the rule meant to protect
it was the reason it could not.

The race the rule guarded against is real. It is also solved, cheaply, by a
lock the database already provides.

## Decision

The application applies outstanding migrations at startup.

**Without a lock**, and that was learned the hard way. The first version held
`pg_advisory_lock` for the duration, which is the standard answer and is wrong
against this database: `DATABASE_URL` points at Neon's *pooler*, PgBouncer in
transaction mode. A session-level advisory lock is taken on a backend
connection that is returned to the pool immediately, so it is never released.
The container logged "Waiting for the migration lock…", never bound its port,
and Render cancelled the deploy — leaving the previous image serving and the
schema exactly as far behind as before.

The race the lock guarded against needs two migrators. This service runs one
instance with `WEB_CONCURRENCY=1`. If that changes, the lock must be taken on
a **direct, non-pooled** Neon endpoint, or be a transaction-level lock around
a single-transaction migration.

**If the migration fails, the app refuses to start.** Serving with a schema
the code does not match is worse than not serving: every request against the
missing table answers 500, which is the exact failure this is meant to
prevent. A deploy that cannot migrate should fail loudly at the platform
level, not quietly at the API.

**Off by default** (`RUN_MIGRATIONS_ON_START`). Local development and the test
suite migrate explicitly and keep doing so — a schema changing under you
mid-task is its own kind of unpleasant. Deployments turn it on; `render.yaml`
sets it.

`backend/scripts/release.sh` stays, for running a migration deliberately
against a database before a deploy, or for data repairs that want a human
watching.

## Consequences

- A push to `main` is now sufficient to deploy a schema change. That is the
  point, and it is also the risk: a destructive migration now runs
  unattended. Migration 0021 merges conversation threads, and had this been in
  place first it would have merged them without anybody watching. Data
  migrations that cannot be undone should still be run deliberately via
  `release.sh` before the code that needs them merges.
- Startup is slower by however long the migrations take, and the platform's
  health check must tolerate that. On this free instance the whole chain runs
  in seconds.
- The lock id is a constant. It must never change: two versions of the app
  with different ids would not see each other's lock, which is the race back
  again.
- A test asserts startup returns rather than blocking. "It hangs" and "it is
  slow" look identical to a platform health check, and the difference is a
  cancelled deploy.
- Anything that runs before the port is bound can stop the service from
  existing. Migrations are now the only such thing, and they are bounded by
  the migrations themselves.

## Alternatives considered

- **Keep the manual release step and remember harder.** It failed twice; the
  second time it needed a credential one person had.
- **A pre-deploy hook.** The right answer, and not available on Render's free
  tier — which is a constraint of this project, not a preference.
- **Migrate in the container entrypoint rather than the app.** Same effect,
  but the lock and the "refuse to start" behaviour would live in a shell
  script instead of in tested Python.
- **Let it serve and answer 500 on the missing table.** What happens today.

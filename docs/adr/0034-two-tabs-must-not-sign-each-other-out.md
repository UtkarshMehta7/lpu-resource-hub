# ADR 0034: Two tabs must not sign each other out

- **Status:** Accepted
- **Date:** 2026-10-08

## Context

The session dropped twice during use, with nothing on screen to explain it
and nothing in the frontend that could have caused it. Each time it looked
like an expiry, and each time the access token was nowhere near its lifetime.

There is exactly one code path that ends a session instantly:

```python
# app/modules/auth/service.py
if existing.revoked_at is not None:
    # already rotated out, being presented again: replay
    _revoke_family(db, existing.family_id)
    raise InvalidRefreshTokenError
```

Refresh tokens rotate on every use, and re-presenting one that has already
been rotated out revokes **every token descended from that login**. That is
deliberate — it is how a stolen token is contained — and
`tests/test_auth.py` asserts it.

The frontend knows this. `refreshAccessToken` single-flights through a
module-level `refreshPromise`, and its comment says why: several requests
failing with a 401 at once, or StrictMode running the bootstrap effect twice,
must produce one POST.

**That promise is per tab. The cookie is per browser.** Two tabs of the app
cannot see each other's in-flight refresh, so both read the same cookie and
both POST it. The first rotates it; the second arrives holding a token that
no longer exists; the backend reads replay and revokes the family. Both tabs
are signed out, mid-sentence, and the reuse detection worked exactly as
designed.

The window is only as wide as two overlapping requests, which is why it
presented as an occasional mystery rather than a reproducible bug. It opens
every time a second tab is opened, a window is restored, or anything refreshes
the token from outside the app — which is how it was finally caught.

## Decision

**Serialise the refresh across tabs with the Web Locks API, and change
nothing on the backend.**

```ts
function withRefreshLock(run: () => Promise<string>): Promise<string> {
  const locks: LockManager | undefined = navigator.locks;
  if (!locks) return run();
  return locks.request(REFRESH_LOCK, run);
}
```

The lock is per-origin, so every tab of the app contends for the same one.
The second tab waits, then refreshes with the cookie the first left behind —
an ordinary rotation, not a replay. Where the API is absent (jsdom, older
Safari) it runs unserialised, which is the behaviour that already shipped.

### Rejected: a grace window on the backend

Accept the immediately-previous token for a few seconds after rotation and
hand back the successor it already issued.

It fixes the same race and it is a common pattern, but it buys that by making
reuse detection deliberately blind for the length of the window — the one
mechanism in this system that contains a stolen token. The problem is that
two clients raced, not that the backend was too strict, so the fix belongs
where the race is. A client-side lock costs nothing in security and nothing
in protocol.

### Rejected: sharing the access token between tabs over BroadcastChannel

It avoids the second round trip, but it means a tab trusting a token it did
not obtain and keeping a second copy of the auth state in sync. The lock
makes the second refresh correct rather than unnecessary, and a refresh is
cheap.

## Consequences

- Two tabs no longer sign each other out. The second simply waits.
- A tab blocked behind another's refresh waits at most for that request,
  which Axios caps at its 10 s timeout.
- Reuse detection keeps its current strictness: a genuinely replayed token
  still kills the family on the first attempt.
- The fallback path is untested in browsers without Web Locks, because it is
  the code that was already running everywhere.

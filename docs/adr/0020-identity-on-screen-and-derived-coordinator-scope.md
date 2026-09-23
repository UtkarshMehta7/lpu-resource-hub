# ADR 0020: Separate sign-in entrances, a derived coordinator scope, and the UID on screen

- **Status:** Accepted
- **Date:** 2026-09-24
- **Builds on:** [ADR 0015](0015-registration-number-sign-in.md) (registration-number
  sign-in), [ADR 0019](0019-account-provisioning-hierarchy.md) (provisioning
  hierarchy).

## Context

Three problems surfaced from using the deployed instance rather than from
reading the code, and all three are about the same thing: whether the
interface tells the truth about who somebody is and what they may do.

1. **One sign-in page for two audiences.** Administration and the research
   platform are different products with different shapes. Anyone could sign in
   at either entrance, so an administrator arriving at the main page landed on
   a dashboard instead of the console they came for, and the administration
   page was visible to people it does not concern.

2. **A coordinator who oversaw nothing.** `coordinator_scope_type` /
   `coordinator_scope_id` were independent columns an admin was expected to
   set by hand. Appointing a coordinator from the users page set the role and
   left the scope `NULL`, which the platform read as "oversees nothing": an
   empty verification queue and `403` on every decision, with nothing on the
   coordinator's own screen saying why. Reported as "coordinators are unable to
   verify faculty, only administrator is able".

3. **Names without identity.** Lists showed "Demo Faculty 07" and nothing
   else. At a university of this size names repeat, and the registration
   number is what people actually use to tell two of them apart — but it was
   shown on two pages out of a dozen, and search would not match it.

## Decision

**Two entrances, enforced on the server.** `LoginRequest.portal` is
`"admin" | "main" | None`. Administrators may only use `/admin/login` and
everyone else only `/login`; `None` still works, so an API client or a cached
older build is not locked out by a field it has never heard of. The portal
check runs **after** password verification. Refusing earlier would make the
administration page an oracle: a wrong password against an admin account
would answer differently from a wrong password against a student's, telling an
attacker which registration numbers belong to administrators.

**A coordinator's scope is derived, not entered.** The platform only has
department-level coordinators today, so the scope is not an independent
choice: it *is* the department. `admin/service.py::_sync_coordinator_scope`
sets it whenever the role or the department changes, and clears it when
somebody stops being a coordinator. Setting a scope explicitly remains
possible for the case where the authority is deliberately not the
coordinator's own department, but it is no longer something an admin has to
remember.

**The registration number is shown wherever a person is named.** One
component, `components/ui/Uid`, renders it beside the name; every response
schema that carries a person carries `registration_number`; and the directory
matches it as a case-insensitive prefix — an identifier is not prose, so it
does not go through the language analyser.

## Consequences

- Fixing the service layer did not fix the deployed database. Coordinators
  appointed before this change still had no scope, so **migration 0018**
  backfills the scope from the department, and only where none was set, so a
  deliberately different scope survives. Tests run the migration's own
  statement rather than a retyped copy.
- The users page now shows each coordinator's scope, with a one-click repair
  when it is missing. The failure that was silent is now visible where the
  role is set: a class of bug that produced a `403` with no explanation is
  now a sentence on the screen.
- Two entrances mean two places to keep working. The portal rule has its own
  test module (`tests/test_portals_and_scope.py`), including that a refused
  portal issues no session and that the check runs after the password.
- `Uid` is the single place that styling lives, so the UID cannot drift into a
  different shape on each page.

## Alternatives considered

- **Redirect instead of refuse.** Signing an administrator in at the main page
  and redirecting them is friendlier and enforces nothing; the URL is not a
  boundary. Refused, with a clear 403.
- **Drop the scope columns and always read the department.** Tempting, and
  wrong for the reason the columns exist: school-level and university-wide
  coordinators are a planned extension, and dropping the columns would mean a
  schema change to get them back.
- **Repair the scope lazily, when a coordinator next signs in.** Hides a
  data problem inside a request path, and leaves the queue empty until the
  coordinator happens to log in. A migration is the honest place for it.

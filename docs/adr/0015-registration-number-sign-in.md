# ADR 0015: Sign in with the LPU registration number

- **Status:** Accepted
- **Date:** 2026-09-23
- **Context:** The platform is meant for the LPU ecosystem, where people already identify themselves by a registration (or employee) number in UMS. Email-based self-registration for students also meant anyone could create a student account.

## Decisions

1. **The registration number is the credential identifier.** `users.registration_number` is unique, stored trimmed and upper-cased, indexed, and set once at creation. Email is now **optional contact information** and is never accepted at sign-in.
2. **Students do not self-register.** `/auth/register` accepts faculty only. Student accounts are created by someone who already has standing: admins anywhere, faculty and coordinators within their own department (`user:create`, plus a scope check in `admin/accounts.py`). A department passed by a non-admin is ignored in favour of their own — the request can't widen its own authority.
3. **New accounts get a temporary password, shown to the creator exactly once.** It is generated with `secrets`, stored only as a hash, and returned in the creation response and nowhere else. There is no email service in this project (by the zero-cost constraint), so a link-based invite would still have been copied by hand; a temporary password keeps one mechanism instead of two.
4. **A temporary password unlocks nothing but replacing itself.** `must_change_password` gates the API: `get_authenticated_user` allows `GET /me` and `POST /auth/change-password`, while `get_current_user` — used by every other endpoint — answers `403 password_change_required`. The frontend routes such users to `/set-password` and nowhere else. Changing the password clears the flag and revokes every session, so the temporary one is dead the moment it is used.
5. **Rate limiting is re-keyed to the identifier being tried.** Registration numbers are sequential and semi-public, so the account half of the credential pair is guessable; only the password is secret. The limiter keys on IP + registration number, and login failures stay indistinguishable between "no such account" and "wrong password" so the form can't be used to enumerate a roster.
6. **Demo data uses obviously fake numbers** (`DEMOFACULTY01`, `DEMOSTUDENT01`, and `DEMO000001`-style values for rows backfilled by migration 0014). A demo row must never look like a real LPU registration number.

## Consequences

- This contradicts the original architecture note that students self-register; `docs/architecture.md` is updated accordingly.
- With email optional, there is no self-service password reset: a forgotten password needs an admin. That is acceptable while there is no mail service, and it is the main thing an SSO integration would fix.
- A registration number typed into a form proves nothing by itself — it is a lookup key, not an authentication factor. Trust comes from *who created the account*. If LPU ever exposes SSO (Entra/Google Workspace/LDAP), that becomes the right front door and this field becomes the join key; the column is deliberately shaped to survive that change.
- Registration numbers are personal data: they are shown to the person themselves, to admins, and in the coordinator verification queue, but never on public directory cards (which already omit email).

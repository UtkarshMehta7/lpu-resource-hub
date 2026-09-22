# ADR 0009: Step 8 collaboration requests

- **Status:** Accepted
- **Date:** 2026-09-22
- **Context:** Step 8 adds direct collaboration requests between users, optionally about a specific project, with an inbox and a sent box.

## Decisions

1. **One transition table.** `collaborations/policies.py: TRANSITIONS` allows PENDING → ACCEPTED/DECLINED for the recipient and PENDING → CANCELLED for the sender. Nothing else writes `status`; a request that has already been answered is `409`.
2. **Wrong party is `403`, stranger is `404`.** Both parties can see a request, so a sender trying to accept their own request gets `403`. Anyone else — including admins — gets `404`: a private message between two people isn't theirs to know about.
3. **Contactability mirrors the directory.** Researchers (faculty, coordinators) are reachable by anyone; students only when `is_discoverable` is true; admins are never collaboration targets. An uncontactable recipient is `404`, the same answer as a non-existent one, so sending can't be used to probe who exists or who opted out. The rule is the same for every sender, so it never exposes more than Step 4's directory already does.
4. **The partial unique index is the duplicate guard.** `uq_collaboration_requests_pending` is `UNIQUE(sender_id, recipient_id, project_id) WHERE status = 'pending'` with `NULLS NOT DISTINCT`, so two project-less pending requests to the same person also collide (PostgreSQL 15+). The service inserts and converts the violation into `409` rather than checking first, so concurrent sends can't both win. Once a request is answered or cancelled, a new one may be sent.
5. **A referenced project must be visible to the sender** (`404` otherwise), and its title is resolved per viewer: a recipient who can't see a draft project sees `project_title: null` rather than the title.
6. **Sending is rate-limited per user, not per IP** (10/hour): the thing being protected is a person's inbox, and the sender is authenticated, so the account is the right key. It reuses the in-memory `RateLimiter` from Step 1 with its own limiter on `app.state`.
7. **`collaboration:send` is granted to STUDENT and FACULTY** (coordinators inherit it); admins deliberately have no grant.
8. **No audit rows.** These are ordinary user-to-user messages, not privileged actions; `responded_at` and the status are the record.

## Consequences

- Accepting a request doesn't add anyone to a project team; joining a project goes through an opportunity application (Step 7) or the owner adding a member.
- There are no notifications yet, so a recipient only sees new requests when they open their inbox. Step 12 adds notifications.

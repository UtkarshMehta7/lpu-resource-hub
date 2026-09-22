# ADR 0013: Step 12 funding calls, notifications and deadline reminders

- **Status:** Accepted
- **Date:** 2026-09-23
- **Context:** Step 12 adds funding calls, in-app notifications driven by domain events, and deadline reminders — the first work in this project that happens without a user request.

## Decisions

1. **Domain events are in-process and synchronous.** `app/core/events.py` is a tiny bus: modules publish (`application.submitted`, `booking.decided`, `project.reviewed`, …) and handlers run **inside the publisher's transaction**. A notification therefore commits with the action that caused it — no notification for a rolled-back decision, and no silently missing one. It is deliberately not a queue: with one subscriber (the notification writer), a broker would be infrastructure and cost for no benefit. A failing handler fails the action, which is the honest trade-off at this size.
2. **Publishers don't know their subscribers.** `applications`, `collaborations`, `bookings`, `projects`, `researchers` and `opportunities` import only the bus; `register_notification_handlers()` wires the notification module once at startup in `app/main.py`.
3. **Events are published *after* the row they describe is flushed.** Approving a booking flushes the status change first, so an overlap violation surfaces as `409` instead of exploding inside a handler — a bug this step introduced and the booking tests caught.
4. **Notification payloads are self-contained JSONB.** Everything the UI needs to render a line and a link is captured when the notification is written, so listing notifications is one query and a later rename can't rewrite history.
5. **Idempotency lives in the database.** A `dedupe_key` column with a partial unique index (`WHERE dedupe_key IS NOT NULL`) means "one reminder per user per item per lead time" and "one relevance notification per opening per person" are facts, not conventions. The reminder job can run as often as it likes.
6. **Channels are an interface with one honest implementation.** `InAppChannel` writes rows; `EmailChannel` logs what it would send. The seam exists so the service never assumes one channel, without pretending email works (and without a paid provider).
7. **The scheduler is APScheduler in the API process, off by default.** `ENABLE_SCHEDULER=true` starts a background thread that calls `send_deadline_reminders`; tests and CLI runs never start it. The job itself is a plain function taking a Session, so it can be run by hand or from a test. With several workers, more than one may run it — harmless, because of decision 5.
8. **Relevance notifications reuse the Step 9 scorer.** `notifications/matching.py` calls the same `score_item` and `build_reasons` as the recommendations page, above a 0.35 threshold and capped at 50 recipients, so a notification and a recommendation can never disagree about the same opening. The shared feature-building moved into public helpers in `recommendations/service.py` rather than being duplicated.
9. **Funding is university-wide, not department-scoped.** `funding:manage` goes to coordinators and admins with no scope check, because a funding call isn't owned by a department. Seeded calls are fictional, flagged `is_demo`, and the UI says so; every call links its official source, because this prototype is not a source of truth about real money.
10. **Saved items gained a fourth target** (`funding_id`), which widened the `num_nonnulls(...) = 1` CHECK from three columns to four in migration 0012 — `op.f()` is needed on the constraint name there, or the naming convention double-prefixes it.
11. **The dashboard's upcoming deadlines now cover both kinds.** `DeadlineItem` carries `kind` + `item_id` instead of an opportunity id, so a saved funding call and an applied-to opening sit in one sorted list.

## Consequences

- A handler that raises rolls back the user's action. With more subscribers this becomes the wrong default and the bus should grow an "isolate failures" mode (or a real queue).
- Relevance matching scores candidate users one by one at publish time. That is fine for a department-sized user base and capped at 50 notifications, but it makes publishing an opening slower as the platform grows; Step 13's embeddings are the natural place to fix it.
- Reminder lead times (7 and 1 days) are constants in `app/jobs/reminders.py`; making them per-user preferences needs a settings table that doesn't exist yet.

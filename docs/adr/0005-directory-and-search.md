# ADR 0005: Step 4 researcher directory and search

- **Status:** Accepted
- **Date:** 2026-09-22
- **Context:** Step 4 adds a searchable, filterable researcher directory, opt-in student discovery and a unified search endpoint.

## Decisions

1. **The weighted tsvector is a maintained column, not a generated one.** The roadmap asked for a generated column (name A, tags B, bio C), but its inputs live in three tables (`users`, `user_skills`/`user_research_areas`, `researcher_profiles`) and a Postgres generated column can only read its own row. `researcher_profiles.search_document` is instead rebuilt by one SQL statement in `profiles/service.py` on every write that feeds it (profile save, skills, research areas). Migration `0005` backfills existing rows with the same statement. Trade-off: a code path that changes an input without calling `rebuild_search_document` would leave the document stale — covered by `test_search_document_refreshes_when_skills_change`.
2. **One query does both exact and fuzzy matching.** `search_document @@ websearch_to_tsquery(q) OR similarity(full_name, q) > 0.3`, ranked by `ts_rank` then name similarity. A misspelled name ("Seedd facluty") still finds the person through the `pg_trgm` GIN index on `users.full_name`, without a second round trip.
3. **Research-area filtering includes child areas.** Filtering by "Artificial Intelligence" finds someone tagged only "Machine Learning". Areas are at most two levels deep (ADR 0004), so one `parent_id` hop is complete.
4. **Public directory schemas never expose email.** `search_schemas.py` holds the first schemas that return *other people's* data; email is deliberately absent. The coordinator verification queue (a scoped review view) remains the only place it appears.
5. **Student privacy is enforced in the query, not the response.** `is_discoverable = true` is part of the `WHERE` clause in `list_discoverable_students`, so an opted-out student can never be returned by any filter combination.
6. **`student:discover` is FACULTY's first permission.** Granted to FACULTY and ADMIN; RESEARCH_COORDINATOR gets it through `ROLE_HIERARCHY` inheritance — the first time that mechanism does real work rather than being asserted hypothetically.
7. **Separate search rate limiter.** 60 requests/minute per IP on directory and search endpoints, a separate `app.state` instance from auth's 5/minute IP+email limiter. Search is interactive; the limit exists to stop scraping, not to slow typing.
8. **Public read-only `GET /schools` and `GET /departments`.** The directory filters need these lists and the Step 3 endpoints are admin-only. Names are not sensitive, so any signed-in user may read them; writes remain admin-only under `/admin`.
9. **`GET /search?q=&types=` returns researchers only for now.** The `types` parameter exists so later steps can add projects, publications and opportunities without changing the contract.

## Consequences

- A future write path that changes a researcher's name, skills, areas or bio must call `rebuild_search_document`. The admin `PATCH /admin/users/{id}` name change is not yet wired to it; a renamed researcher will match under the old name until they next save their profile.
- Department names are not yet shown on researcher cards (only `department_id`); the frontend resolves filter labels from `/departments` but cards don't display a department name.

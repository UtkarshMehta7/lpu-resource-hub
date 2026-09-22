# ADR 0007: Step 6 publications

- **Status:** Accepted
- **Date:** 2026-09-22
- **Context:** Step 6 adds publications with ordered author lists (platform users or external names), links to research projects, and full-text search. They feed the TF-IDF matching in later steps.

## Decisions

1. **An author slot is exactly one identity.** `publication_authors` has nullable `user_id` and `external_name` with `CHECK (num_nonnulls(user_id, external_name) = 1)`; the API schema enforces the same rule so clients get a `422` before touching the database.
2. **Author order is the list position.** Clients send an ordered list and the service numbers it `1..n`, so gaps and duplicate positions are impossible; `UNIQUE(publication_id, author_order)` backs it up. Edits replace the whole list.
3. **DOIs are normalised before storage.** Lower-cased, with `https://doi.org/`, `http://doi.org/` and `doi:` prefixes stripped, so the plain `UNIQUE` constraint catches real duplicates. A duplicate is `409`.
4. **Publications are public to signed-in users; their project links are not.** The linked-project list runs through the project `visibility_filter`, so linking a publication to a draft never leaks the draft's title, and filtering by a project you can't see returns nothing.
5. **You can only link projects you own or belong to** (`422` otherwise).
6. **Owner = creator.** Only the creator may edit; the creator or an admin may delete (hard delete — publications have no workflow state). Admin deletions are audited as `publication.deleted`. Internal co-authors see the publication on their profile via `author_id`, which matches authored *or* created publications, but cannot edit it.
7. **`publication:create` is a FACULTY grant (inherited by coordinators).** Students and admins don't author publications in this prototype.
8. **Search uses a generated `tsvector`** (title A, abstract B, venue C) with a GIN index, the same pattern as projects (ADR 0006). `/search` includes publications.
9. **Deleting a user removes their author slots** (`ON DELETE CASCADE`), because `SET NULL` would violate the one-identity check.

## Consequences

- There is no claim/merge flow yet: an external author who later joins the platform stays an external name until the creator edits the list.
- The area filter only finds publications linked to a project tagged with that area (or a child area); unlinked publications have no area.

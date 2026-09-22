# ADR 0010: Step 9 explainable recommendations (v1)

- **Status:** Accepted
- **Date:** 2026-09-22
- **Context:** Step 9 adds the platform's first real matching: recommending opportunities, projects, researchers and collaborators, with an explanation for every suggestion. Local only, no paid APIs, no chatbot.

## Decisions

1. **`app/ml` is database-free.** It operates on `ViewerFeatures`/`ItemFeatures` dataclasses; `app/modules/recommendations/service.py` builds those from SQL. This is why the offline evaluation can run the production scoring code against fixtures, and why scoring is unit-testable without a database. The roadmap's `Recommender.recommend(user, target_type, k)` therefore became `Recommender.recommend(viewer_features, items, k, ...)`, with the DB-facing `recommend(db, viewer, target, limit, weights)` one layer up.
2. **Three components, weights in settings.** `score = 0.40*skill + 0.35*area + 0.25*text` (`rec_weight_skill`, `rec_weight_area`, `rec_weight_text`). Skills weight required above optional and scale by self-reported proficiency; areas are Jaccard with half credit for a parent/child relation; text is TF-IDF cosine (scikit-learn), all local.
3. **An item asking for nothing scores 0 on that component**, rather than counting as a perfect match. No requirement is not evidence of a fit.
4. **Filters run in SQL, before scoring.** Visibility, eligibility by role and opportunity type, OPEN status, deadline, already-applied, own items and self are all `WHERE` clauses. A hidden item can never reach the ranker, so it can never be recommended *or* explained — the same guarantee the list endpoints give.
5. **Explanations are derived, never generated.** `Breakdown` records exactly what matched; `explain.py` only phrases those facts. A required skill the viewer lacks is never named as a match, and a zero-scoring item is dropped instead of being given a reason. There is no language model in this feature.
6. **Cold start is explicit.** Fewer than 3 skills, fewer than 3 research areas and no profile text means there is nothing to rank on: the API returns the newest items with `cold_start: true` and a plain-language reason, instead of pretending to match.
7. **The TF-IDF index is cached in memory and invalidated by a content fingerprint** (row count + newest `updated_at` for the relevant tables), so no code has to remember to invalidate it and a stale index can't outlive a content change. The corpus covers all items of a kind so term statistics don't shift per viewer; only ids that survived the filters are ever looked up in it.
8. **Ranking is deterministic.** Ties break on item id, so the same inputs always produce the same order — required for the evaluation to mean anything.
9. **Quality has a recorded baseline.** `fixtures/recommendation_eval.json` (hand-labelled, graded 0-3) plus `scripts/evaluate_recommendations.py` give precision@5 and nDCG@10; `docs/ai-evaluation.md` records the numbers and their limits, and a test fails if the means drop below them.
10. **scikit-learn ships no type stubs**, so mypy gets a scoped `ignore_missing_imports` override for `sklearn.*` only — not a blanket relaxation, and no `# type: ignore` comments.

## Consequences

- TF-IDF matches words, not meaning; Step 13 replaces/augments it with embeddings and pgvector.
- The in-memory cache is per process. With more than one worker each holds its own copy, which is correct but duplicated work; a shared cache would need Redis, which the zero-cost constraint rules out for now.
- The evaluation set is small and was labelled by the same author as the scoring code, so it is a regression guard rather than evidence of user-perceived quality. `docs/ai-evaluation.md` says so explicitly.

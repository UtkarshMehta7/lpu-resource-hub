# ADR 0014: Step 13 embeddings, pgvector and hybrid search

- **Status:** Accepted
- **Date:** 2026-09-23
- **Context:** Step 13 adds sentence embeddings and vector search, with an explicit instruction from the roadmap: beat the Step 9 recommender on the labelled evaluation set, or say so and keep Phase 1.

## Decisions

1. **Embeddings are an optional install.** `pip install -e ".[ml]"` adds sentence-transformers and pgvector; without it `is_available()` is False, `/search/semantic` answers lexically and reports `semantic_used: false`, and nothing else changes. The app must never require a 400MB dependency to run.
2. **The model is local and small**: all-MiniLM-L6-v2, 384 dimensions, CPU, cached on disk. No API, no per-query cost, consistent with the zero-cost constraint.
3. **Vectors live in `entity_embeddings`, keyed by (entity_type, entity_id, model_name)**, with an HNSW cosine index. `entity_id` has no foreign key on purpose: it points at five tables, and searches join back to the real table, so a stale row can never be returned.
4. **Re-embedding is content-addressed.** A `content_hash` of the built document decides whether work is needed, which is what makes "re-embed on every save" affordable; saves schedule it as a FastAPI background task, so the write path is unchanged.
5. **Lexical and semantic rankings are fused with reciprocal rank fusion**, not blended scores. A `ts_rank` and a cosine similarity are not on the same scale, and RRF needs no calibration: an item ranked well by both beats one ranked brilliantly by either.
6. **Visibility is enforced after retrieval, with the same filters the list endpoints use.** Semantic candidates are checked against `project_visibility` / `opportunity_visibility` (etc.) before being fused, so embeddings can never widen what a viewer can discover — a draft project is embedded but unreachable.
7. **The query is embedded once per request** and visibility is checked with one targeted query per type. The first version embedded the same query four times and fetched 200-row visibility pools; measured latency went from ~9s cold / noticeable warm to ~35–50ms warm.
8. **The model is warmed in a background thread at startup**, so the first user query doesn't pay the model load.
9. **`MIN_SIMILARITY` (0.15) is a tail-trim, not a relevance test.** On profile-length text this model scores a good match ~0.20–0.30 and an unrelated query ~0.15–0.23; the code and docs say so rather than implying the threshold separates relevant from irrelevant.
10. **Phase 1 remains the default recommender.** The offline comparison (docs/ai-evaluation.md) shows every semantic share from 0.05 to 0.40 is worse than or equal to Phase 1 on precision@5 (0.6667 vs 0.7167) and never better on nDCG@10. `rec_semantic_weight` therefore defaults to `0.0`. Semantic *search* stays on, because there the same embeddings answer queries that return nothing lexically.

## Consequences

- Two behaviours now differ by design: search is hybrid, recommendations are not. `recommendations/weights.py` is the single place that decides, so they can't drift apart accidentally.
- `vector` is not a trusted PostgreSQL extension, so it must be created by a superuser before migration 0013 runs (documented in docs/development.md). This will matter again on any managed host.
- Embeddings are written by background tasks, so a row saved while the ML extra is absent has no vector until `scripts/backfill_embeddings.py` runs. That is why backfill exists and is idempotent.
- The evaluation verdict is data-dependent: 3 viewers and 14 fixture items is a small set, and the conclusion should be revisited with real content. The comparison is one command (`--compare`), so revisiting it is cheap.

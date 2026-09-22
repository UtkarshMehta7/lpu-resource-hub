# Recommendation quality (Step 9, v1)

How good are the recommendations, and how would we know if a change made
them worse? This is the baseline.

## What is measured

`backend/fixtures/recommendation_eval.json` holds **hand-labelled relevance
judgements**: three viewer profiles (an ML student, an agricultural-sensors
student and a chemistry researcher) against 14 opportunity-shaped items,
each graded 0–3 (3 = clearly relevant, 0 = not relevant). The items and
profiles are fictional demo data in the same shape as the seed data.

`backend/scripts/evaluate_recommendations.py` runs the **real scoring code**
(`app/ml`) over those fixtures — no database, no network — and reports:

- **precision@5** — of the top 5, how many are actually relevant (grade ≥ 2).
- **nDCG@10** — how close the top 10 ordering is to the ideal ordering,
  with graded relevance.

```bash
cd backend && python -m scripts.evaluate_recommendations       # table
cd backend && python -m scripts.evaluate_recommendations --json
```

## Baseline results

Weights: skill 0.40, area 0.35, text 0.25 (the defaults in `Settings`).

| Viewer | precision@5 | nDCG@10 |
|---|---:|---:|
| ml-student | 0.60 | 0.9880 |
| agri-sensors-student | 0.80 | 0.9979 |
| chemistry-researcher | 0.75 | 1.0000 |
| **mean** | **0.7167** | **0.9953** |

`tests/test_recommendation_scoring.py` asserts the means stay at or above
0.70 / 0.95, so a scoring or weight change that degrades quality fails the
test suite rather than shipping quietly.

### Reading the numbers honestly

- **nDCG@10 is near-perfect because the ranking is near-ideal on this set**,
  not because the task is solved. With 14 items and clear topical
  separation, getting the order right is easy. It is a regression guard, not
  evidence of production quality.
- **precision@5 is capped below 1.0 for these viewers.** Two of the three
  have only 3–4 items graded ≥ 2, so the best possible precision@5 is 0.60
  and 0.80 respectively. ml-student at 0.60 is therefore already at its
  ceiling; chemistry-researcher's 0.75 comes from a 4-item pool.
- **The fixture set is small and was labelled by the author of the scoring
  code.** It cannot show whether real users would agree. Treat it as a
  change-detector, not a user study.

## Step 13: does semantic matching beat it?

Step 13 added sentence embeddings (all-MiniLM-L6-v2, 384 dimensions, local
CPU) stored in pgvector. The roadmap set a clear bar: the hybrid recommender
must beat Phase 1 on precision@5 / nDCG@10, and if it doesn't, say so and
keep Phase 1 as the default.

**It doesn't. Phase 1 stays the default.**

```bash
cd backend && python -m scripts.evaluate_recommendations --compare
```

| Semantic share of the score | precision@5 | nDCG@10 |
|---|---:|---:|
| **0.00 (Phase 1, default)** | **0.7167** | **0.9953** |
| 0.05 | 0.6667 | 0.9953 |
| 0.10 | 0.6667 | 0.9953 |
| 0.15 | 0.6667 | 0.9953 |
| 0.20 | 0.6667 | 0.9953 |
| 0.25 | 0.6667 | 0.9817 |
| 0.40 | 0.6667 | 0.9822 |

Every mix tried is worse than or equal to Phase 1, so `rec_semantic_weight`
defaults to `0.0`: recommendations keep the Step 9 scoring. The knob stays in
`Settings` so this can be re-tested as the corpus grows.

### Why it loses here

- **The fixtures are short and tag-rich.** Each item is two lines of text plus
  explicit required/optional skills and research areas. Structured overlap is
  a strong signal on that data; embeddings add noise the tags already cover.
- **The set is tiny** (3 viewers, 14 items). One item swapping places moves
  precision@5 by a sixth, which is what the 0.7167 → 0.6667 drop is: a single
  marginal item displacing a relevant one for one viewer.
- **Absolute similarities are low and poorly separated** on profile-length
  text: a good match scores ~0.20–0.30 cosine, and an unrelated query still
  scores ~0.15–0.23. That is why `MIN_SIMILARITY` (0.15) is described in code
  as a tail-trim, not a relevance test.

### Where semantic *does* win: search

Ranking a labelled candidate set is not the same task as answering a
question. On the demo database, natural-language queries that share no words
with the text return **nothing** lexically and sensible results semantically:

| Query | Lexical hits | Semantic hits |
|---|---:|---:|
| "researchers working on soil moisture sensing in farms" | 0 researchers | 3 researchers |
| "equipment for measuring how wet farmland is" | 0 projects | finds the soil-sensor project |
| "machine learning for images" | 0 researchers | 3 researchers |

So `/api/v1/search/semantic` keeps the hybrid on by default (lexical and
vector rankings fused with reciprocal rank fusion), while
`/api/v1/recommendations` keeps Phase 1 scoring. Two different jobs, two
different verdicts, both recorded here rather than assumed.

### Cost

Measured locally: the model loads in ~3–8s (warmed in a background thread at
startup, so it's off the request path), after which a semantic search is
~35–50ms end to end. Embedding one entity is a few milliseconds and is
skipped entirely when its content hash hasn't changed.

## What the scores are made of

```
score = 0.40 * skill_score + 0.35 * area_score + 0.25 * text_score
```

- **skill_score** — the weighted share of an item's skills the viewer has.
  Required skills count double the optional ones, and self-reported
  proficiency scales the contribution (level 1 → 0.5, level 5 → 1.0). An
  item that asks for no skills scores 0, not 1: absence of a requirement is
  not evidence of a match.
- **area_score** — Jaccard overlap of research areas, with half credit where
  one area is the parent or child of one of the viewer's (the taxonomy is
  two levels deep).
- **text_score** — TF-IDF cosine similarity between the viewer's own words
  (profile bio/interests plus their publication titles and abstracts) and
  the item's text (title, description, objectives, eligibility).

## Explanations

Every reason shown to a user is generated from the score breakdown that
produced the score — `app/ml/explain.py` can only phrase what
`app/ml/scoring.py` actually counted:

```
Matches 2 of 2 required skills: arduino, sensors
Shared research areas: Soil Science
Related terms: moisture, calibration
```

There is no language model anywhere in this feature and nothing is
paraphrased or invented. A skill the viewer lacks is never mentioned as a
match, and an item that scores zero is dropped rather than explained.

## Known limitations

- **Cold start:** a viewer with fewer than 3 skills, fewer than 3 research
  areas and no profile text gets the newest items, clearly labelled as such
  in the API (`cold_start: true`) and in the UI.
- **Recommendations are lexical + structured only.** TF-IDF matches words,
  not meaning. Embeddings exist and power search, but they are switched off
  in the recommendation score because the evaluation above says they make it
  worse on this data.
- **No feedback loop:** nothing learns from what people click or apply to.
- **Popularity is ignored**, so a brand-new item competes on content alone.
- **Term statistics are global:** the TF-IDF index is built over all items of
  a kind and cached in memory, keyed by a content fingerprint (row count +
  newest `updated_at`). Only the ids that survived the business filters are
  ever scored, so a hidden item can influence term weights but can never be
  recommended or named.

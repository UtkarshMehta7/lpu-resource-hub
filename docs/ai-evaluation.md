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
- **Lexical only:** TF-IDF matches words, not meaning. "CNN" and
  "convolutional network" are unrelated to it. Step 13 adds embeddings.
- **No feedback loop:** nothing learns from what people click or apply to.
- **Popularity is ignored**, so a brand-new item competes on content alone.
- **Term statistics are global:** the TF-IDF index is built over all items of
  a kind and cached in memory, keyed by a content fingerprint (row count +
  newest `updated_at`). Only the ids that survived the business filters are
  ever scored, so a hidden item can influence term weights but can never be
  recommended or named.

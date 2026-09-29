# Publication de-duplication: the rules, and where they fail

This is the written note the project brief asks for. It describes how the
profile importer decides that two records are the same publication, and —
more usefully — the cases where that decision is wrong.

## Why this needs rules at all

A profile import reads the same researcher from up to four sites. They
disagree constantly:

- ORCID has `Deep Learning for Graphs`; Crossref has
  `Deep learning for graphs: a survey`.
- OpenAlex returns a resolver URL for the DOI, sometimes percent-encoded;
  everyone else returns the bare identifier.
- Semantic Scholar has the abstract; ORCID never does.

Without a merge step the researcher gets the same paper three times. With a
careless merge step they lose papers that only looked alike.

## The rules, in order

### 1. A shared DOI is decisive

Two records with the same DOI are the same work. No scoring, no threshold.
DOIs are compared after normalisation (`normalise_doi`): the resolver prefix
is stripped, percent-encoding is decoded, case is folded, and anything that
is not `10.<4+ digits>/<suffix>` is discarded rather than stored.

### 2. Two different DOIs are never merged

However similar the titles. An erratum, a preprint and its version of record,
and a reprint all share a title and are genuinely separate records. This rule
is the reason `Erratum: Deep learning for graphs` stays out of the group.

### 2b. A replaced word means a different study

Token-set ratio is deliberately forgiving about omissions — it scores
"Forecasting wheat yield" against "Forecasting wheat yield from open satellite
data" at 100, which is right: one source dropped the subtitle.

But it scores "Forecasting **wheat** yield…" against "Forecasting **maize**
yield…" above the merge threshold too, and those are different studies.

The distinction is whether *each* side has a word the other lacks. A subset is
an omission; a two-way difference is a substitution. Spelling variants are
exempted by comparing the differing words to each other — "schrodinger s"
against "schrodingers" is one word written two ways, scoring 96, while "wheat"
against "maize" scores 20. The threshold is 80.

### 2c. With no DOI, a different year is a different work

Two records with no DOI, matching titles and different publication years are
treated as separate. Without this, a study repeated the following year folds
into its predecessor and one of them disappears from the register.

### 3. Without a DOI, compare normalised titles

`normalise_title` folds accents, strips punctuation, collapses whitespace and
lower-cases. The comparison is rapidfuzz's **token-set ratio**, which ignores
word order and tolerates one source carrying a subtitle the other dropped.

- **≥ 92** — treated as the same work.
- **84 – 92** — shown as a *possible duplicate*, unticked, for the researcher
  to decide.
- **< 84** — treated as distinct.

The thresholds are deliberately high. A false merge loses a real publication
silently; a false split produces a duplicate the researcher can see and
untick. The cheaper mistake is the visible one.

### 4. Against the existing register

The same two rules run against what is already stored: exact DOI first, then a
`pg_trgm` shortlist (index-backed, `ix_publications_title_trgm`) scored with
the same ratio. Candidates are capped at five per title.

## Field precedence once records are grouped

| Field | Believed source, best first |
|---|---|
| title, venue, year, type, authors | Crossref → OpenAlex → Semantic Scholar → ORCID |
| abstract | Semantic Scholar → Crossref → OpenAlex → ORCID |
| designation, bio, links | ORCID → OpenAlex → Semantic Scholar |

Crossref wins the bibliographic fields because it returns what the publisher
registered. ORCID wins the personal fields because the researcher curates
that record themselves.

## Measured accuracy

Measured by `tests/test_deduplication_accuracy.py` against the labelled
fixture in `tests/fixtures/deduplication.py`. Run it with `-s` to print the
table below.

### What "accuracy" means here

A **pair** of records either is or is not the same publication; the fixture
labels every pair through its clusters. The algorithm groups records, and
every pair inside a group is a predicted duplicate.

```
precision = TP / (TP + FP)    of the merges made, how many were right
recall    = TP / (TP + FN)    of the merges needed, how many were made
F1        = harmonic mean     <- the figure reported as "accuracy"
```

Plain pairwise accuracy — `(TP + TN) / all pairs` — is **not** the headline.
With 32 records there are 496 pairs of which only 11 are duplicates, so an
algorithm that merged nothing at all would score 97.8%. It is reported
alongside so that inflation is visible rather than hidden.

The two errors do not cost the same. A false positive silently folds a real
publication into another and it is gone; a false negative leaves a visible
duplicate somebody can remove. Precision is therefore guarded by its own
assertion, separate from the F1 target.

### Fixture composition

32 records in 22 clusters — 9 genuine duplicate groups and 13 singletons,
giving 11 true duplicate pairs and 485 distinct ones.

Roughly a third of the fixture is **near misses** designed to be merged by a
careless rule: an erratum sharing a title with its original, a preprint and
its version of record, a sequel paper differing only by "II", two crops in
otherwise identical phrasing, and generic titles ("Editorial",
"Introduction") repeated across years. A fixture of only obvious duplicates
would score well and prove nothing.

It also covers exact duplicates across sources, DOIs in bare/URL/percent-
encoded form, differing capitalisation, em dashes and hyphens, accented
characters, dropped subtitles, initialised author names, missing authors and
venues, unusable DOIs, and whitespace noise.

### Measured result

| Measure | Value |
|---|---|
| Fixture size | 32 records |
| Ground-truth pairs | 11 duplicate, 485 distinct |
| True positives | 11 |
| False positives | **0** |
| False negatives | **0** |
| Precision | **100.0%** |
| Recall | **100.0%** |
| **F1 (reported accuracy)** | **100.0%** |
| Pairwise accuracy | 100.0% (inflated; not the headline) |
| Acceptance target | ≥95% |
| **Status** | **PASS** |

### An honest caveat about that number

The first run of this measurement scored **F1 66.7%** (precision 61.5%, recall
72.7%). Three of the rules above — case-insensitive DOI comparison, the
substitution test, and the year discriminator — were added *in response* to
the failures it exposed.

That is the measurement doing its job, but it means the fixture and the
algorithm are no longer independent. 100% is the score on **this** fixture,
not a claim about all publication data. The rules added are general
(a DOI genuinely is case-insensitive; a substituted word genuinely indicates a
different study), not special cases keyed to fixture rows — but a new fixture
drawn from different sources should be expected to find new failures.

The number to trust is the *method*: a labelled corpus, a pairwise F1, and
precision guarded separately.

## Known failure cases

These are real, unfixed, and accepted:

1. **Translated titles.** The same paper published in two languages has two
   unrelated titles. With DOIs they stay separate (correct). Without, they
   stay separate too (also correct) — but a translation *of the same DOI*
   will merge and keep whichever title precedence picks.
2. **Very short titles.** `Introduction`, `Editorial`, `Preface` score 100
   against each other. Where they carry DOIs rule 2 protects them; where they
   do not, distinct editorials in different years can merge. Mitigated only
   by the year being part of what the researcher sees before importing.
3. **Preprint and version of record.** Usually different DOIs, so they are
   imported as two entries. That is arguably correct and arguably noise; the
   importer does not try to decide.
4. **Series titles.** `OpenAlex Snapshot` is published repeatedly with a new
   DOI each time. Rule 2 keeps them separate, which is right, but a
   researcher's list can look repetitive.
5. **Author disambiguation is not attempted.** Co-author names are stored as
   plain text, not matched to accounts. Guessing wrong would attribute a
   colleague's work to the wrong person, so the importer links only the
   importing researcher by id and leaves the rest for a human.
6. **Name-only lookup is a guess.** Without an ORCID iD, OpenAlex is matched
   on name and affiliation. Namesakes are common; the interface labels these
   results as unconfirmed and the researcher is expected to check.
7. **One ORCID, several OpenAlex authors.** ORCID's public demo iD resolves
   to dozens of real author records because people pasted the example into
   their submissions. The connector refuses to guess and reports the
   ambiguity rather than importing a stranger's publication list.

## What the importer never does

- It never writes without the researcher ticking the item first.
- It never overwrites a profile field that was not ticked.
- It never edits or deletes an existing publication — a match is *reported*,
  not merged into.
- It never accepts bibliographic data from the browser: applying an import
  re-reads the sources, so the payload cannot be forged.

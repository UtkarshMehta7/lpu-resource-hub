"""Measuring de-duplication against a labelled fixture.

The specification asks for ">=95% deduplication accuracy on the fixture set".
"Accuracy" needs a definition before it means anything, so:

* A **pair** of records is either the same publication or not. The fixture
  labels every pair through its clusters.
* The algorithm groups records; every pair inside a group is a **predicted**
  duplicate.
* precision = TP / (TP + FP)  -- of the merges made, how many were right
* recall    = TP / (TP + FN)  -- of the merges needed, how many were made
* F1        = harmonic mean, and the figure reported as the accuracy

Plain pairwise accuracy -- (TP + TN) / all pairs -- is deliberately *not* the
headline. With 32 records there are 496 pairs of which only 11 are duplicates,
so an algorithm that merged nothing at all would score 97.8%. It is reported
alongside so the inflation is visible rather than hidden.

The cost of the two errors is not symmetric. A false positive silently
destroys a publication by folding it into another; a false negative leaves a
duplicate a human can see and remove. Precision therefore matters more than
recall, and the thresholds are set accordingly.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.imports.merge import group_works
from tests.fixtures.deduplication import FIXTURE, ground_truth_pairs

#: The specification's bar.
TARGET = 0.95


@dataclass(frozen=True, slots=True)
class Measurement:
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int
    missed: list[tuple[str, str]]
    wrong: list[tuple[str, str]]

    @property
    def precision(self) -> float:
        predicted = self.true_positives + self.false_positives
        return self.true_positives / predicted if predicted else 1.0

    @property
    def recall(self) -> float:
        actual = self.true_positives + self.false_negatives
        return self.true_positives / actual if actual else 1.0

    @property
    def f1(self) -> float:
        total = self.precision + self.recall
        return 2 * self.precision * self.recall / total if total else 0.0

    @property
    def pairwise_accuracy(self) -> float:
        total = (
            self.true_positives + self.false_positives + self.false_negatives + self.true_negatives
        )
        return (self.true_positives + self.true_negatives) / total if total else 1.0


def measure() -> Measurement:
    """Run the real algorithm over the fixture and score its grouping."""
    works = [item.work for item in FIXTURE]
    groups = group_works(works)

    predicted: set[frozenset[int]] = set()
    for group in groups:
        for position, left in enumerate(group):
            for right in group[position + 1 :]:
                predicted.add(frozenset({left, right}))

    truth = ground_truth_pairs()
    all_pairs = {frozenset({i, j}) for i in range(len(FIXTURE)) for j in range(i + 1, len(FIXTURE))}

    tp = predicted & truth
    fp = predicted - truth
    fn = truth - predicted
    tn = all_pairs - predicted - truth

    def describe(pairs: set[frozenset[int]]) -> list[tuple[str, str]]:
        return sorted((FIXTURE[min(p)].case, FIXTURE[max(p)].case) for p in pairs)

    return Measurement(
        true_positives=len(tp),
        false_positives=len(fp),
        false_negatives=len(fn),
        true_negatives=len(tn),
        missed=describe(fn),
        wrong=describe(fp),
    )


def test_deduplication_meets_the_specified_accuracy() -> None:
    """The headline measurement. Printed so the number is in the test log."""
    result = measure()

    report = "\n".join(
        [
            "",
            "DEDUPLICATION",
            f"  Fixture size:              {len(FIXTURE)} records",
            f"  Ground-truth pairs:        {len(ground_truth_pairs())} duplicate, "
            f"{len(FIXTURE) * (len(FIXTURE) - 1) // 2 - len(ground_truth_pairs())} distinct",
            f"  True positives:            {result.true_positives}",
            f"  False positives:           {result.false_positives}",
            f"  False negatives:           {result.false_negatives}",
            f"  Precision:                 {result.precision * 100:.1f}%",
            f"  Recall:                    {result.recall * 100:.1f}%",
            f"  F1 (reported accuracy):    {result.f1 * 100:.1f}%",
            f"  Pairwise accuracy:         {result.pairwise_accuracy * 100:.1f}%  "
            "(inflated by true negatives; not the headline)",
            f"  Acceptance target:         {TARGET * 100:.0f}%",
            f"  Status:                    {'PASS' if result.f1 >= TARGET else 'FAIL'}",
            "",
        ]
    )
    if result.missed:
        report += f"  Missed duplicates: {result.missed}\n"
    if result.wrong:
        report += f"  Wrongly merged:    {result.wrong}\n"
    print(report)

    assert result.f1 >= TARGET, report


def test_no_distinct_publication_is_ever_merged_away() -> None:
    """Precision is the one that must not slip.

    A false positive folds a real publication into another and it is gone from
    the register with nothing to notice. A false negative leaves a visible
    duplicate somebody can remove. The two are not equally bad.
    """
    result = measure()
    assert result.false_positives == 0, f"wrongly merged: {result.wrong}"


def test_the_fixture_is_adversarial_enough_to_mean_something() -> None:
    """Guards the measurement itself.

    A fixture of only obvious duplicates would score well and prove nothing.
    Roughly a third of these records are near misses designed to be merged by
    a careless rule.
    """
    clusters = {item.cluster for item in FIXTURE}
    multi = sum(1 for c in clusters if sum(1 for i in FIXTURE if i.cluster == c) > 1)
    assert len(FIXTURE) >= 30
    assert multi >= 8, "not enough genuine duplicate groups to measure recall"
    assert len(clusters) >= 20, "not enough distinct works to measure precision"

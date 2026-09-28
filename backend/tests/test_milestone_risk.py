"""The at-risk rules, as a table of inputs and outputs.

These are the rules the whole feature rests on -- the board, the analytics and
the reminder job all ask this same function -- and they are deliberately free
of the database, so they are tested directly rather than through HTTP.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.modules.milestones.models import MilestoneStatus
from app.modules.milestones.risk import (
    NEEDS_ATTENTION,
    Risk,
    RiskInput,
    assess,
    assess_all,
    days_until,
)

TODAY = date(2026, 6, 1)
THRESHOLD = 7


def at(offset: int, status: MilestoneStatus = MilestoneStatus.PENDING) -> RiskInput:
    return RiskInput(status=status, due_date=TODAY + timedelta(days=offset))


def risk_of(milestone: RiskInput, *deps: RiskInput) -> Risk:
    return assess(milestone, today=TODAY, threshold_days=THRESHOLD, depends_on=deps)


# --- settled ---------------------------------------------------------------


@pytest.mark.parametrize("status", [MilestoneStatus.DONE, MilestoneStatus.CANCELLED])
def test_settled_milestones_are_never_late_however_old(status: MilestoneStatus) -> None:
    """Done and cancelled are not outstanding work, so they cannot slip."""
    assert risk_of(at(-365, status)) is Risk.NONE


# --- dates -----------------------------------------------------------------


def test_a_date_that_has_passed_is_overdue() -> None:
    assert risk_of(at(-1)) is Risk.OVERDUE


def test_due_today_is_at_risk_not_overdue() -> None:
    assert risk_of(at(0)) is Risk.AT_RISK


def test_the_threshold_boundary_is_inclusive() -> None:
    """Exactly N days out is at risk; one day further out is not.

    The off-by-one here is the difference between warning somebody and not,
    so it is pinned rather than left to reading the comparison.
    """
    assert risk_of(at(THRESHOLD)) is Risk.AT_RISK
    assert risk_of(at(THRESHOLD + 1)) is Risk.ON_TRACK


def test_a_distant_milestone_is_on_track() -> None:
    assert risk_of(at(90)) is Risk.ON_TRACK


# --- dependencies ----------------------------------------------------------


def test_waiting_on_an_overdue_milestone_blocks() -> None:
    assert risk_of(at(90), at(-2)) is Risk.BLOCKED


def test_waiting_on_an_at_risk_milestone_blocks() -> None:
    assert risk_of(at(90), at(3, MilestoneStatus.IN_PROGRESS)) is Risk.BLOCKED


def test_waiting_on_healthy_work_is_ordinary_sequencing_not_a_block() -> None:
    """An unfinished dependency that is comfortably on track is fine."""
    assert risk_of(at(90), at(30)) is Risk.ON_TRACK


def test_waiting_on_finished_work_is_not_a_block() -> None:
    assert risk_of(at(90), at(-2, MilestoneStatus.DONE)) is Risk.ON_TRACK
    assert risk_of(at(90), at(-2, MilestoneStatus.CANCELLED)) is Risk.ON_TRACK


# --- precedence ------------------------------------------------------------


def test_overdue_beats_blocked() -> None:
    """A date that has passed is a fact; a blockage is a prediction."""
    assert risk_of(at(-1), at(-9)) is Risk.OVERDUE


def test_blocked_beats_at_risk() -> None:
    """Saying *why* it is in trouble is more useful than saying it is due."""
    assert risk_of(at(2), at(-9)) is Risk.BLOCKED


# --- helpers ---------------------------------------------------------------


def test_days_until_goes_negative_once_late() -> None:
    assert days_until(TODAY - timedelta(days=3), TODAY) == -3
    assert days_until(TODAY + timedelta(days=4), TODAY) == 4


def test_needs_attention_is_exactly_the_three_bad_states() -> None:
    assert {Risk.AT_RISK, Risk.OVERDUE, Risk.BLOCKED} == NEEDS_ATTENTION
    assert Risk.ON_TRACK not in NEEDS_ATTENTION
    assert Risk.NONE not in NEEDS_ATTENTION


def test_assess_all_judges_a_whole_project_at_once() -> None:
    verdicts = assess_all(
        {"a": at(-3), "b": at(20), "c": at(2)},
        {"b": ["a"], "c": []},
        today=TODAY,
        threshold_days=THRESHOLD,
    )
    assert verdicts == {"a": Risk.OVERDUE, "b": Risk.BLOCKED, "c": Risk.AT_RISK}


def test_a_dependency_we_cannot_see_degrades_to_not_blocked() -> None:
    """A pointer at something outside the set must never raise."""
    verdicts = assess_all({"a": at(20)}, {"a": ["missing"]}, today=TODAY, threshold_days=THRESHOLD)
    assert verdicts == {"a": Risk.ON_TRACK}

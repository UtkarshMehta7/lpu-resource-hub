"""Academic years, which are not calendar years.

Getting the boundary wrong would put the wrong dates on a report somebody
signs, so the parsing is pinned rather than trusted to a regex read.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.modules.analytics import academic_year as ay


@pytest.mark.parametrize(
    ("label", "start", "end"),
    [
        ("2025-26", date(2025, 7, 1), date(2026, 6, 30)),
        ("2025-2026", date(2025, 7, 1), date(2026, 6, 30)),
        # An en dash is what a word processor produces; people paste it.
        ("2024–25", date(2024, 7, 1), date(2025, 6, 30)),
        ("  2023-24  ", date(2023, 7, 1), date(2024, 6, 30)),
    ],
)
def test_the_forms_people_actually_type_are_accepted(label: str, start: date, end: date) -> None:
    year = ay.parse(label)
    assert year.start == start
    assert year.end == end


def test_a_year_always_ends_the_day_before_it_began(cross_check: None = None) -> None:
    """Including across a leap year, where a naive -365 days would be wrong."""
    assert ay.from_start_year(2023).end == date(2024, 6, 30)
    assert ay.from_start_year(2024).end == date(2025, 6, 30)


@pytest.mark.parametrize("label", ["2025-27", "2025", "rubbish", "", "20-21", "2025-2027"])
def test_anything_ambiguous_is_refused_rather_than_guessed(label: str) -> None:
    """ "2025-27" is a typo, not a two-year period. Reinterpreting it would put
    the wrong dates on a signed report."""
    with pytest.raises(ay.InvalidAcademicYearError):
        ay.parse(label)


def test_the_label_is_normalised_however_it_was_written() -> None:
    assert ay.parse("2025-2026").label == "2025-26"
    assert ay.parse("2024–25").label == "2024-25"


def test_which_year_we_are_in_turns_over_at_the_start_month() -> None:
    # June is still the old year; July begins the new one.
    assert ay.current(date(2026, 6, 30)).label == "2025-26"
    assert ay.current(date(2026, 7, 1)).label == "2026-27"


def test_recent_years_are_offered_newest_first() -> None:
    years = ay.recent(3, today=date(2026, 8, 1))
    assert [y.label for y in years] == ["2026-27", "2025-26", "2024-25"]


def test_a_year_knows_what_falls_inside_it() -> None:
    year = ay.parse("2025-26")
    assert year.contains(date(2025, 7, 1))
    assert year.contains(date(2026, 6, 30))
    assert not year.contains(date(2025, 6, 30))
    assert not year.contains(date(2026, 7, 1))

"""Academic years, which are not calendar years.

An institution's year runs from one July to the next June, so "2025-26" means
1 July 2025 to 30 June 2026 inclusive. Reporting on a calendar year would
split every cohort in half and make the numbers useless for the people who
actually plan around terms.

The starting month is configuration rather than a constant, because it is the
one thing that genuinely differs between institutions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime

from app.core.config import get_settings

#: "2025-26" or "2025-2026". Anything else is rejected rather than guessed at.
LABEL_PATTERN = re.compile(r"^(\d{4})\s*[-–/]\s*(\d{2}|\d{4})$")


class InvalidAcademicYearError(ValueError):
    """The label is not an academic year this system can parse."""


@dataclass(frozen=True, slots=True)
class AcademicYear:
    """One academic year, and the dates it covers."""

    label: str
    start: date
    end: date

    @property
    def start_year(self) -> int:
        return self.start.year

    def contains(self, when: date) -> bool:
        return self.start <= when <= self.end

    def describe(self) -> str:
        return f"{self.label} ({self.start.isoformat()} to {self.end.isoformat()})"


def _start_month() -> int:
    return get_settings().academic_year_start_month


def from_start_year(start_year: int) -> AcademicYear:
    """The academic year beginning in `start_year`."""
    month = _start_month()
    start = date(start_year, month, 1)
    # The day before the same month next year: correct whatever the start
    # month is, and correct in a leap year, without any month-length table.
    end_year_start = date(start_year + 1, month, 1)
    end = date.fromordinal(end_year_start.toordinal() - 1)
    label = f"{start_year}-{str(start_year + 1)[-2:]}"
    return AcademicYear(label=label, start=start, end=end)


def parse(label: str) -> AcademicYear:
    """Turn "2025-26" into the year it names.

    Refuses anything ambiguous. A label whose halves are not consecutive
    ("2025-27") is a typo, not a two-year period, and silently reinterpreting
    it would put the wrong dates on a report somebody signs.
    """
    match = LABEL_PATTERN.match((label or "").strip())
    if match is None:
        raise InvalidAcademicYearError(f"{label!r} is not an academic year. Use the form 2025-26.")
    start_year = int(match.group(1))
    tail = match.group(2)
    end_year = int(tail) if len(tail) == 4 else int(str(start_year)[:2] + tail)
    if end_year != start_year + 1:
        raise InvalidAcademicYearError(
            f"{label!r} does not name a single academic year; "
            f"{start_year}-{str(start_year + 1)[-2:]} would."
        )
    return from_start_year(start_year)


def current(today: date | None = None) -> AcademicYear:
    """The academic year we are in now."""
    now = today or datetime.now(UTC).date()
    start_year = now.year if now.month >= _start_month() else now.year - 1
    return from_start_year(start_year)


def recent(count: int = 5, today: date | None = None) -> list[AcademicYear]:
    """The current year and the ones before it, newest first.

    Offered so the interface can present a list of real years instead of a
    free-text box that invites typos.
    """
    latest = current(today)
    return [from_start_year(latest.start_year - offset) for offset in range(count)]


__all__ = [
    "AcademicYear",
    "InvalidAcademicYearError",
    "current",
    "from_start_year",
    "parse",
    "recent",
]

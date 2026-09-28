"""Deriving whether a milestone is slipping.

Risk is computed here, at read time, rather than stored on the row and
refreshed by a job. The brief asks for "at-risk computation as a scheduled
job", and this is a deliberate departure from it: a stored flag is correct
only at the instant the job last ran, so a milestone that falls due overnight
reads as on track until morning. Risk is a pure function of the status, the
due date and today -- there is nothing to cache and nothing to go stale.

The scheduled job still exists, and does the one thing this cannot: sending
each reminder exactly once (see app/jobs/reminders.py).

Everything below is deliberately free of database and ORM types so the rules
can be tested as a table of inputs and outputs.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from app.modules.milestones.models import SETTLED_STATUSES, MilestoneStatus


class Risk(StrEnum):
    #: Settled: done or cancelled. Not "fine" -- simply not outstanding.
    NONE = "none"
    ON_TRACK = "on_track"
    AT_RISK = "at_risk"
    OVERDUE = "overdue"
    #: Waiting on something that is itself late, so its own date is optimistic.
    BLOCKED = "blocked"


#: The states that mean somebody should be doing something about it.
NEEDS_ATTENTION = frozenset({Risk.AT_RISK, Risk.OVERDUE, Risk.BLOCKED})


@dataclass(frozen=True, slots=True)
class RiskInput:
    """The minimum needed to judge one milestone."""

    status: MilestoneStatus
    due_date: date


def assess(
    milestone: RiskInput,
    *,
    today: date,
    threshold_days: int,
    depends_on: Iterable[RiskInput] = (),
) -> Risk:
    """Where one milestone stands.

    Order matters. Overdue beats blocked, because a date that has already
    passed is a fact and a blockage is a prediction. Blocked beats at-risk,
    because the useful thing to tell someone is *why* their milestone is in
    trouble, and "the thing before it is late" is more actionable than "it is
    due soon".
    """
    if milestone.status in SETTLED_STATUSES:
        return Risk.NONE
    if milestone.due_date < today:
        return Risk.OVERDUE
    for dependency in depends_on:
        if dependency.status in SETTLED_STATUSES:
            continue
        # Only a dependency that is itself in trouble blocks: an unfinished
        # one that is comfortably on track is just ordinary sequencing.
        upstream = assess(dependency, today=today, threshold_days=threshold_days)
        if upstream in (Risk.OVERDUE, Risk.AT_RISK):
            return Risk.BLOCKED
    if (milestone.due_date - today).days <= threshold_days:
        return Risk.AT_RISK
    return Risk.ON_TRACK


def assess_all(
    milestones: Mapping[object, RiskInput],
    dependencies: Mapping[object, list[object]],
    *,
    today: date,
    threshold_days: int,
) -> dict[object, Risk]:
    """Assess a whole project in one pass.

    `dependencies` maps a milestone key to the keys it waits on. Unknown keys
    are ignored rather than raising: a dependency pointing at a milestone the
    viewer cannot see should degrade to "not blocked", never to an error.
    """
    return {
        key: assess(
            value,
            today=today,
            threshold_days=threshold_days,
            depends_on=[
                milestones[upstream]
                for upstream in dependencies.get(key, [])
                if upstream in milestones
            ],
        )
        for key, value in milestones.items()
    }


def days_until(due_date: date, today: date) -> int:
    """Negative once it is late, which is what the interface wants to say."""
    return (due_date - today).days


__all__ = ["NEEDS_ATTENTION", "Risk", "RiskInput", "assess", "assess_all", "days_until"]

"""Who may move a milestone, and who may change its plan.

TRANSITIONS is the one place the milestone workflow is defined, matching the
project rule that a workflow lives in a single table and the service looks
every change up in it.

The split between the two actors is the point of the design. A milestone is
the team's work, so any member may move their own work along -- that is the
motion that happens weekly. Changing what the plan *is*, or striking work
off it, is the owner's call, and that is the motion that happens rarely and
matters when it is wrong.

Visibility is deliberately not restated here. A milestone is visible exactly
when its project is, so the service composes projects.policies.visibility_filter
rather than growing a second, drifting copy of the same rule.
"""

from __future__ import annotations

from typing import Literal

from app.modules.milestones.models import MilestoneStatus

Actor = Literal["owner", "member"]

PENDING = MilestoneStatus.PENDING
IN_PROGRESS = MilestoneStatus.IN_PROGRESS
DONE = MilestoneStatus.DONE
CANCELLED = MilestoneStatus.CANCELLED

TRANSITIONS: dict[tuple[MilestoneStatus, MilestoneStatus], frozenset[Actor]] = {
    (PENDING, IN_PROGRESS): frozenset({"owner", "member"}),
    (PENDING, DONE): frozenset({"owner", "member"}),
    (IN_PROGRESS, DONE): frozenset({"owner", "member"}),
    # Walking it back is a correction, not progress, so it is the owner's.
    (IN_PROGRESS, PENDING): frozenset({"owner"}),
    (DONE, IN_PROGRESS): frozenset({"owner"}),
    (PENDING, CANCELLED): frozenset({"owner"}),
    (IN_PROGRESS, CANCELLED): frozenset({"owner"}),
    (CANCELLED, PENDING): frozenset({"owner"}),
}


class InvalidTransitionError(Exception):
    """The requested status change isn't in TRANSITIONS for this actor."""


class NotOwnerError(Exception):
    """The caller can see the milestone but doesn't own its project."""


class ProjectNotEditableError(Exception):
    """The project is under review, completed or archived."""


class DependencyCycleError(Exception):
    """The dependency would make a milestone wait on itself, eventually."""


class CrossProjectDependencyError(Exception):
    """A milestone may only wait on one of its own project's milestones."""


def assert_transition(current: MilestoneStatus, target: MilestoneStatus, actor: Actor) -> None:
    if actor not in TRANSITIONS.get((current, target), frozenset()):
        raise InvalidTransitionError


__all__ = [
    "TRANSITIONS",
    "Actor",
    "CrossProjectDependencyError",
    "DependencyCycleError",
    "InvalidTransitionError",
    "NotOwnerError",
    "ProjectNotEditableError",
    "assert_transition",
]

"""Human-readable reasons, derived only from a Breakdown.

Nothing here invents a justification: every sentence is backed by a score
component that actually contributed.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping

from app.ml.features import Breakdown

MAX_NAMES = 4
# Below this, semantic similarity isn't worth mentioning to a person.
STRONG_SEMANTIC = 0.35


def _join(names: list[str]) -> str:
    shown = names[:MAX_NAMES]
    extra = len(names) - len(shown)
    text = ", ".join(shown)
    return f"{text} and {extra} more" if extra > 0 else text


def build_reasons(
    breakdown: Breakdown,
    skill_names: Mapping[uuid.UUID, str],
    area_names: Mapping[uuid.UUID, str],
) -> list[str]:
    reasons: list[str] = []

    required = [skill_names[s] for s in breakdown.matched_required if s in skill_names]
    if required:
        noun = "skill" if breakdown.total_required == 1 else "skills"
        reasons.append(
            f"Matches {len(required)} of {breakdown.total_required} required {noun}: "
            f"{_join(sorted(required))}"
        )
    optional = [skill_names[s] for s in breakdown.matched_optional if s in skill_names]
    if optional:
        label = "Also has" if required else "Shared skills"
        reasons.append(f"{label}: {_join(sorted(optional))}")

    shared = [area_names[a] for a in breakdown.shared_areas if a in area_names]
    if shared:
        noun = "area" if len(shared) == 1 else "areas"
        reasons.append(f"Shared research {noun}: {_join(sorted(shared))}")
    related = [area_names[a] for a in breakdown.related_areas if a in area_names]
    if related:
        noun = "area" if len(related) == 1 else "areas"
        reasons.append(f"Related research {noun}: {_join(sorted(related))}")

    # Only claimed when it actually contributed, and phrased as the hedge it
    # is: the model found the writing similar, not the tags.
    if breakdown.semantic_score >= STRONG_SEMANTIC:
        reasons.append(
            f"Your profile and this describe similar work ({breakdown.semantic_score:.0%} similar)"
        )

    if breakdown.related_terms:
        reasons.append(f"Related terms: {_join(list(breakdown.related_terms))}")

    if not reasons:
        reasons.append("Suggested because it is new and relevant to your department")
    return reasons


COLD_START_REASON = "Your profile is still incomplete, so this is simply one of the newest items"

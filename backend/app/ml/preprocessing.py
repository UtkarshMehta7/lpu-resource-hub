"""Text normalisation for the lexical part of matching."""

from __future__ import annotations

import re
from collections.abc import Iterable

_NON_WORD = re.compile(r"[^a-z0-9]+")


def normalise(text: str | None) -> str:
    """Lower-case, strip punctuation, collapse whitespace."""
    if not text:
        return ""
    return _NON_WORD.sub(" ", text.lower()).strip()


def join_documents(parts: Iterable[str | None]) -> str:
    """One document from several fields (bio, description, abstracts, ...)."""
    return " ".join(filter(None, (normalise(part) for part in parts)))

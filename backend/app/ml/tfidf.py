"""TF-IDF index over item documents, with a small in-memory cache.

The index is rebuilt when the underlying content changes. Change detection
is a "fingerprint" (row count + newest updated_at) supplied by the caller,
so nothing has to remember to invalidate a cache by hand.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from threading import Lock
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

MIN_TERM_SCORE = 1e-6


@dataclass(frozen=True, slots=True)
class TfidfIndex:
    vectorizer: TfidfVectorizer
    matrix: Any  # scipy sparse matrix, rows aligned with item_ids
    item_ids: tuple[uuid.UUID, ...]

    @classmethod
    def build(cls, documents: Sequence[tuple[uuid.UUID, str]]) -> TfidfIndex | None:
        """None when there's nothing to index (no items, or no words at all)."""
        usable = [(item_id, text) for item_id, text in documents if text.strip()]
        if not usable:
            return None
        vectorizer = TfidfVectorizer(stop_words="english", min_df=1, sublinear_tf=True)
        try:
            matrix = vectorizer.fit_transform([text for _, text in usable])
        except ValueError:
            # Every term was a stop word.
            return None
        return cls(vectorizer, matrix, tuple(item_id for item_id, _ in usable))

    def similarities(self, document: str) -> dict[uuid.UUID, float]:
        """Cosine similarity of `document` against every indexed item.

        TfidfVectorizer L2-normalises its rows, so the dot product *is* the
        cosine similarity.
        """
        if not document.strip():
            return {}
        query = self.vectorizer.transform([document])
        scores = (self.matrix @ query.T).toarray().ravel()
        return {item_id: float(score) for item_id, score in zip(self.item_ids, scores, strict=True)}

    def top_terms(self, document: str, item_id: uuid.UUID, limit: int = 3) -> tuple[str, ...]:
        """The terms that actually drove the similarity, strongest first."""
        if item_id not in self.item_ids or not document.strip():
            return ()
        query = self.vectorizer.transform([document])
        row = self.matrix[self.item_ids.index(item_id)]
        contributions = np.asarray(row.multiply(query).todense()).ravel()
        names = self.vectorizer.get_feature_names_out()
        ranked = np.argsort(contributions)[::-1][:limit]
        return tuple(str(names[i]) for i in ranked if contributions[i] > MIN_TERM_SCORE)


class IndexCache:
    """One index per kind of item, replaced when its fingerprint changes."""

    def __init__(self) -> None:
        self._entries: dict[str, tuple[object, TfidfIndex | None]] = {}
        self._lock = Lock()

    def get_or_build(
        self, kind: str, fingerprint: object, documents: Sequence[tuple[uuid.UUID, str]]
    ) -> TfidfIndex | None:
        with self._lock:
            cached = self._entries.get(kind)
            if cached is not None and cached[0] == fingerprint:
                return cached[1]
        index = TfidfIndex.build(documents)
        with self._lock:
            self._entries[kind] = (fingerprint, index)
        return index

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


# One process-wide cache. It holds only derived, public-ish text (the same
# documents the caller could already read), and every read re-checks the
# fingerprint, so a stale index can't outlive a content change.
INDEX_CACHE = IndexCache()

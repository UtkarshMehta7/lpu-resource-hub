"""Sentence embeddings, loaded lazily and optionally.

`sentence-transformers` is an *optional* install (`pip install -e ".[ml]"`).
Everything here answers honestly when it isn't there, so the app keeps
running on the Step 9 lexical/structured path instead of failing.

The model is small (all-MiniLM-L6-v2, 384 dimensions), runs on CPU and is
downloaded once to the local HuggingFace cache -- no API, no per-call cost.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Sequence
from functools import lru_cache
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

_model: Any | None = None
_model_lock = Lock()


@lru_cache(maxsize=1)
def is_available() -> bool:
    """True when the optional ML extra is installed."""
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return False
    return True


def load_model() -> Any | None:
    """The shared model instance, or None when the extra isn't installed.

    Loading takes a few seconds the first time (and downloads the model on a
    cold cache), so it happens on first use rather than at import.
    """
    global _model
    if not is_available():
        return None
    with _model_lock:
        if _model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("loading embedding model %s", MODEL_NAME)
            _model = SentenceTransformer(MODEL_NAME, device="cpu")
    return _model


def embed_texts(texts: Sequence[str]) -> list[list[float]] | None:
    """Embeddings for each text, or None when embeddings are unavailable."""
    if not texts:
        return []
    model = load_model()
    if model is None:
        return None
    # normalize_embeddings makes cosine similarity a plain dot product, which
    # is what pgvector's <=> operator assumes here.
    vectors = model.encode(
        list(texts), normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False
    )
    return [[float(value) for value in vector] for vector in vectors]


def embed_text(text: str) -> list[float] | None:
    vectors = embed_texts([text])
    return vectors[0] if vectors else None


def content_hash(text: str) -> str:
    """Stable fingerprint of the text an embedding was built from.

    Re-embedding is skipped when this hasn't changed, which is what keeps the
    background pipeline cheap.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

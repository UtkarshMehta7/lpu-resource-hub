"""Re-embedding as a background task.

Embedding is not on the critical path of a save: the request returns, then
the entity is (re)embedded with its own session. A failure is logged, never
surfaced -- a missing embedding degrades search, it doesn't break the write.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable

from fastapi import BackgroundTasks, Request
from sqlalchemy.orm import Session

from app.ml.embeddings import is_available
from app.modules.search.models import EntityType
from app.modules.search.service import embed_entity

logger = logging.getLogger(__name__)


def _run(
    session_factory: Callable[[], Session], entity_type: EntityType, entity_id: uuid.UUID
) -> None:
    session = session_factory()
    try:
        embed_entity(session, entity_type, entity_id)
    except Exception:  # noqa: BLE001 - background work must not escalate
        session.rollback()
        logger.exception("re-embedding failed for %s %s", entity_type.value, entity_id)
    finally:
        session.close()


def schedule_embedding(
    request: Request,
    background: BackgroundTasks,
    entity_type: EntityType,
    entity_id: uuid.UUID,
) -> None:
    """Queues a re-embed after the response is sent. No-op without the extra."""
    if not is_available():
        return
    background.add_task(_run, request.app.state.session_factory, entity_type, entity_id)

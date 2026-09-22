"""Embed everything that needs it.

Run after installing the ML extra, or after a bulk import:

    python -m scripts.backfill_embeddings            # every entity type
    python -m scripts.backfill_embeddings --type project

Entities whose content hasn't changed are skipped, so re-running is cheap.
"""

from __future__ import annotations

import argparse
import sys

from app.core.config import get_settings
from app.db.session import create_db_engine, create_session_factory
from app.ml.embeddings import MODEL_NAME, is_available
from app.modules.search.models import EntityType
from app.modules.search.service import embed_all


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--type",
        choices=[entity.value for entity in EntityType],
        help="only embed this entity type",
    )
    args = parser.parse_args()

    if not is_available():
        print(
            "sentence-transformers isn't installed. Install the optional extra first:\n"
            '  pip install -e ".[ml]"'
        )
        return 1

    settings = get_settings()
    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)
    try:
        print(f"Embedding with {MODEL_NAME} into {settings.database_summary()}\n")
        with session_factory() as db:
            written = embed_all(db, EntityType(args.type) if args.type else None)
        for entity_type, count in written.items():
            print(f"  {entity_type:<12} {count} embedded (unchanged content skipped)")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())

"""Imports every ORM model so `Base.metadata` is complete for Alembic autogenerate.

`alembic/env.py` imports this module (not individual model modules) before
reading `target_metadata`, so adding a module's models here is the only step
needed to keep future migrations stable.
"""

from app.modules.auth.models import RefreshToken  # noqa: F401
from app.modules.users.models import User  # noqa: F401

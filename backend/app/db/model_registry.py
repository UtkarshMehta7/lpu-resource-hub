"""Imports every ORM model so `Base.metadata` is complete for Alembic autogenerate.

`alembic/env.py` imports this module (not individual model modules) before
reading `target_metadata`, so adding a module's models here is the only step
needed to keep future migrations stable.
"""

from app.modules.admin.models import Department, School  # noqa: F401
from app.modules.audit.models import AuditLog  # noqa: F401
from app.modules.auth.models import RefreshToken  # noqa: F401
from app.modules.profiles.models import (  # noqa: F401
    ResearcherProfile,
    StudentProfile,
    UserResearchArea,
    UserSkill,
)
from app.modules.projects.models import (  # noqa: F401
    Project,
    ProjectMember,
    ProjectResearchArea,
    ProjectSkill,
)
from app.modules.taxonomy.models import ResearchArea, Skill, TagAlias, TagSuggestion  # noqa: F401
from app.modules.users.models import User  # noqa: F401

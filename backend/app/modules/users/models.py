"""User ORM model and role enum."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserRole(StrEnum):
    STUDENT = "student"
    FACULTY = "faculty"
    RESEARCH_COORDINATOR = "research_coordinator"
    ADMIN = "admin"


class CoordinatorScopeType(StrEnum):
    """A research coordinator's authority scope. Department-level is used today;
    SCHOOL and UNIVERSITY exist so the schema doesn't need to change later."""

    DEPARTMENT = "department"
    SCHOOL = "school"
    UNIVERSITY = "university"


class User(Base):
    __tablename__ = "users"
    # Trigram index so misspelled name searches still match (pg_trgm).
    __table_args__ = (
        Index(
            "ix_users_full_name_trgm",
            "full_name",
            postgresql_using="gin",
            postgresql_ops={"full_name": "gin_trgm_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # The LPU registration / employee number: what people log in with, the
    # same identifier they use in UMS. Stored upper-cased and trimmed, unique,
    # and never changed after creation (an identifier people can edit isn't
    # one -- an admin correction is an audited action).
    registration_number: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    # Optional contact address. Not a credential: nobody logs in with it.
    email: Mapped[str | None] = mapped_column(String(320), unique=True, nullable=True, index=True)
    # True until a user replaces the temporary password their creator set.
    # While true, every endpoint except /me and /auth/change-password is closed.
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    # A research coordinator's authority scope. No FK on coordinator_scope_id:
    # it's a polymorphic reference (a department/school/university id
    # depending on coordinator_scope_type) and none of those tables exist yet
    # (departments arrive in Step 3). Validated at the application layer.
    coordinator_scope_type: Mapped[CoordinatorScopeType | None] = mapped_column(
        Enum(
            CoordinatorScopeType,
            name="coordinator_scope_type",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=True,
    )
    coordinator_scope_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    # Nullable for every role, not just admin: nothing here forces a
    # student/faculty to have one at registration time.
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    # Recomputed (not just read) whenever user_skills/user_research_areas
    # change; true once both have >= 3 rows. See app/modules/profiles/service.py.
    onboarding_complete: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

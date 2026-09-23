"""Creating accounts for other people.

Students don't self-register (ADR 0015): their department creates the
account and hands over a temporary password, which the new user must replace
at first sign-in. Faculty and coordinators may only create accounts in the
department they belong to or oversee; admins anywhere, for any role.
"""

from __future__ import annotations

import secrets
import string
import uuid
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.modules.admin.models import Department
from app.modules.audit import service as audit_service
from app.modules.users.models import CoordinatorScopeType, User, UserRole

# Long enough that a temporary password isn't the weak link, short enough to
# read out loud once.
TEMPORARY_PASSWORD_LENGTH = 14
_ALPHABET = string.ascii_letters + string.digits


class NotAllowedRoleError(Exception):
    """This creator may not create an account with that role."""


class OutOfScopeError(Exception):
    """The creator may not add people to that department."""


class DepartmentRequiredError(Exception):
    """A student account needs a department."""


class UnknownDepartmentError(Exception):
    """No such department."""


class RegistrationNumberTakenError(Exception):
    """That registration number already has an account."""


@dataclass(frozen=True, slots=True)
class CreatedAccount:
    user: User
    # Shown to the creator exactly once; never stored in the clear.
    temporary_password: str


def generate_temporary_password() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(TEMPORARY_PASSWORD_LENGTH))


def _creator_department(creator: User) -> uuid.UUID | None:
    """Which department this creator may add people to."""
    if (
        creator.role is UserRole.RESEARCH_COORDINATOR
        and creator.coordinator_scope_type is CoordinatorScopeType.DEPARTMENT
        and creator.coordinator_scope_id is not None
    ):
        return creator.coordinator_scope_id
    return creator.department_id


def create_account(
    db: Session,
    creator: User,
    *,
    registration_number: str,
    full_name: str,
    role: UserRole,
    department_id: uuid.UUID | None,
    email: str | None,
    ip: str | None,
) -> CreatedAccount:
    if creator.role is not UserRole.ADMIN:
        # Faculty and coordinators create students, in their own department.
        if role is not UserRole.STUDENT:
            raise NotAllowedRoleError
        scope = _creator_department(creator)
        if scope is None:
            raise OutOfScopeError
        if department_id is not None and department_id != scope:
            raise OutOfScopeError
        department_id = scope

    if role is UserRole.STUDENT and department_id is None:
        raise DepartmentRequiredError
    if department_id is not None and db.get(Department, department_id) is None:
        raise UnknownDepartmentError

    temporary_password = generate_temporary_password()
    user = User(
        registration_number=registration_number.strip().upper(),
        email=email.lower() if email else None,
        full_name=full_name.strip(),
        role=role,
        department_id=department_id,
        password_hash=hash_password(temporary_password),
        must_change_password=True,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise RegistrationNumberTakenError from exc

    audit_service.record(
        db,
        actor_id=creator.id,
        action="user.created",
        entity_type="user",
        entity_id=user.id,
        before=None,
        after={
            "registration_number": user.registration_number,
            "role": user.role.value,
            "department_id": str(department_id) if department_id else None,
        },
        ip=ip,
    )
    db.commit()
    db.refresh(user)
    return CreatedAccount(user=user, temporary_password=temporary_password)

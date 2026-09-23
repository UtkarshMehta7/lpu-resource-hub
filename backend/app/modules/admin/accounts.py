"""Provisioning accounts down the institutional hierarchy.

Nobody signs themselves up (ADR 0019). An admin appoints research
coordinators, a coordinator appoints the faculty of the department they
oversee, and a faculty member enrols the students of their own department.
Each new account gets a temporary password its creator hands over once, and
which the new user must replace before they can use anything.

The role of a new account is *derived* from the creator's role via
`creatable_role`; it is never read from the request. There is therefore no
client-supplied role to validate, and none to forge.
"""

from __future__ import annotations

import secrets
import string
import uuid
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.permissions import creatable_role
from app.core.security import hash_password
from app.modules.admin.models import Department
from app.modules.audit import service as audit_service
from app.modules.profiles.models import ResearcherProfile, VerificationStatus
from app.modules.users.models import CoordinatorScopeType, User, UserRole

# Long enough that a temporary password isn't the weak link, short enough to
# read out loud once.
TEMPORARY_PASSWORD_LENGTH = 14
_ALPHABET = string.ascii_letters + string.digits


class NotAllowedRoleError(Exception):
    """This role may not bring anyone into the platform."""


class OutOfScopeError(Exception):
    """The creator may not add people to that department."""


class NoDepartmentError(Exception):
    """The creator has no department of their own to add anyone to."""


class NotVerifiedError(Exception):
    """The creator's researcher profile has not been verified yet."""


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
    """Which department this creator may add people to.

    A coordinator's authority comes from the scope an admin gave them, so it
    is the only thing read here: their own `department_id` says where they
    work, not what they oversee, and it may have been self-declared.
    """
    if creator.role is UserRole.RESEARCH_COORDINATOR:
        if (
            creator.coordinator_scope_type is CoordinatorScopeType.DEPARTMENT
            and creator.coordinator_scope_id is not None
        ):
            return creator.coordinator_scope_id
        return None
    return creator.department_id


def _may_create_in_own_department(db: Session, creator: User) -> bool:
    """Faculty state their own department, so that claim alone can't be what
    lets them create accounts in it — a coordinator has to have verified the
    profile first. Coordinators are placed by an admin, so they're exempt."""
    if creator.role is not UserRole.FACULTY:
        return True
    profile = db.get(ResearcherProfile, creator.id)
    return profile is not None and profile.verification_status is VerificationStatus.VERIFIED


def create_account(
    db: Session,
    creator: User,
    *,
    registration_number: str,
    full_name: str,
    department_id: uuid.UUID | None,
    email: str | None,
    ip: str | None,
) -> CreatedAccount:
    """Create the one role this creator may create, in a department they may
    reach. `role` is deliberately not a parameter: see the module docstring."""
    role = creatable_role(creator.role)
    if role is None:
        raise NotAllowedRoleError

    if creator.role is UserRole.ADMIN:
        # An admin appoints coordinators anywhere, but a coordinator with no
        # department oversees nothing, so the department is required here.
        if department_id is None:
            raise DepartmentRequiredError
    else:
        # Everyone else works inside their own department, and may not name
        # another one.
        if not _may_create_in_own_department(db, creator):
            raise NotVerifiedError
        scope = _creator_department(creator)
        if scope is None:
            raise NoDepartmentError
        if department_id is not None and department_id != scope:
            raise OutOfScopeError
        department_id = scope

    if db.get(Department, department_id) is None:
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
        created_by=creator.id,
    )
    if role is UserRole.RESEARCH_COORDINATOR:
        # A coordinator with no scope can do nothing, and the department just
        # chosen is the one they are being appointed to oversee. Setting it
        # here saves a second admin step that is only ever done one way.
        user.coordinator_scope_type = CoordinatorScopeType.DEPARTMENT
        user.coordinator_scope_id = department_id
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

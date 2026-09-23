"""Account creation endpoint, mounted under /api/v1.

Not under /admin: faculty and coordinators use it too, for students in their
own department. Admins may create any role anywhere.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.permissions import Permission, require_permission
from app.core.rate_limit import client_ip
from app.db.session import get_db
from app.modules.admin import accounts
from app.modules.admin.schemas import AccountCreateRequest, AdminUserRead, CreatedAccountRead
from app.modules.users.models import User

router = APIRouter(tags=["accounts"])

Creator = Annotated[User, Depends(require_permission(Permission.USER_CREATE))]

_ERROR_MAP: dict[type[Exception], tuple[int, str]] = {
    accounts.NotAllowedRoleError: (
        status.HTTP_403_FORBIDDEN,
        "You can only create student accounts.",
    ),
    accounts.OutOfScopeError: (
        status.HTTP_403_FORBIDDEN,
        "You can only add people to your own department.",
    ),
    accounts.NoDepartmentError: (
        status.HTTP_403_FORBIDDEN,
        "Your account is not in a department yet, so there is nowhere to add "
        "anyone. Set your department on your profile, or ask an admin.",
    ),
    accounts.NotVerifiedError: (
        status.HTTP_403_FORBIDDEN,
        "A research coordinator has to verify your researcher profile before "
        "you can add people to your department.",
    ),
    accounts.UnknownDepartmentError: (status.HTTP_404_NOT_FOUND, "Department not found."),
    accounts.DepartmentRequiredError: (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "A student account needs a department.",
    ),
    accounts.RegistrationNumberTakenError: (
        status.HTTP_409_CONFLICT,
        "An account with this registration number already exists.",
    ),
}


@contextmanager
def _domain_errors() -> Iterator[None]:
    try:
        yield
    except tuple(_ERROR_MAP) as exc:
        code, detail = _ERROR_MAP[type(exc)]
        raise HTTPException(status_code=code, detail=detail) from exc


@router.post("/users", response_model=CreatedAccountRead, status_code=status.HTTP_201_CREATED)
def create_account(
    data: AccountCreateRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    creator: Creator,
) -> CreatedAccountRead:
    """Creates an account and returns its temporary password **once**.

    The new user must replace that password before they can use anything
    else, so it is safe to show but not to store.
    """
    with _domain_errors():
        created = accounts.create_account(
            db,
            creator,
            registration_number=data.registration_number,
            full_name=data.full_name,
            role=data.role,
            department_id=data.department_id,
            email=data.email,
            ip=client_ip(request),
        )
    return CreatedAccountRead(
        user=AdminUserRead.model_validate(created.user),
        temporary_password=created.temporary_password,
    )

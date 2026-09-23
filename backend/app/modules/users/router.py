"""User profile endpoints, mounted under /api/v1."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import get_authenticated_user
from app.modules.users.models import User
from app.modules.users.schemas import UserRead

router = APIRouter(tags=["users"])


@router.get("/me", response_model=UserRead)
def read_current_user(current_user: Annotated[User, Depends(get_authenticated_user)]) -> User:
    return current_user

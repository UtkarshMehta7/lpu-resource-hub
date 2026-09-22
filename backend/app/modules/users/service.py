"""User lookups. Services never import FastAPI."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.users.models import User


def get_by_email(db: Session, email: str) -> User | None:
    return db.execute(select(User).where(User.email == email.lower())).scalar_one_or_none()


def get_by_id(db: Session, user_id: uuid.UUID) -> User | None:
    return db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()

"""User lookups. Services never import FastAPI."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.users.models import User


def get_by_email(db: Session, email: str) -> User | None:
    return db.execute(select(User).where(User.email == email.lower())).scalar_one_or_none()


def get_by_registration_number(db: Session, registration_number: str) -> User | None:
    """Lookup by the identifier people log in with (stored upper-cased)."""
    return db.execute(
        select(User).where(User.registration_number == registration_number.strip().upper())
    ).scalar_one_or_none()


def get_by_id(db: Session, user_id: uuid.UUID) -> User | None:
    return db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()

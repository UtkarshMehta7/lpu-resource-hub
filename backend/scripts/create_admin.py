"""CLI to create the first administrator (or a research coordinator).

Nobody self-registers (ADR 0019), so this is how a platform gets its first
account: everyone else is provisioned from it, down the hierarchy. The
password is always prompted (getpass, never echoed, never a CLI argument or
environment variable) so it can't end up in shell history or a process list.

Usage (from backend/, with the venv active):
    python -m scripts.create_admin
"""

from __future__ import annotations

import getpass
import sys

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import MIN_PASSWORD_LENGTH, hash_password, is_common_password
from app.db.session import create_db_engine, create_session_factory
from app.modules.auth.schemas import normalise_registration_number
from app.modules.users.models import User, UserRole

ROLE_CHOICES = (UserRole.ADMIN, UserRole.RESEARCH_COORDINATOR)


def _prompt_registration_number(db: Session) -> str:
    """What they will sign in with. Unique, and compared case-insensitively
    because it is always stored upper-cased."""
    while True:
        raw = input("Registration number: ").strip()
        if len(raw) < 4:
            print("Enter the registration or employee number they sign in with.")
            continue
        registration_number = normalise_registration_number(raw)
        existing = db.execute(
            select(User).where(func.upper(User.registration_number) == registration_number.upper())
        ).scalar_one_or_none()
        if existing is not None:
            print(f"'{registration_number}' already belongs to {existing.full_name}.")
            continue
        return registration_number


def _prompt_email(db: Session) -> str | None:
    """Optional contact address. Nobody signs in with it."""
    while True:
        email = input("Email (optional, press enter to skip): ").strip().lower()
        if not email:
            return None
        if "@" not in email:
            print("Enter a valid email address, or press enter to skip.")
            continue
        existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if existing is not None:
            print(f"An account with '{email}' already exists.")
            continue
        return email


def _prompt_full_name() -> str:
    while True:
        full_name = input("Full name: ").strip()
        if full_name:
            return full_name
        print("Full name must not be blank.")


def _prompt_role() -> UserRole:
    labels = {str(i + 1): role for i, role in enumerate(ROLE_CHOICES)}
    prompt = "Role (" + ", ".join(f"{key}={role.value}" for key, role in labels.items()) + "): "
    while True:
        choice = input(prompt).strip()
        role = labels.get(choice)
        if role is not None:
            return role
        print("Enter one of: " + ", ".join(labels))


def _prompt_password() -> str:
    while True:
        password = getpass.getpass(f"Password (min {MIN_PASSWORD_LENGTH} characters): ")
        if len(password) < MIN_PASSWORD_LENGTH:
            print(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
            continue
        if is_common_password(password):
            print("That password is too common. Choose a different one.")
            continue
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords did not match.")
            continue
        return password


def main() -> int:
    settings = get_settings()
    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)

    try:
        with session_factory() as db:
            print(f"Creating an account in {settings.database_summary()}\n")
            registration_number = _prompt_registration_number(db)
            full_name = _prompt_full_name()
            email = _prompt_email(db)
            role = _prompt_role()
            password = _prompt_password()

            user = User(
                registration_number=registration_number,
                email=email,
                password_hash=hash_password(password),
                full_name=full_name,
                role=role,
                # They chose this password themselves, so there is nothing to
                # replace at first sign-in.
                must_change_password=False,
            )
            db.add(user)
            db.commit()
            print(f"\nCreated {role.value} account {registration_number} for {full_name}.")
            print("They sign in with that number and the password you just set.")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())

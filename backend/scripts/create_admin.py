"""CLI to create an admin or research-coordinator account.

`admin` and `research_coordinator` cannot self-register through the public
API (see app/modules/auth/schemas.py: SelfRegisterableRole). This is the
only way to create one. The password is always prompted (getpass, never
echoed, never a CLI argument or env var) so it can't end up in shell history
or process listings.

Usage (from backend/, with the venv active):
    python -m scripts.create_admin
"""

from __future__ import annotations

import getpass
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import MIN_PASSWORD_LENGTH, hash_password, is_common_password
from app.db.session import create_db_engine, create_session_factory
from app.modules.users.models import User, UserRole

ROLE_CHOICES = (UserRole.ADMIN, UserRole.RESEARCH_COORDINATOR)


def _prompt_email(db: Session) -> str:
    while True:
        email = input("Email: ").strip().lower()
        if not email or "@" not in email:
            print("Enter a valid email address.")
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
            email = _prompt_email(db)
            full_name = _prompt_full_name()
            role = _prompt_role()
            password = _prompt_password()

            user = User(
                email=email,
                password_hash=hash_password(password),
                full_name=full_name,
                role=role,
            )
            db.add(user)
            db.commit()
            print(f"\nCreated {role.value} account for {email}.")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())

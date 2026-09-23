"""Ownership/invariant guards for admin user management.

Checked after the target user is loaded, before the mutation is applied --
the "resource policy" layer in docs/architecture.md §6, applied here to
admin's own actions since no other domain resource exists yet.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.users.models import User, UserRole


class SelfRoleChangeError(Exception):
    """Raised when an admin tries to change their own role."""


class LastActiveAdminError(Exception):
    """Raised when a change would leave the platform with zero active admins."""


class SelfPasswordResetError(Exception):
    """Raised when an admin tries to reset their own password this way."""


def assert_not_self_role_change(actor: User, target: User) -> None:
    if actor.id == target.id:
        raise SelfRoleChangeError


def assert_not_self_password_reset(actor: User, target: User) -> None:
    """An admin resetting their own password here would lock themselves behind
    the password-change gate for no reason: /auth/change-password is the way."""
    if actor.id == target.id:
        raise SelfPasswordResetError


def assert_preserves_last_active_admin(
    db: Session,
    target: User,
    *,
    new_role: UserRole | None = None,
    new_is_active: bool | None = None,
) -> None:
    """Raises if `target` is currently an active admin and this change would
    make them not one (role change away from ADMIN, or deactivation), while
    no other active admin exists to take over."""
    is_currently_active_admin = target.role is UserRole.ADMIN and target.is_active
    stops_being_admin = new_role is not None and new_role is not UserRole.ADMIN
    stops_being_active = new_is_active is False

    if not is_currently_active_admin or not (stops_being_admin or stops_being_active):
        return

    other_active_admins = db.execute(
        select(func.count())
        .select_from(User)
        .where(User.role == UserRole.ADMIN, User.is_active.is_(True), User.id != target.id)
    ).scalar_one()
    if other_active_admins == 0:
        raise LastActiveAdminError

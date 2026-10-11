"""Who may post a notice, how far it carries, and who may read it.

Two separate questions, and keeping them apart is the point:

*Reading* needs no permission at all. Every signed-in role sees what is
addressed to them -- a student, a facility custodian and the dean read the
same board. There is no role filter anywhere in this module.

*Posting* is `Permission.ANNOUNCEMENT_POST`, and the reach of a post is
DERIVED from the poster rather than named in the request, the same discipline
`CREATABLE_ROLE` holds for a new account's role. A coordinator's notice
carries across their own department, because that is what a coordinator's
scope is everywhere else in this schema; institution-wide is the dean's and
the administrator's. Letting the request choose would hand every coordinator
an institution-wide megaphone through a field.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ColumnElement, and_, false, or_

from app.core.permissions import INSTITUTION_WIDE_ROLES
from app.modules.announcements.models import Announcement, AnnouncementAudience, AnnouncementStatus
from app.modules.users.models import CoordinatorScopeType, User, UserRole


class NoScopeToPostError(Exception):
    """A coordinator with no department has nobody to address.

    `_sync_coordinator_scope` makes this unreachable through the application,
    but a row predating it (or written by a script) could still be in this
    state, and a notice addressed to nobody must fail loudly rather than
    quietly become institution-wide.
    """


def reach_of(actor: User) -> tuple[AnnouncementAudience, uuid.UUID | None]:
    """The audience this person posts to, derived -- never read from a request.

    Institution-wide roles address the institution. A coordinator addresses
    the department they are the coordinator *of*, which is their
    `coordinator_scope_id` rather than their `department_id`: the two are kept
    in step by `_sync_coordinator_scope`, and the scope is the one that means
    authority.
    """
    if actor.role in INSTITUTION_WIDE_ROLES:
        return AnnouncementAudience.INSTITUTION, None
    if (
        actor.role is UserRole.RESEARCH_COORDINATOR
        and actor.coordinator_scope_type is CoordinatorScopeType.DEPARTMENT
        and actor.coordinator_scope_id is not None
    ):
        return AnnouncementAudience.DEPARTMENT, actor.coordinator_scope_id
    raise NoScopeToPostError


def visibility_filter(viewer: User) -> ColumnElement[bool]:
    """The rows this person may see, as a filter.

    Used by the list, the single read, the unread count and the attachment
    download, so none of them can disagree with the others -- the same reason
    milestones call the projects module's filter instead of restating it.

    A published institution-wide notice is visible to everyone. A published
    departmental one is visible to that department, and to the roles that
    answer to the institution rather than to a department (an administrator
    and the dean oversee every department, so withholding a department's
    notices from them would be a gap, not a privacy guarantee).

    **A DRAFT is its author's alone -- administrators included.** The form
    tells the author that nobody else can see it, and that has to be true;
    the same "404 for everyone else, admins included" the conversation
    threads answer with. An administrator still answers for the BOARD, which
    is what `may_withdraw` is for, and they can see a withdrawn notice so
    there is somebody able to clear it away.
    """
    published = Announcement.status == AnnouncementStatus.PUBLISHED
    if viewer.role in INSTITUTION_WIDE_ROLES:
        addressed: ColumnElement[bool] = published
    else:
        addressed = and_(
            published,
            or_(
                Announcement.audience == AnnouncementAudience.INSTITUTION,
                and_(
                    Announcement.audience == AnnouncementAudience.DEPARTMENT,
                    Announcement.department_id == viewer.department_id,
                )
                if viewer.department_id is not None
                # No department means no departmental notice is addressed to
                # you. Said plainly rather than left to `= NULL`, which is
                # never true and would read like an oversight.
                else false(),
            ),
        )
    own = Announcement.posted_by == viewer.id
    if viewer.role is UserRole.ADMIN:
        return or_(addressed, own, Announcement.status == AnnouncementStatus.WITHDRAWN)
    return or_(addressed, own)


def may_edit(actor: User, announcement: Announcement) -> bool:
    """Only the author edits the words, and only before anybody has read them.

    An administrator may withdraw somebody else's notice (see `may_withdraw`)
    but never rewrite it: changing what another person is recorded as having
    announced is a different and worse power than taking it down.
    """
    return announcement.posted_by == actor.id and announcement.status is AnnouncementStatus.DRAFT


def may_publish(actor: User, announcement: Announcement) -> bool:
    return announcement.posted_by == actor.id and announcement.status is AnnouncementStatus.DRAFT


def may_withdraw(actor: User, announcement: Announcement) -> bool:
    if announcement.status is not AnnouncementStatus.PUBLISHED:
        return False
    return announcement.posted_by == actor.id or actor.role is UserRole.ADMIN


def may_delete(actor: User, announcement: Announcement) -> bool:
    """A draft is the author's to discard; anything published is history.

    Withdrawing takes a notice off the board and leaves the record of it.
    Deleting a published notice would let somebody unsay a thing the whole
    institution read, so only an administrator may, and only once it is
    already withdrawn.
    """
    if announcement.status is AnnouncementStatus.DRAFT:
        return announcement.posted_by == actor.id
    return announcement.status is AnnouncementStatus.WITHDRAWN and actor.role is UserRole.ADMIN

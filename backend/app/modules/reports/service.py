"""Content reports: anyone can report something they can see; moderators
resolve them.

A report can't be used to probe for hidden content: the target must exist
*and* be visible to the reporter, otherwise it's a 404.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.audit import service as audit_service
from app.modules.opportunities.models import Opportunity, OpportunityStatus
from app.modules.opportunities.policies import visibility_filter as opportunity_visibility
from app.modules.profiles.models import ResearcherProfile
from app.modules.projects.models import Project, ProjectStatus
from app.modules.projects.policies import visibility_filter as project_visibility
from app.modules.publications.models import Publication
from app.modules.reports.models import ContentReport, ReportStatus, ReportTargetType
from app.modules.reports.schemas import ReportCreate, ReportRead, ReportResolve
from app.modules.users.models import User


class TargetNotFoundError(Exception):
    """The reported thing doesn't exist, or the reporter can't see it."""


class ReportNotFoundError(Exception):
    """No such report."""


class DuplicateReportError(Exception):
    """This reporter already has an open report about this item."""


class AlreadyResolvedError(Exception):
    """The report has already been dealt with."""


def _target_title(
    db: Session, viewer: User, target_type: ReportTargetType, target_id: uuid.UUID
) -> str | None:
    """The target's title, or None when it's no longer visible."""
    if target_type is ReportTargetType.PROJECT:
        return db.execute(
            select(Project.title).where(
                Project.id == target_id,
                Project.deleted_at.is_(None),
                project_visibility(viewer),
            )
        ).scalar_one_or_none()
    if target_type is ReportTargetType.OPPORTUNITY:
        return db.execute(
            select(Opportunity.title).where(
                Opportunity.id == target_id, opportunity_visibility(viewer)
            )
        ).scalar_one_or_none()
    if target_type is ReportTargetType.PUBLICATION:
        return db.execute(
            select(Publication.title).where(Publication.id == target_id)
        ).scalar_one_or_none()
    return db.execute(
        select(User.full_name)
        .join(ResearcherProfile, ResearcherProfile.user_id == User.id)
        .where(User.id == target_id, User.is_active.is_(True))
    ).scalar_one_or_none()


def _to_reads(db: Session, viewer: User, rows: Sequence[ContentReport]) -> list[ReportRead]:
    if not rows:
        return []
    names = {
        user_id: name
        for user_id, name in db.execute(
            select(User.id, User.full_name).where(
                User.id.in_({report.reporter_id for report in rows})
            )
        ).all()
    }
    return [
        ReportRead(
            id=report.id,
            reporter_id=report.reporter_id,
            reporter_name=names.get(report.reporter_id, ""),
            target_type=report.target_type,
            target_id=report.target_id,
            target_title=_target_title(db, viewer, report.target_type, report.target_id),
            reason=report.reason,
            status=report.status,
            reviewed_by=report.reviewed_by,
            reviewed_at=report.reviewed_at,
            resolution_note=report.resolution_note,
            created_at=report.created_at,
        )
        for report in rows
    ]


def create_report(db: Session, reporter: User, data: ReportCreate) -> ReportRead:
    if _target_title(db, reporter, data.target_type, data.target_id) is None:
        raise TargetNotFoundError
    report = ContentReport(
        reporter_id=reporter.id,
        target_type=data.target_type,
        target_id=data.target_id,
        reason=data.reason,
    )
    db.add(report)
    try:
        # The partial unique index allows one open report per reporter per item.
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateReportError from exc
    db.refresh(report)
    return _to_reads(db, reporter, [report])[0]


def list_reports(
    db: Session, moderator: User, status: ReportStatus | None = ReportStatus.OPEN
) -> list[ReportRead]:
    query = select(ContentReport)
    if status is not None:
        query = query.where(ContentReport.status == status)
    rows = db.execute(query.order_by(ContentReport.created_at)).scalars().all()
    return _to_reads(db, moderator, list(rows))


def _hide_target(db: Session, report: ContentReport) -> bool:
    """Takes the reported content out of circulation, where that's meaningful.

    A project is archived and an opening is closed -- both existing states, so
    nothing is destroyed and the owner can still see their own item. Reported
    publications and profiles have no equivalent, so this is a no-op for them
    and the audit row records that nothing was hidden.
    """
    if report.target_type is ReportTargetType.PROJECT:
        project = db.get(Project, report.target_id)
        if project is None or project.status is ProjectStatus.ARCHIVED:
            return False
        project.status = ProjectStatus.ARCHIVED
        return True
    if report.target_type is ReportTargetType.OPPORTUNITY:
        opportunity = db.get(Opportunity, report.target_id)
        if opportunity is None or opportunity.status is OpportunityStatus.CLOSED:
            return False
        opportunity.status = OpportunityStatus.CLOSED
        return True
    return False


def resolve_report(
    db: Session, moderator: User, report_id: uuid.UUID, data: ReportResolve, *, ip: str | None
) -> ReportRead:
    report = db.get(ContentReport, report_id)
    if report is None:
        raise ReportNotFoundError
    if report.status is not ReportStatus.OPEN:
        raise AlreadyResolvedError
    hidden = _hide_target(db, report) if data.hide_target else False
    report.status = data.status
    report.reviewed_by = moderator.id
    report.reviewed_at = datetime.now(UTC)
    report.resolution_note = data.note
    audit_service.record(
        db,
        actor_id=moderator.id,
        action=f"report.{data.status.value}",
        entity_type="content_report",
        entity_id=report.id,
        before={"status": ReportStatus.OPEN.value},
        after={"status": data.status.value, "note": data.note, "hidden": hidden},
        ip=ip,
    )
    db.commit()
    db.refresh(report)
    return _to_reads(db, moderator, [report])[0]

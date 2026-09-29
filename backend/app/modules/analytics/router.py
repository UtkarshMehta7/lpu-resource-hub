"""Dashboard endpoint, mounted under /api/v1."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.deps import get_current_user
from app.core.permissions import Permission, require_permission
from app.db.session import get_db
from app.ml import embeddings
from app.modules.analytics import academic_year, exporters, insights, institutional, service
from app.modules.analytics.analytics_schemas import (
    AcademicYearOption,
    AnalyticsOverview,
    CollaborationNetwork,
    EquipmentUsage,
    InstitutionalReportRead,
    LabelledCount,
    MilestoneAdherence,
    NetworkEdge,
    NetworkNode,
    PlatformSettings,
    TrendPoint,
    VerificationBacklog,
)
from app.modules.analytics.network import build_graph
from app.modules.analytics.schemas import DashboardResponse
from app.modules.recommendations.weights import score_weights
from app.modules.users.models import User

router = APIRouter(tags=["dashboard"])


@router.get("/me/dashboard", response_model=DashboardResponse)
def read_dashboard(
    db: Annotated[Session, Depends(get_db)],
    viewer: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DashboardResponse:
    return service.dashboard(db, viewer, score_weights(settings))


@router.get("/analytics/overview", response_model=AnalyticsOverview)
def read_analytics_overview(
    db: Annotated[Session, Depends(get_db)],
    viewer: Annotated[User, Depends(require_permission(Permission.ANALYTICS_READ))],
) -> AnalyticsOverview:
    """Aggregates for the viewer's slice: a coordinator's department, or the
    whole platform for an admin. Counts only -- no personal data."""
    scope = insights.scope_for(viewer)
    return AnalyticsOverview(
        scope="platform" if scope.is_platform else "department",
        department_id=str(scope.department_id) if scope.department_id else None,
        projects_by_status=insights.projects_by_status(db, scope),
        projects_by_area=[LabelledCount(**row) for row in insights.projects_by_area(db, scope)],
        opportunity_funnel=insights.opportunity_funnel(db, scope),
        equipment_utilisation=[
            EquipmentUsage(**row) for row in insights.equipment_utilisation(db, scope)
        ],
        funding_interest=[LabelledCount(**row) for row in insights.funding_interest(db, scope)],
        verification_backlog=VerificationBacklog(**insights.verification_backlog(db, scope)),
        accepted_collaborations=insights.collaboration_totals(db, scope)["accepted_collaborations"],
        open_reports=insights.open_reports(db),
        milestone_adherence=MilestoneAdherence(**insights.milestone_adherence(db, scope)),
        trends=[TrendPoint(**row) for row in insights.trends(db, scope)],
    )


@router.get("/analytics/network", response_model=CollaborationNetwork)
def read_collaboration_network(
    db: Annotated[Session, Depends(get_db)],
    viewer: Annotated[User, Depends(require_permission(Permission.ANALYTICS_READ))],
) -> CollaborationNetwork:
    """Who has worked with whom: co-authorship, shared projects and accepted
    collaboration requests. Students appear only if they opted in."""
    scope = insights.scope_for(viewer)
    graph = build_graph(db, scope)
    return CollaborationNetwork(
        scope="platform" if scope.is_platform else "department",
        nodes=[NetworkNode.model_validate(node) for node in graph["nodes"]],
        edges=[NetworkEdge.model_validate(edge) for edge in graph["edges"]],
    )


@router.get("/admin/settings", response_model=PlatformSettings)
def read_platform_settings(
    settings: Annotated[Settings, Depends(get_settings)],
    admin: Annotated[User, Depends(require_permission(Permission.USER_LIST))],
) -> PlatformSettings:
    """What this deployment is configured to do. Read-only, and no secrets:
    changing behaviour is a deploy, not a click."""
    return PlatformSettings(
        environment=settings.app_env.value,
        settings={
            "recommendation_weights": {
                "skill": settings.rec_weight_skill,
                "area": settings.rec_weight_area,
                "text": settings.rec_weight_text,
                "semantic": settings.rec_semantic_weight,
            },
            "semantic_search_available": embeddings.is_available(),
            "deadline_reminder_scheduler": settings.enable_scheduler,
            "milestone_at_risk_days": settings.milestone_at_risk_days,
            "reminder_interval_minutes": settings.reminder_interval_minutes,
            "access_token_expire_minutes": settings.access_token_expire_minutes,
            "refresh_token_expire_days": settings.refresh_token_expire_days,
        },
    )


# --- the institutional research report --------------------------------------


@router.get("/analytics/academic-years", response_model=list[AcademicYearOption])
def list_academic_years(
    viewer: Annotated[User, Depends(require_permission(Permission.ANALYTICS_READ))],
) -> list[AcademicYearOption]:
    """Years the report can be run for, newest first."""
    current = academic_year.current()
    return [
        AcademicYearOption(
            label=year.label,
            start=year.start.isoformat(),
            end=year.end.isoformat(),
            is_current=year.label == current.label,
        )
        for year in academic_year.recent()
    ]


@router.get("/analytics/institutional-report", response_model=InstitutionalReportRead)
def read_institutional_report(
    db: Annotated[Session, Depends(get_db)],
    viewer: Annotated[User, Depends(require_permission(Permission.ANALYTICS_READ))],
    academic_year_label: Annotated[
        str | None,
        Query(
            alias="academic_year",
            description="Academic year, e.g. 2025-26. Defaults to the current one.",
            max_length=16,
        ),
    ] = None,
) -> InstitutionalReportRead:
    """The full-year institutional research report, scoped to the viewer.

    A coordinator sees their department, an administrator the institution.
    Every figure is counted at request time from real rows.
    """
    year = _resolve_year(academic_year_label)
    report = institutional.build(db, insights.scope_for(viewer), year)
    return InstitutionalReportRead.model_validate(report, from_attributes=True)


@router.get(
    "/analytics/institutional-report/export",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/csv": {}, "application/pdf": {}}}},
)
def export_institutional_report(
    db: Annotated[Session, Depends(get_db)],
    viewer: Annotated[User, Depends(require_permission(Permission.ANALYTICS_READ))],
    export_format: Annotated[
        Literal["csv", "pdf"], Query(alias="format", description="csv or pdf")
    ] = "pdf",
    academic_year_label: Annotated[str | None, Query(alias="academic_year", max_length=16)] = None,
) -> StreamingResponse:
    """The same report as a file. Same aggregation, so the numbers cannot differ."""
    year = _resolve_year(academic_year_label)
    report = institutional.build(db, insights.scope_for(viewer), year)

    if export_format == "csv":
        payload: bytes = exporters.to_csv(report).encode("utf-8-sig")
        media_type, suffix = "text/csv", "csv"
    else:
        payload = exporters.to_pdf(report)
        media_type, suffix = "application/pdf", "pdf"

    filename = f"{report.filename_stem}.{suffix}"
    return StreamingResponse(
        iter([payload]),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _resolve_year(label: str | None) -> academic_year.AcademicYear:
    if label is None:
        return academic_year.current()
    try:
        return academic_year.parse(label)
    except academic_year.InvalidAcademicYearError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

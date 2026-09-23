"""Analytics response shapes. Counts and labels only -- never people."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class LabelledCount(BaseModel):
    label: str
    count: int


class EquipmentUsage(BaseModel):
    label: str
    hours: float
    bookings: int


class TrendPoint(BaseModel):
    month: str
    projects: int
    applications: int
    bookings: int


class VerificationBacklog(BaseModel):
    pending: int
    oldest_waiting_since: str | None


class AnalyticsOverview(BaseModel):
    # "department" or "platform": says plainly whose numbers these are.
    scope: str
    department_id: str | None
    projects_by_status: dict[str, int]
    projects_by_area: list[LabelledCount]
    opportunity_funnel: dict[str, int]
    equipment_utilisation: list[EquipmentUsage]
    funding_interest: list[LabelledCount]
    verification_backlog: VerificationBacklog
    accepted_collaborations: int
    open_reports: int
    trends: list[TrendPoint]


class NetworkNode(BaseModel):
    id: str
    full_name: str
    role: str
    department_id: str | None
    degree: int
    connected: bool


class NetworkEdge(BaseModel):
    source: str
    target: str
    kinds: list[str]
    weight: int


class CollaborationNetwork(BaseModel):
    scope: str
    nodes: list[NetworkNode]
    edges: list[NetworkEdge]


class PlatformSettings(BaseModel):
    """Read-only view of the knobs this deployment is running with.

    Secrets are deliberately absent: this shows behaviour, not credentials.
    """

    environment: str
    settings: dict[str, Any]

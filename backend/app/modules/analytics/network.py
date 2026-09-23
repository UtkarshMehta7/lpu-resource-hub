"""The collaboration network as graph JSON.

Nodes are people, edges are the three ways this platform records that two
people worked together: co-authoring a publication, sharing a project, and
an accepted collaboration request.

Privacy rules, applied in the queries rather than after the fact:

* Students appear only if they opted in to discovery (`is_discoverable`);
  researchers appear because the directory is already public.
* A node carries a name, role and department -- no email, no registration
  number, no contact details.
* A coordinator's graph is limited to their department; only an admin sees
  the whole platform.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.analytics.insights import Scope
from app.modules.collaborations.models import CollaborationRequest, CollaborationStatus
from app.modules.profiles.models import ResearcherProfile, StudentProfile
from app.modules.projects.models import Project, ProjectMember
from app.modules.publications.models import PublicationAuthor
from app.modules.users.models import User

EdgeKind = str
CO_AUTHORSHIP: EdgeKind = "co_authorship"
PROJECT: EdgeKind = "project"
COLLABORATION: EdgeKind = "collaboration"

# A graph nobody can read is no use; this keeps the payload and the SVG sane.
MAX_NODES = 150


@dataclass(frozen=True, slots=True)
class Node:
    id: uuid.UUID
    full_name: str
    role: str
    department_id: uuid.UUID | None


@dataclass
class Edge:
    source: uuid.UUID
    target: uuid.UUID
    kinds: set[EdgeKind] = field(default_factory=set)
    weight: int = 0


def _visible_people(db: Session, scope: Scope) -> dict[uuid.UUID, Node]:
    """Researchers, plus students who opted in to being discoverable."""
    query = (
        select(User)
        .outerjoin(ResearcherProfile, ResearcherProfile.user_id == User.id)
        .outerjoin(StudentProfile, StudentProfile.user_id == User.id)
        .where(
            User.is_active.is_(True),
            (ResearcherProfile.user_id.is_not(None)) | (StudentProfile.is_discoverable.is_(True)),
        )
    )
    if not scope.is_platform:
        query = query.where(User.department_id == scope.department_id)
    return {
        user.id: Node(
            id=user.id,
            full_name=user.full_name,
            role=user.role.value,
            department_id=user.department_id,
        )
        for user in db.execute(query.limit(MAX_NODES)).scalars()
    }


def _add(
    edges: dict[tuple[uuid.UUID, uuid.UUID], Edge], a: uuid.UUID, b: uuid.UUID, kind: EdgeKind
) -> None:
    if a == b:
        return
    key = (a, b) if str(a) < str(b) else (b, a)
    edge = edges.get(key)
    if edge is None:
        edge = Edge(source=key[0], target=key[1])
        edges[key] = edge
    edge.kinds.add(kind)
    edge.weight += 1


def _pairs(members: Iterable[uuid.UUID]) -> Iterable[tuple[uuid.UUID, uuid.UUID]]:
    return combinations(sorted(set(members), key=str), 2)


def build_graph(db: Session, scope: Scope) -> dict[str, list[dict[str, object]]]:
    nodes = _visible_people(db, scope)
    visible = set(nodes)
    edges: dict[tuple[uuid.UUID, uuid.UUID], Edge] = {}

    # Co-authorship: everyone named on the same publication.
    by_publication: dict[uuid.UUID, list[uuid.UUID]] = {}
    for publication_id, user_id in db.execute(
        select(PublicationAuthor.publication_id, PublicationAuthor.user_id).where(
            PublicationAuthor.user_id.in_(visible)
        )
    ).all():
        if user_id is not None:
            by_publication.setdefault(publication_id, []).append(user_id)
    for authors in by_publication.values():
        for left, right in _pairs(authors):
            _add(edges, left, right, CO_AUTHORSHIP)

    # Project membership: the owner and every member of the same project.
    by_project: dict[uuid.UUID, list[uuid.UUID]] = {}
    for project_id, owner_id in db.execute(
        select(Project.id, Project.owner_id).where(
            Project.deleted_at.is_(None), Project.owner_id.in_(visible)
        )
    ).all():
        by_project.setdefault(project_id, []).append(owner_id)
    for project_id, member_id in db.execute(
        select(ProjectMember.project_id, ProjectMember.user_id).where(
            ProjectMember.user_id.in_(visible)
        )
    ).all():
        by_project.setdefault(project_id, []).append(member_id)
    for members in by_project.values():
        for left, right in _pairs(members):
            _add(edges, left, right, PROJECT)

    # Accepted collaboration requests.
    for sender_id, recipient_id in db.execute(
        select(CollaborationRequest.sender_id, CollaborationRequest.recipient_id).where(
            CollaborationRequest.status == CollaborationStatus.ACCEPTED,
            CollaborationRequest.sender_id.in_(visible),
            CollaborationRequest.recipient_id.in_(visible),
        )
    ).all():
        _add(edges, sender_id, recipient_id, COLLABORATION)

    connected = {edge.source for edge in edges.values()} | {edge.target for edge in edges.values()}
    return {
        "nodes": [
            {
                "id": str(node.id),
                "full_name": node.full_name,
                "role": node.role,
                "department_id": str(node.department_id) if node.department_id else None,
                "degree": sum(
                    1 for edge in edges.values() if node.id in (edge.source, edge.target)
                ),
                "connected": node.id in connected,
            }
            for node in _ordered(nodes.values())
        ],
        "edges": [
            {
                "source": str(edge.source),
                "target": str(edge.target),
                "kinds": sorted(edge.kinds),
                "weight": edge.weight,
            }
            for edge in edges.values()
        ],
    }


def _ordered(nodes: Iterable[Node]) -> Sequence[Node]:
    """Stable order, so the same data always draws the same graph."""
    return sorted(nodes, key=lambda node: (node.full_name, str(node.id)))

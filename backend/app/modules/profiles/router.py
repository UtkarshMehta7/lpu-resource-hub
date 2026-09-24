"""Profile endpoints, mounted under /api/v1/me.

GET/PUT /me/profile is one literal endpoint pair per spec, but a student and
a researcher have genuinely different profile shapes -- not optional fields
of one schema. The response is validated against a Union response_model;
the PUT request body is parsed manually and validated against whichever
schema matches current_user.role, since FastAPI can't declare a
role-conditional body type on one route declaratively.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.modules.admin.models import Department
from app.modules.profiles.models import ResearcherProfile, StudentProfile
from app.modules.profiles.saved import (
    AlreadySavedError,
    SavedItemNotFoundError,
    TargetNotFoundError,
    delete_saved_item,
    list_saved,
    save_item,
)
from app.modules.profiles.saved_schemas import SavedCreate, SavedEntry, SavedType
from app.modules.profiles.schemas import (
    DepartmentCoordinatorRead,
    ResearchAreaEntry,
    ResearcherProfileRead,
    ResearcherProfileUpdate,
    SkillEntry,
    StudentProfileRead,
    StudentProfileUpdate,
)
from app.modules.profiles.service import (
    DepartmentLockedError,
    DepartmentNotFoundError,
    ProfileNotFoundError,
    ResearchAreaNotFoundError,
    SkillNotFoundError,
    department_is_locked,
    get_profile,
    set_research_areas,
    set_skills,
    upsert_researcher_profile,
    upsert_student_profile,
)
from app.modules.search.models import EntityType
from app.modules.search.tasks import schedule_embedding
from app.modules.users.models import User, UserRole

router = APIRouter(prefix="/me", tags=["profiles"])

ProfileRead = StudentProfileRead | ResearcherProfileRead


def _to_read_schema(
    db: Session, user: User, profile: StudentProfile | ResearcherProfile
) -> ProfileRead:
    """The department lives on the user, not the profile row, but it is edited
    on the profile form -- so it is answered here alongside it."""
    extra = {
        "department_id": user.department_id,
        "department_locked": department_is_locked(db, user),
    }
    if isinstance(profile, StudentProfile):
        return StudentProfileRead.model_validate(profile).model_copy(update=extra)
    return ResearcherProfileRead.model_validate(profile).model_copy(update=extra)


@contextmanager
def _department_errors() -> Iterator[None]:
    try:
        yield
    except DepartmentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Department not found."
        ) from exc
    except DepartmentLockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Your department was set when your profile was verified. "
            "Ask an admin to change it.",
        ) from exc


@router.get("/profile", response_model=StudentProfileRead | ResearcherProfileRead)
def read_my_profile(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ProfileRead:
    try:
        profile = get_profile(db, current_user)
    except ProfileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not created yet. PUT /api/v1/me/profile to create it.",
        ) from exc
    return _to_read_schema(db, current_user, profile)


@router.put("/profile", response_model=StudentProfileRead | ResearcherProfileRead)
async def update_my_profile(
    request: Request,
    background: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ProfileRead:
    body = await request.json()

    if current_user.role is UserRole.STUDENT:
        try:
            student_data = StudentProfileUpdate.model_validate(body)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=exc.errors()
            ) from exc
        with _department_errors():
            student_profile = upsert_student_profile(db, current_user, student_data)
        return _to_read_schema(db, current_user, student_profile)

    try:
        researcher_data = ResearcherProfileUpdate.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=exc.errors()
        ) from exc
    with _department_errors():
        profile = upsert_researcher_profile(db, current_user, researcher_data)
    # The profile text feeds semantic search, so re-embed it after replying.
    schedule_embedding(request, background, EntityType.RESEARCHER, current_user.id)
    return _to_read_schema(db, current_user, profile)


@router.put("/skills", response_model=list[SkillEntry])
def update_my_skills(
    entries: list[SkillEntry],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[SkillEntry]:
    try:
        rows = set_skills(db, current_user.id, entries)
    except SkillNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="One or more skills not found."
        ) from exc
    return [SkillEntry(skill_id=row.skill_id, proficiency=row.proficiency) for row in rows]


@router.put("/research-areas", response_model=list[ResearchAreaEntry])
def update_my_research_areas(
    entries: list[ResearchAreaEntry],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[ResearchAreaEntry]:
    try:
        rows = set_research_areas(db, current_user.id, entries)
    except ResearchAreaNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="One or more research areas not found."
        ) from exc
    return [
        ResearchAreaEntry(research_area_id=row.research_area_id, is_expertise=row.is_expertise)
        for row in rows
    ]


@router.get("/saved", response_model=list[SavedEntry])
def read_saved(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    saved_type: Annotated[SavedType | None, Query(alias="type")] = None,
) -> list[SavedEntry]:
    """Bookmarks whose target is still visible to the caller."""
    return list_saved(db, current_user, saved_type)


@router.post("/saved", response_model=SavedEntry, status_code=status.HTTP_201_CREATED)
def create_saved(
    data: SavedCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SavedEntry:
    try:
        return save_item(db, current_user, data)
    except TargetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="That item was not found."
        ) from exc
    except AlreadySavedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="You have already saved this."
        ) from exc


@router.delete("/saved/{saved_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved(
    saved_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    try:
        delete_saved_item(db, current_user, saved_id)
    except SavedItemNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Saved item not found."
        ) from exc


@router.get("/department", response_model=DepartmentCoordinatorRead | None)
def read_my_department_coordinator(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> DepartmentCoordinatorRead | None:
    """The viewer's department and whoever oversees it.

    Returns null when the viewer has no department. Returns the department
    with an empty coordinator when nobody oversees it yet: "there is no
    coordinator" is useful information, and silence is not.
    """
    if current_user.department_id is None:
        return None

    department = db.get(Department, current_user.department_id)
    if department is None:
        return None

    coordinator = (
        db.execute(
            select(User)
            .where(
                User.role == UserRole.RESEARCH_COORDINATOR,
                User.coordinator_scope_id == department.id,
                User.is_active.is_(True),
            )
            .order_by(User.full_name)
        )
        .scalars()
        .first()
    )
    if coordinator is None:
        return DepartmentCoordinatorRead(
            department_id=department.id, department_name=department.name
        )

    profile = db.get(ResearcherProfile, coordinator.id)
    return DepartmentCoordinatorRead(
        department_id=department.id,
        department_name=department.name,
        user_id=coordinator.id,
        full_name=coordinator.full_name,
        registration_number=coordinator.registration_number,
        designation=profile.designation if profile is not None else None,
        email=coordinator.email,
    )

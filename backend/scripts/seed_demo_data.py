"""Seed fictional demo data: org structure, taxonomy, profiles, people.

Everything created here is FICTIONAL and marked `is_demo` on the user rows.
Names are deliberately synthetic ("Demo Faculty 07") so no row can be
mistaken for a real person or for real LPU data.

Idempotent: re-running matches existing rows by their natural keys (school
name, department name within a school, skill/area name, user email) and
only inserts what's missing, so it is safe to run repeatedly.

The password for every seeded account comes from the SEED_DEMO_PASSWORD
environment variable, or is prompted for; it is never hardcoded. It is
hashed once and reused for all demo accounts (Argon2 is intentionally slow;
hashing 108 times would make the script take minutes for no benefit --
demo-only shortcut, never do this for real accounts).

Usage (from backend/, with the venv active):
    python -m scripts.seed_demo_data
"""

from __future__ import annotations

import getpass
import os
import random
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import MIN_PASSWORD_LENGTH, hash_password, is_common_password
from app.db.session import create_db_engine, create_session_factory
from app.modules.admin.models import Department, School
from app.modules.funding.models import FundingOpportunity
from app.modules.profiles.models import (
    ResearcherAvailability,
    ResearcherProfile,
    StudentProfile,
    UserResearchArea,
    UserSkill,
    VerificationStatus,
)
from app.modules.taxonomy.models import ResearchArea, Skill, TagAlias
from app.modules.users.models import CoordinatorScopeType, User, UserRole

RANDOM_SEED = 20260922
FACULTY_COUNT = 25
STUDENT_COUNT = 80
COORDINATOR_COUNT = 2

SCHOOLS_AND_DEPARTMENTS: dict[str, list[str]] = {
    "School of Computing": [
        "Computer Science",
        "Information Technology",
        "Data Science",
    ],
    "School of Engineering": [
        "Electrical Engineering",
        "Mechanical Engineering",
        "Civil Engineering",
    ],
    "School of Life Sciences": [
        "Biotechnology",
        "Microbiology",
    ],
}

SKILLS = [
    "Python",
    "JavaScript",
    "TypeScript",
    "Java",
    "C++",
    "Go",
    "Rust",
    "R",
    "MATLAB",
    "SQL",
    "PostgreSQL",
    "MongoDB",
    "Redis",
    "Docker",
    "Kubernetes",
    "Linux",
    "Git",
    "CI/CD",
    "AWS",
    "Azure",
    "TensorFlow",
    "PyTorch",
    "scikit-learn",
    "Pandas",
    "NumPy",
    "OpenCV",
    "Keras",
    "Hadoop",
    "Spark",
    "Tableau",
    "Power BI",
    "Statistics",
    "Linear Algebra",
    "Optimisation",
    "Signal Processing",
    "Embedded Systems",
    "VHDL",
    "Verilog",
    "PCB Design",
    "Robotics",
    "CAD",
    "Finite Element Analysis",
    "Thermodynamics",
    "Fluid Dynamics",
    "Structural Analysis",
    "GIS",
    "Remote Sensing",
    "Gene Sequencing",
    "PCR",
    "Cell Culture",
    "Bioinformatics",
    "Mass Spectrometry",
    "Chromatography",
    "Microscopy",
    "Technical Writing",
    "Research Methodology",
    "Grant Writing",
    "Data Visualisation",
    "Experimental Design",
    "Survey Design",
]

RESEARCH_AREA_TREE: dict[str, list[str]] = {
    "Artificial Intelligence": [
        "Machine Learning",
        "Natural Language Processing",
        "Computer Vision",
        "Reinforcement Learning",
    ],
    "Data Science": ["Data Mining", "Big Data Analytics", "Statistical Modelling"],
    "Cloud Computing": ["Distributed Systems", "Edge Computing", "Virtualisation"],
    "Cybersecurity": ["Cryptography", "Network Security", "Privacy"],
    "Internet of Things": ["Sensor Networks", "Embedded Intelligence"],
    "Renewable Energy": ["Solar Energy", "Wind Energy", "Energy Storage"],
    "Robotics": ["Autonomous Navigation", "Human-Robot Interaction", "Actuation"],
    "Biotechnology": ["Genomics", "Proteomics", "Synthetic Biology"],
    "Environmental Science": ["Water Treatment", "Air Quality", "Waste Management"],
    "Materials Science": ["Nanomaterials", "Composites", "Polymer Science"],
}

ALIASES: dict[str, str] = {
    "ML": "Machine Learning",
    "AI": "Artificial Intelligence",
    "NLP": "Natural Language Processing",
    "CV": "Computer Vision",
    "IoT": "Internet of Things",
    "RL": "Reinforcement Learning",
}

STUDENT_PROGRAMS = [
    "B.Tech Computer Science",
    "B.Tech Electronics",
    "M.Tech Data Science",
    "M.Sc Biotechnology",
    "Ph.D Computer Science",
]

DESIGNATIONS = [
    "Assistant Professor",
    "Associate Professor",
    "Professor",
    "Senior Research Fellow",
]


@dataclass
class SeedSummary:
    schools: int = 0
    departments: int = 0
    skills: int = 0
    research_areas: int = 0
    aliases: int = 0
    users: int = 0
    profiles: int = 0
    funding_calls: int = 0

    def render(self) -> str:
        return (
            f"  schools:        {self.schools}\n"
            f"  departments:    {self.departments}\n"
            f"  skills:         {self.skills}\n"
            f"  research areas: {self.research_areas}\n"
            f"  aliases:        {self.aliases}\n"
            f"  users:          {self.users}\n"
            f"  profiles:       {self.profiles}\n"
            f"  funding calls:  {self.funding_calls}"
        )


def _resolve_password() -> str:
    password = os.environ.get("SEED_DEMO_PASSWORD")
    if password is None:
        password = getpass.getpass(
            f"Password for every demo account (min {MIN_PASSWORD_LENGTH} chars): "
        )
    if len(password) < MIN_PASSWORD_LENGTH:
        raise SystemExit(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if is_common_password(password):
        raise SystemExit("That password is too common. Choose a different one.")
    return password


def _seed_org(db: Session, summary: SeedSummary) -> list[Department]:
    existing_schools = {s.name: s for s in db.execute(select(School)).scalars()}
    for name in SCHOOLS_AND_DEPARTMENTS:
        if name not in existing_schools:
            school = School(name=name)
            db.add(school)
            existing_schools[name] = school
            summary.schools += 1
    db.flush()

    existing_departments = {
        (d.school_id, d.name): d for d in db.execute(select(Department)).scalars()
    }
    departments: list[Department] = []
    for school_name, department_names in SCHOOLS_AND_DEPARTMENTS.items():
        school = existing_schools[school_name]
        for department_name in department_names:
            department = existing_departments.get((school.id, department_name))
            if department is None:
                department = Department(school_id=school.id, name=department_name)
                db.add(department)
                existing_departments[(school.id, department_name)] = department
                summary.departments += 1
            departments.append(department)
    db.flush()
    return departments


def _seed_taxonomy(db: Session, summary: SeedSummary) -> tuple[list[Skill], list[ResearchArea]]:
    existing_skills = {s.name: s for s in db.execute(select(Skill)).scalars()}
    for name in SKILLS:
        if name not in existing_skills:
            skill = Skill(name=name)
            db.add(skill)
            existing_skills[name] = skill
            summary.skills += 1

    existing_areas = {a.name: a for a in db.execute(select(ResearchArea)).scalars()}
    for parent_name, child_names in RESEARCH_AREA_TREE.items():
        parent = existing_areas.get(parent_name)
        if parent is None:
            parent = ResearchArea(name=parent_name)
            db.add(parent)
            existing_areas[parent_name] = parent
            summary.research_areas += 1
        db.flush()
        for child_name in child_names:
            if child_name not in existing_areas:
                child = ResearchArea(name=child_name, parent_id=parent.id)
                db.add(child)
                existing_areas[child_name] = child
                summary.research_areas += 1
    db.flush()

    existing_aliases = {a.alias for a in db.execute(select(TagAlias)).scalars()}
    for alias, canonical_name in ALIASES.items():
        if alias in existing_aliases:
            continue
        canonical = existing_areas.get(canonical_name)
        if canonical is None:
            continue
        db.add(TagAlias(alias=alias, research_area_id=canonical.id))
        summary.aliases += 1
    db.flush()

    return list(existing_skills.values()), list(existing_areas.values())


def _demo_registration_number(email: str) -> str:
    local_part = email.split("@", 1)[0]
    return "".join(character for character in local_part if character.isalnum()).upper()


def _seed_user(
    db: Session,
    existing: dict[str, User],
    summary: SeedSummary,
    *,
    email: str,
    full_name: str,
    role: UserRole,
    password_hash: str,
    department: Department | None = None,
    coordinator_scope: Department | None = None,
) -> User:
    user = existing.get(email)
    if user is not None:
        return user
    user = User(
        # Obviously fake, so a demo row can never be mistaken for a real LPU
        # registration number: demo.faculty01@example.com -> DEMOFACULTY01.
        registration_number=_demo_registration_number(email),
        email=email,
        password_hash=password_hash,
        full_name=full_name,
        role=role,
        is_demo=True,
        department_id=department.id if department is not None else None,
        coordinator_scope_type=(
            CoordinatorScopeType.DEPARTMENT if coordinator_scope is not None else None
        ),
        coordinator_scope_id=coordinator_scope.id if coordinator_scope is not None else None,
    )
    db.add(user)
    existing[email] = user
    summary.users += 1
    return user


def _attach_expertise(
    db: Session,
    user: User,
    skills: list[Skill],
    areas: list[ResearchArea],
    rng: random.Random,
) -> None:
    """Gives a user 3-6 skills and 3-5 research areas (enough for onboarding_complete)."""
    if db.execute(select(UserSkill).where(UserSkill.user_id == user.id)).first() is not None:
        return
    for skill in rng.sample(skills, rng.randint(3, 6)):
        db.add(UserSkill(user_id=user.id, skill_id=skill.id, proficiency=rng.randint(2, 5)))
    for area in rng.sample(areas, rng.randint(3, 5)):
        db.add(
            UserResearchArea(
                user_id=user.id, research_area_id=area.id, is_expertise=rng.random() < 0.5
            )
        )
    user.onboarding_complete = True


# Fictional calls from invented bodies. Every row is flagged is_demo so the
# UI can say so; nothing here mirrors a real funding programme.
DEMO_FUNDING = (
    (
        "Demo Research Council",
        "Demo seed grant for low-cost sensing",
        "A fictional demo call for small projects building low-cost sensors.",
        "Demo faculty with a verified researcher profile.",
        "Up to a demo amount",
        45,
    ),
    (
        "Demo Innovation Foundation",
        "Demo student research fellowship",
        "A fictional demo fellowship for student-led research projects.",
        "Demo students in their second year or later.",
        "A demo monthly stipend",
        20,
    ),
    (
        "Demo Agritech Mission",
        "Demo field-trial support grant",
        "A fictional demo grant covering field trials and travel.",
        "Demo faculty running an active project.",
        "A demo travel allowance",
        7,
    ),
)


def _seed_funding(db: Session, summary: SeedSummary, admin: User) -> None:
    """Idempotent: a call is identified by its (fictional) title."""
    existing = {title for (title,) in db.execute(select(FundingOpportunity.title)).all()}
    today = datetime.now(UTC).date()
    for organization, title, description, eligibility, amount, days in DEMO_FUNDING:
        if title in existing:
            continue
        db.add(
            FundingOpportunity(
                organization=organization,
                title=title,
                description=description,
                eligibility=eligibility,
                amount_text=amount,
                deadline=today + timedelta(days=days),
                official_source_url="https://example.org/demo-funding-call",
                is_demo=True,
                created_by=admin.id,
            )
        )
        summary.funding_calls += 1


def seed(db: Session, password_hash: str) -> SeedSummary:
    rng = random.Random(RANDOM_SEED)
    summary = SeedSummary()

    departments = _seed_org(db, summary)
    skills, areas = _seed_taxonomy(db, summary)
    existing_users = {u.email: u for u in db.execute(select(User)).scalars()}

    admin = _seed_user(
        db,
        existing_users,
        summary,
        email="demo.admin@example.com",
        full_name="Demo Admin",
        role=UserRole.ADMIN,
        password_hash=password_hash,
    )

    for index in range(1, COORDINATOR_COUNT + 1):
        department = departments[index - 1]
        _seed_user(
            db,
            existing_users,
            summary,
            email=f"demo.coordinator{index:02d}@example.com",
            full_name=f"Demo Coordinator {index}",
            role=UserRole.RESEARCH_COORDINATOR,
            password_hash=password_hash,
            department=department,
            coordinator_scope=department,
        )

    faculty: list[User] = []
    for index in range(1, FACULTY_COUNT + 1):
        faculty.append(
            _seed_user(
                db,
                existing_users,
                summary,
                email=f"demo.faculty{index:02d}@example.com",
                full_name=f"Demo Faculty {index:02d}",
                role=UserRole.FACULTY,
                password_hash=password_hash,
                department=departments[index % len(departments)],
            )
        )

    students: list[User] = []
    for index in range(1, STUDENT_COUNT + 1):
        students.append(
            _seed_user(
                db,
                existing_users,
                summary,
                email=f"demo.student{index:02d}@example.com",
                full_name=f"Demo Student {index:02d}",
                role=UserRole.STUDENT,
                password_hash=password_hash,
                department=departments[index % len(departments)],
            )
        )
    db.flush()

    existing_researcher_ids = {p.user_id for p in db.execute(select(ResearcherProfile)).scalars()}
    # Most demo faculty are verified so the directory has content; a few stay
    # PENDING so the coordinator verification queue isn't empty to demo.
    for position, member in enumerate(faculty):
        _attach_expertise(db, member, skills, areas, rng)
        if member.id in existing_researcher_ids:
            continue
        db.add(
            ResearcherProfile(
                user_id=member.id,
                designation=DESIGNATIONS[position % len(DESIGNATIONS)],
                bio=f"Fictional demo researcher profile #{position + 1}.",
                availability=rng.choice(list(ResearcherAvailability)),
                verification_status=(
                    VerificationStatus.PENDING if position % 5 == 0 else VerificationStatus.VERIFIED
                ),
            )
        )
        summary.profiles += 1

    existing_student_ids = {p.user_id for p in db.execute(select(StudentProfile)).scalars()}
    for position, student in enumerate(students):
        _attach_expertise(db, student, skills, areas, rng)
        if student.id in existing_student_ids:
            continue
        db.add(
            StudentProfile(
                user_id=student.id,
                program=STUDENT_PROGRAMS[position % len(STUDENT_PROGRAMS)],
                year=(position % 4) + 1,
                bio=f"Fictional demo student profile #{position + 1}.",
                interests="Fictional demo interests.",
                is_discoverable=position % 3 != 0,
            )
        )
        summary.profiles += 1

    _seed_funding(db, summary, admin)

    db.commit()
    return summary


def main() -> int:
    settings = get_settings()
    password = _resolve_password()
    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)

    try:
        print(f"Seeding fictional demo data into {settings.database_summary()}\n")
        with session_factory() as db:
            summary = seed(db, hash_password(password))
        print("Created (existing rows were left untouched):")
        print(summary.render())
        print("\nAll seeded accounts share the password you entered. Demo data only.")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())

"""Seed a populated, presentable instance: four schools and everything under them.

Written for demonstrations. `seed_demo_data.py` produces deliberately synthetic
rows ("Demo Faculty 07") that prove the platform works; this produces rows that
show what the platform is *for* — a directory with real depth, projects at
every stage of review, conversations with something actually said in them, and
a booking calendar with entries on it.

Everything here is still FICTIONAL and still flagged `is_demo`. The names are
ordinary North Indian names because a directory full of "Demo Faculty 07" reads
as a placeholder, not as a university — but no row corresponds to a real
person, and none of it is real LPU data.

Passwords follow the pattern the presenter asked for: a person's first name
followed by 123456, so `Aryan Verma` signs in with `Aryan123456`. That is a
demonstration convenience and nothing else: it is exactly the kind of guessable
credential this platform's own password policy exists to prevent, and it must
never be used for an account that matters.

Idempotent. Re-running matches on natural keys (school name, department within
a school, registration number) and inserts only what is missing, so it is safe
to run repeatedly and safe to run after `seed_demo_data.py`.

Usage, from backend/ with the virtualenv active:

    python -m scripts.seed_presentation_data

Against a deployed database, pass the connection string explicitly:

    DATABASE_URL="postgresql+psycopg://…" python -m scripts.seed_presentation_data
"""

from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from psycopg.types.range import Range
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import create_db_engine, create_session_factory
from app.modules.admin.models import Department, School
from app.modules.bookings.models import Booking, BookingStatus
from app.modules.collaborations.models import (
    Collaboration,
    CollaborationRequest,
    CollaborationState,
    CollaborationStatus,
    normalise_pair,
)
from app.modules.facilities.models import Equipment, Facility
from app.modules.funding.models import FundingOpportunity
from app.modules.messages.models import Conversation, ConversationParticipant, Message
from app.modules.opportunities.models import (
    Opportunity,
    OpportunityStatus,
    OpportunityType,
)
from app.modules.profiles.models import (
    ResearcherAvailability,
    ResearcherProfile,
    StudentProfile,
    UserResearchArea,
    UserSkill,
    VerificationStatus,
)
from app.modules.projects.models import Project, ProjectMember, ProjectStatus
from app.modules.publications.models import (
    Publication,
    PublicationAuthor,
    PublicationType,
)
from app.modules.taxonomy.models import ResearchArea, Skill
from app.modules.users.models import CoordinatorScopeType, User, UserRole

TODAY = date.today()
NOW = datetime.now(UTC)


# --------------------------------------------------------------- the university


@dataclass(frozen=True, slots=True)
class Person:
    name: str
    number: str


@dataclass(frozen=True, slots=True)
class SchoolPlan:
    name: str
    departments: list[str]
    coordinator: Person
    faculty: list[Person]
    students: list[Person]
    skills: list[str]
    areas: list[str]
    #: (title, summary, status) — a mix, so review queues are not empty.
    projects: list[tuple[str, str, ProjectStatus]]
    publications: list[str]
    #: (title, type, days until deadline)
    openings: list[tuple[str, OpportunityType, int]]
    #: (facility, [equipment])
    facilities: list[tuple[str, list[str]]]


PLAN: list[SchoolPlan] = [
    SchoolPlan(
        name="School of Computer Science and Engineering",
        departments=[
            "Computer Science and Engineering",
            "Information Technology",
            "Data Science and Artificial Intelligence",
        ],
        coordinator=Person("Rajesh Khanna", "12400101"),
        faculty=[
            Person("Aryan Verma", "12400111"),
            Person("Neha Gupta", "12400112"),
            Person("Rohit Bansal", "12400113"),
        ],
        students=[
            Person("Aditya Singh", "12400121"),
            Person("Ananya Tiwari", "12400122"),
            Person("Harsh Agarwal", "12400123"),
            Person("Simran Kaur", "12400124"),
            Person("Nikhil Yadav", "12400125"),
            Person("Riya Chawla", "12400126"),
        ],
        skills=[
            "Python",
            "Machine Learning",
            "Deep Learning",
            "Computer Vision",
            "Natural Language Processing",
            "Distributed Systems",
            "Cloud Computing",
            "Cybersecurity",
        ],
        areas=[
            "Artificial Intelligence",
            "Data Engineering",
            "Information Security",
            "Human-Computer Interaction",
        ],
        projects=[
            (
                "Regional language speech recognition for classroom captioning",
                "Low-resource speech models that caption lectures in Hindi and Punjabi live.",
                ProjectStatus.ACTIVE,
            ),
            (
                "Federated learning for campus health records",
                "Training shared models across departments without moving sensitive records.",
                ProjectStatus.ACTIVE,
            ),
            (
                "Detecting phishing in university email at the gateway",
                "A lightweight classifier that flags credential-harvesting mail before delivery.",
                ProjectStatus.PENDING_REVIEW,
            ),
            (
                "Course-timetable optimisation under room constraints",
                "Constraint solving for timetables that respect room capacity and staff load.",
                ProjectStatus.COMPLETED,
            ),
        ],
        publications=[
            "Low-resource speech recognition for Indian classroom audio",
            "A survey of federated learning under institutional data policy",
            "Gateway-level phishing detection with limited labelled mail",
        ],
        openings=[
            ("Research assistant — speech datasets", OpportunityType.RESEARCH_ASSISTANT, 21),
            ("Student researcher — model evaluation", OpportunityType.STUDENT_RESEARCHER, 35),
            ("Summer internship — applied NLP", OpportunityType.RESEARCH_INTERNSHIP, 48),
        ],
        facilities=[
            ("High Performance Computing Lab", ["GPU Cluster Node A", "GPU Cluster Node B"]),
            ("Networks and Security Lab", ["Packet Analyser Workstation", "Isolated Test Rack"]),
        ],
    ),
    SchoolPlan(
        name="School of Management",
        departments=["Business Administration", "Finance and Accounting", "Marketing"],
        coordinator=Person("Priya Malhotra", "12400201"),
        faculty=[
            Person("Sanjay Mehra", "12400211"),
            Person("Kavita Joshi", "12400212"),
        ],
        students=[
            Person("Manish Goel", "12400221"),
            Person("Pooja Bhatia", "12400222"),
            Person("Varun Kapoor", "12400223"),
            Person("Shreya Mittal", "12400224"),
            Person("Rahul Dubey", "12400225"),
        ],
        skills=[
            "Financial Modelling",
            "Survey Design",
            "Econometrics",
            "Consumer Research",
            "Operations Research",
            "Business Analytics",
        ],
        areas=[
            "Entrepreneurship",
            "Behavioural Economics",
            "Supply Chain Management",
            "Financial Inclusion",
        ],
        projects=[
            (
                "Credit access for first-generation entrepreneurs in Punjab",
                "Field study of how small founders reach formal credit, and where they stop.",
                ProjectStatus.ACTIVE,
            ),
            (
                "Consumer response to regional-language advertising",
                "Experimental work on recall and trust when advertising is not in English.",
                ProjectStatus.ACTIVE,
            ),
            (
                "Supply chain resilience for agricultural cooperatives",
                "Mapping where cooperative supply chains break under seasonal stress.",
                ProjectStatus.PENDING_REVIEW,
            ),
        ],
        publications=[
            "Formal credit and the first-generation entrepreneur: evidence from Punjab",
            "Language choice in advertising and recall among semi-urban consumers",
        ],
        openings=[
            ("Research assistant — field survey", OpportunityType.RESEARCH_ASSISTANT, 18),
            ("Project assistant — data coding", OpportunityType.PROJECT_ASSISTANT, 30),
        ],
        facilities=[("Behavioural Research Lab", ["Eye Tracking Station", "Focus Group Room"])],
    ),
    SchoolPlan(
        name="School of Architecture",
        departments=["Architecture", "Urban and Regional Planning"],
        coordinator=Person("Vikram Chauhan", "12400301"),
        faculty=[
            Person("Meera Rathore", "12400311"),
            Person("Arjun Sethi", "12400312"),
        ],
        students=[
            Person("Tanya Arora", "12400321"),
            Person("Gaurav Saini", "12400322"),
            Person("Isha Bajaj", "12400323"),
            Person("Dev Sharma", "12400324"),
        ],
        skills=[
            "Building Information Modelling",
            "Thermal Simulation",
            "Urban Mapping",
            "Structural Detailing",
            "Geographic Information Systems",
        ],
        areas=[
            "Sustainable Design",
            "Urban Heat and Comfort",
            "Heritage Conservation",
            "Affordable Housing",
        ],
        projects=[
            (
                "Passive cooling for low-cost housing in north Indian summers",
                "Measuring how courtyard geometry and shading change indoor temperature.",
                ProjectStatus.ACTIVE,
            ),
            (
                "Mapping urban heat islands across the Jalandhar corridor",
                "Satellite and ground survey work locating where heat concentrates, and why.",
                ProjectStatus.ACTIVE,
            ),
            (
                "Adaptive reuse of disused campus buildings",
                "What it costs, structurally and financially, to reuse rather than rebuild.",
                ProjectStatus.ARCHIVED,
            ),
        ],
        publications=[
            "Courtyard geometry and indoor comfort in low-cost north Indian housing",
            "Ground-truthing satellite heat island maps in a mid-sized Indian city",
        ],
        openings=[
            ("Student researcher — thermal survey", OpportunityType.STUDENT_RESEARCHER, 25),
            ("Collaboration — sensor instrumentation", OpportunityType.COLLABORATION, 40),
        ],
        facilities=[
            ("Building Performance Lab", ["Thermal Imaging Camera", "Weather Station"]),
            ("Design Studio and Fabrication Shop", ["Large Format Plotter", "Laser Cutter"]),
        ],
    ),
    SchoolPlan(
        name="School of Aerospace and Aeronautical Engineering",
        departments=["Aerospace Engineering", "Aeronautical Engineering"],
        coordinator=Person("Anjali Sharma", "12400401"),
        faculty=[
            Person("Ishaan Chopra", "12400411"),
            Person("Karan Ahuja", "12400412"),
            Person("Divya Saxena", "12400413"),
        ],
        students=[
            Person("Siddharth Pandey", "12400421"),
            Person("Megha Dhawan", "12400422"),
            Person("Kunal Thakur", "12400423"),
            Person("Aarti Bhardwaj", "12400424"),
            Person("Nisha Rana", "12400425"),
        ],
        skills=[
            "Computational Fluid Dynamics",
            "Finite Element Analysis",
            "Flight Dynamics",
            "Composite Materials",
            "Propulsion Systems",
            "Control Systems",
        ],
        areas=[
            "Unmanned Aerial Systems",
            "Aerodynamics",
            "Lightweight Structures",
            "Space Propulsion",
        ],
        projects=[
            (
                "Fixed-wing UAV for crop health survey over small holdings",
                "An airframe and payload sized for farms too small for commercial survey flights.",
                ProjectStatus.ACTIVE,
            ),
            (
                "Composite wing spar fatigue under repeated survey loading",
                "Where light composite spars fail when flown daily rather than now and then.",
                ProjectStatus.ACTIVE,
            ),
            (
                "Low-cost wind tunnel instrumentation for teaching laboratories",
                "Instrumenting a teaching tunnel to research standard without research budget.",
                ProjectStatus.PENDING_REVIEW,
            ),
        ],
        publications=[
            "Airframe sizing for agricultural survey over fragmented land holdings",
            "Fatigue behaviour of low-cost composite spars under repeated loading",
        ],
        openings=[
            ("Research assistant — flight testing", OpportunityType.RESEARCH_ASSISTANT, 20),
            ("Research internship — CFD meshing", OpportunityType.RESEARCH_INTERNSHIP, 45),
        ],
        facilities=[
            ("Subsonic Wind Tunnel Laboratory", ["Subsonic Wind Tunnel", "Six-Axis Force Balance"]),
            ("UAV Flight Test Field", ["Ground Control Station", "Telemetry Kit"]),
        ],
    ),
]

FUNDING = [
    ("Campus Sustainability Research Grant", "Internal Research Board", 6, 400000),
    ("Regional Language Technology Fund", "National Language Mission (fictional)", 21, 750000),
    ("Young Faculty Seed Grant", "Internal Research Board", 34, 250000),
    ("Industry Collaboration Fellowship", "Punjab Industry Council (fictional)", 52, 900000),
]


# --------------------------------------------------------------------- helpers


@dataclass
class Summary:
    schools: int = 0
    departments: int = 0
    users: int = 0
    skills: int = 0
    areas: int = 0
    projects: int = 0
    publications: int = 0
    opportunities: int = 0
    facilities: int = 0
    equipment: int = 0
    bookings: int = 0
    funding: int = 0
    collaborations: int = 0
    messages: int = 0
    applications: int = 0
    saved_items: int = 0
    notifications: int = 0
    reports: int = 0
    notes: list[str] = field(default_factory=list)


def password_for(full_name: str) -> str:
    """`Aryan Verma` → `Aryan123456`. A demonstration convenience only."""
    return f"{full_name.split()[0]}123456"


def _get_or_create_school(db: Session, name: str, summary: Summary) -> School:
    school = db.execute(select(School).where(School.name == name)).scalar_one_or_none()
    if school is None:
        school = School(name=name)
        db.add(school)
        db.flush()
        summary.schools += 1
    return school


def _get_or_create_department(
    db: Session, school: School, name: str, summary: Summary
) -> Department:
    department = db.execute(
        select(Department).where(Department.school_id == school.id, Department.name == name)
    ).scalar_one_or_none()
    if department is None:
        department = Department(school_id=school.id, name=name)
        db.add(department)
        db.flush()
        summary.departments += 1
    return department


def _get_or_create_user(
    db: Session,
    person: Person,
    role: UserRole,
    department: Department,
    summary: Summary,
    *,
    scope: Department | None = None,
) -> User:
    user = db.execute(
        select(User).where(User.registration_number == person.number)
    ).scalar_one_or_none()
    if user is None:
        user = User(
            registration_number=person.number,
            full_name=person.name,
            email=f"{person.name.split()[0].lower()}.{person.number}@example.edu",
            role=role,
            department_id=department.id,
            password_hash=hash_password(password_for(person.name)),
            # Presentable means usable: nobody wants to change eight passwords
            # in front of an audience.
            must_change_password=False,
            is_active=True,
            is_demo=True,
        )
        db.add(user)
        summary.users += 1
    else:
        user.full_name = person.name
        user.role = role
        user.department_id = department.id
        user.is_active = True
        user.must_change_password = False
        user.password_hash = hash_password(password_for(person.name))
    if role is UserRole.RESEARCH_COORDINATOR:
        # A coordinator with no scope oversees nothing: empty queues and 403s.
        user.coordinator_scope_type = CoordinatorScopeType.DEPARTMENT
        user.coordinator_scope_id = (scope or department).id
    db.flush()
    return user


def _get_or_create_skill(db: Session, name: str, summary: Summary) -> Skill:
    skill = db.execute(select(Skill).where(Skill.name == name)).scalar_one_or_none()
    if skill is None:
        skill = Skill(name=name)
        db.add(skill)
        db.flush()
        summary.skills += 1
    return skill


def _get_or_create_area(db: Session, name: str, summary: Summary) -> ResearchArea:
    area = db.execute(select(ResearchArea).where(ResearchArea.name == name)).scalar_one_or_none()
    if area is None:
        area = ResearchArea(name=name)
        db.add(area)
        db.flush()
        summary.areas += 1
    return area


def _attach_expertise(
    db: Session, user: User, skills: list[Skill], areas: list[ResearchArea]
) -> None:
    """Profiles without expertise make the directory and recommendations look
    broken, so everybody gets some."""
    for index, skill in enumerate(skills):
        has_skill = db.execute(
            select(UserSkill).where(UserSkill.user_id == user.id, UserSkill.skill_id == skill.id)
        ).scalar_one_or_none()
        if has_skill is None:
            db.add(UserSkill(user_id=user.id, skill_id=skill.id, proficiency=3 + (index % 3)))
    for index, area in enumerate(areas):
        has_area = db.execute(
            select(UserResearchArea).where(
                UserResearchArea.user_id == user.id,
                UserResearchArea.research_area_id == area.id,
            )
        ).scalar_one_or_none()
        if has_area is None:
            db.add(
                UserResearchArea(user_id=user.id, research_area_id=area.id, is_expertise=index == 0)
            )
    db.flush()


DESIGNATIONS = ["Professor", "Associate Professor", "Assistant Professor"]
PROGRAMMES = ["B.Tech", "M.Tech", "MBA", "B.Arch", "M.Arch", "Ph.D"]


def _seed_school(db: Session, plan: SchoolPlan, admin: User | None, summary: Summary) -> None:
    school = _get_or_create_school(db, plan.name, summary)
    departments = [_get_or_create_department(db, school, n, summary) for n in plan.departments]
    primary = departments[0]

    skills = [_get_or_create_skill(db, n, summary) for n in plan.skills]
    areas = [_get_or_create_area(db, n, summary) for n in plan.areas]

    coordinator = _get_or_create_user(
        db, plan.coordinator, UserRole.RESEARCH_COORDINATOR, primary, summary, scope=primary
    )
    _attach_expertise(db, coordinator, skills[:3], areas[:2])
    _ensure_researcher_profile(db, coordinator, "Professor", verified_by=coordinator)

    faculty: list[User] = []
    for index, person in enumerate(plan.faculty):
        department = departments[index % len(departments)]
        member = _get_or_create_user(db, person, UserRole.FACULTY, department, summary)
        _attach_expertise(db, member, skills[index : index + 4] or skills[:4], areas[: index + 2])
        _ensure_researcher_profile(
            db, member, DESIGNATIONS[index % len(DESIGNATIONS)], verified_by=coordinator
        )
        faculty.append(member)

    students: list[User] = []
    for index, person in enumerate(plan.students):
        department = departments[index % len(departments)]
        student = _get_or_create_user(db, person, UserRole.STUDENT, department, summary)
        _attach_expertise(db, student, skills[index % 4 : index % 4 + 3], areas[: 1 + index % 2])
        # Most students opt in so the directory has depth; a few do not, so the
        # opt-in rule can be demonstrated rather than asserted.
        _ensure_student_profile(db, student, PROGRAMMES[index % len(PROGRAMMES)], index % 4 != 3)
        students.append(student)

    _seed_projects(db, plan, primary, faculty, students, coordinator, skills, areas, summary)
    _seed_publications(db, plan, faculty, summary)
    _seed_opportunities(db, plan, primary, faculty, summary)
    _seed_facilities(db, plan, primary, coordinator, students, summary)
    _seed_conversations(db, faculty, students, summary)


def _ensure_researcher_profile(
    db: Session, user: User, designation: str, *, verified_by: User
) -> None:
    profile = db.get(ResearcherProfile, user.id)
    bio = (
        f"{designation} in {user.full_name.split()[-1]}'s department. Works with students on "
        "applied problems and supervises undergraduate research."
    )
    if profile is None:
        db.add(
            ResearcherProfile(
                user_id=user.id,
                designation=designation,
                bio=bio,
                availability=ResearcherAvailability.AVAILABLE,
                verification_status=VerificationStatus.VERIFIED,
                verified_by=verified_by.id,
                verified_at=NOW,
            )
        )
    else:
        profile.designation = designation
        profile.bio = profile.bio or bio
        profile.verification_status = VerificationStatus.VERIFIED
        profile.verified_by = verified_by.id
        profile.verified_at = profile.verified_at or NOW
    db.flush()


def _ensure_student_profile(db: Session, user: User, programme: str, discoverable: bool) -> None:
    profile = db.get(StudentProfile, user.id)
    if profile is None:
        db.add(
            StudentProfile(
                user_id=user.id,
                program=programme,
                year=2 + (hash(user.registration_number) % 3),
                bio="Looking for research work alongside coursework.",
                is_discoverable=discoverable,
            )
        )
    else:
        profile.program = programme
        profile.is_discoverable = discoverable
    db.flush()


def _seed_projects(
    db: Session,
    plan: SchoolPlan,
    department: Department,
    faculty: list[User],
    students: list[User],
    coordinator: User,
    skills: list[Skill],
    areas: list[ResearchArea],
    summary: Summary,
) -> None:
    for index, (title, blurb, status) in enumerate(plan.projects):
        existing = db.execute(select(Project).where(Project.title == title)).scalar_one_or_none()
        if existing is not None:
            continue
        owner = faculty[index % len(faculty)]
        reviewed = status in {ProjectStatus.ACTIVE, ProjectStatus.COMPLETED, ProjectStatus.ARCHIVED}
        project = Project(
            title=title,
            summary=blurb,
            description=(
                f"{blurb} The work is carried out in the {department.name} department with "
                "undergraduate and postgraduate students contributing to data collection, "
                "analysis and write-up."
            ),
            objectives="Produce a working prototype, a dataset others can reuse, and one paper.",
            owner_id=owner.id,
            department_id=department.id,
            status=status,
            start_date=TODAY - timedelta(days=90 + index * 30),
            end_date=TODAY + timedelta(days=180) if status is ProjectStatus.ACTIVE else None,
            reviewed_by=coordinator.id if reviewed else None,
            reviewed_at=NOW if reviewed else None,
        )
        db.add(project)
        db.flush()
        summary.projects += 1

        # A team, so the project page is not one name and an empty list.
        for offset in range(2):
            student = students[(index + offset) % len(students)]
            already = db.execute(
                select(ProjectMember).where(
                    ProjectMember.project_id == project.id,
                    ProjectMember.user_id == student.id,
                )
            ).scalar_one_or_none()
            if already is None:
                db.add(
                    ProjectMember(
                        project_id=project.id,
                        user_id=student.id,
                        member_role="Research assistant",
                    )
                )
        db.flush()


def _seed_publications(
    db: Session, plan: SchoolPlan, faculty: list[User], summary: Summary
) -> None:

    for index, title in enumerate(plan.publications):
        existing = db.execute(
            select(Publication).where(Publication.title == title)
        ).scalar_one_or_none()
        if existing is not None:
            continue
        author = faculty[index % len(faculty)]
        publication = Publication(
            title=title,
            pub_type=PublicationType.JOURNAL_ARTICLE,
            venue="Journal of Applied Research (fictional)",
            year=TODAY.year - (index % 3),
            abstract="Fictional record created for demonstration purposes.",
            created_by=author.id,
        )
        db.add(publication)
        db.flush()
        db.add(
            PublicationAuthor(
                publication_id=publication.id,
                user_id=author.id,
                author_order=1,
            )
        )
        if len(faculty) > 1:
            second = faculty[(index + 1) % len(faculty)]
            db.add(
                PublicationAuthor(
                    publication_id=publication.id,
                    user_id=second.id,
                    author_order=2,
                )
            )
        db.flush()
        summary.publications += 1


def _seed_opportunities(
    db: Session,
    plan: SchoolPlan,
    department: Department,
    faculty: list[User],
    summary: Summary,
) -> None:
    for index, (title, kind, days) in enumerate(plan.openings):
        existing = db.execute(
            select(Opportunity).where(Opportunity.title == title)
        ).scalar_one_or_none()
        if existing is not None:
            continue
        creator = faculty[index % len(faculty)]
        db.add(
            Opportunity(
                title=title,
                description=(
                    "Work alongside the research team on data collection and analysis. "
                    "Suitable for students who have completed the second year."
                ),
                opportunity_type=kind,
                created_by=creator.id,
                department_id=department.id,
                eligibility="Open to enrolled students in any year.",
                positions=1 + (index % 2),
                deadline=TODAY + timedelta(days=days),
                status=OpportunityStatus.OPEN,
            )
        )
        summary.opportunities += 1
    db.flush()


def _seed_facilities(
    db: Session,
    plan: SchoolPlan,
    department: Department,
    coordinator: User,
    students: list[User],
    summary: Summary,
) -> None:
    for facility_index, (facility_name, equipment_names) in enumerate(plan.facilities):
        facility = db.execute(
            select(Facility).where(
                Facility.name == facility_name, Facility.department_id == department.id
            )
        ).scalar_one_or_none()
        if facility is None:
            facility = Facility(
                name=facility_name,
                description=f"Shared facility of the {department.name} department.",
                department_id=department.id,
                location=f"Block {chr(65 + facility_index)}, {department.name}",
                contact=coordinator.email,
            )
            db.add(facility)
            db.flush()
            summary.facilities += 1

        for equipment_index, equipment_name in enumerate(equipment_names):
            equipment = db.execute(
                select(Equipment).where(
                    Equipment.facility_id == facility.id, Equipment.name == equipment_name
                )
            ).scalar_one_or_none()
            if equipment is None:
                equipment = Equipment(
                    facility_id=facility.id,
                    name=equipment_name,
                    description="Available to students with supervisor approval.",
                    max_hours=4,
                    students_allowed=True,
                )
                db.add(equipment)
                db.flush()
                summary.equipment += 1

            # A calendar with nothing on it says the feature is unused. One
            # approved booking and one still waiting, per equipment item.
            _ensure_booking(
                db,
                equipment,
                students[(facility_index + equipment_index) % len(students)],
                coordinator,
                days_ahead=2 + equipment_index,
                approved=True,
                summary=summary,
            )
            if equipment_index == 0:
                _ensure_booking(
                    db,
                    equipment,
                    students[(facility_index + 1) % len(students)],
                    coordinator,
                    days_ahead=5,
                    approved=False,
                    summary=summary,
                )


def _ensure_booking(
    db: Session,
    equipment: Equipment,
    user: User,
    coordinator: User,
    *,
    days_ahead: int,
    approved: bool,
    summary: Summary,
) -> None:
    start = datetime.combine(TODAY + timedelta(days=days_ahead), datetime.min.time(), tzinfo=UTC)
    start = start.replace(hour=10)
    end = start + timedelta(hours=2)
    clash = db.execute(
        select(Booking).where(Booking.equipment_id == equipment.id, Booking.user_id == user.id)
    ).scalar_one_or_none()
    if clash is not None:
        return
    db.add(
        Booking(
            equipment_id=equipment.id,
            user_id=user.id,
            period=Range(start, end, bounds="[)"),
            purpose="Measurements for an ongoing project.",
            status=BookingStatus.APPROVED if approved else BookingStatus.PENDING,
            decided_by=coordinator.id if approved else None,
            decided_at=NOW if approved else None,
        )
    )
    db.flush()
    summary.bookings += 1


def _seed_conversations(
    db: Session, faculty: list[User], students: list[User], summary: Summary
) -> None:
    """An accepted collaboration with something actually said in it.

    A thread with one line in it undersells the feature more than an empty one:
    it looks like nobody uses it.
    """
    if not faculty or not students:
        return
    supervisor, student = faculty[0], students[0]
    user_a, user_b = normalise_pair(supervisor.id, student.id)

    collaboration = db.execute(
        select(Collaboration).where(
            Collaboration.user_a_id == user_a, Collaboration.user_b_id == user_b
        )
    ).scalar_one_or_none()
    if collaboration is not None:
        return

    collaboration = Collaboration(
        user_a_id=user_a, user_b_id=user_b, state=CollaborationState.ACTIVE
    )
    db.add(collaboration)
    db.flush()
    db.add(
        CollaborationRequest(
            collaboration_id=collaboration.id,
            sender_id=student.id,
            recipient_id=supervisor.id,
            message="I read your paper and would like to help with the data collection.",
            status=CollaborationStatus.ACCEPTED,
            responded_at=NOW - timedelta(days=6),
        )
    )
    conversation = Conversation(collaboration_id=collaboration.id)
    db.add(conversation)
    db.flush()
    for person in (supervisor, student):
        db.add(ConversationParticipant(conversation_id=conversation.id, user_id=person.id))

    script = [
        (supervisor, "Glad to have you on this. Have you used the lab instruments before?"),
        (student, "Not the newer ones. I have worked with the older setup in the teaching lab."),
        (supervisor, "That is close enough. I will book you an induction slot this week."),
        (student, "Thank you. Should I read anything before then?"),
        (supervisor, "The methods section of the last paper is the fastest way in."),
    ]
    base = NOW - timedelta(days=5)
    for index, (sender, body) in enumerate(script):
        db.add(
            Message(
                conversation_id=conversation.id,
                sender_id=sender.id,
                body=body,
                created_at=base + timedelta(hours=index * 5),
            )
        )
        summary.messages += 1
    conversation.last_message_at = base + timedelta(hours=len(script) * 5)
    db.flush()
    summary.collaborations += 1


def _seed_funding(db: Session, owner: User, summary: Summary) -> None:
    for title, body, days, amount in FUNDING:
        existing = db.execute(
            select(FundingOpportunity).where(FundingOpportunity.title == title)
        ).scalar_one_or_none()
        if existing is not None:
            continue
        db.add(
            FundingOpportunity(
                title=title,
                organization=body,
                description="Fictional funding call created for demonstration purposes.",
                amount_text=f"Up to Rs {amount:,}",
                amount_max=amount,
                eligibility="Open to faculty and research students of the university.",
                deadline=TODAY + timedelta(days=days),
                is_demo=True,
            )
        )
        summary.funding += 1
    db.flush()


def seed(db: Session) -> Summary:
    summary = Summary()
    admin = (
        db.execute(select(User).where(User.role == UserRole.ADMIN, User.is_active.is_(True)))
        .scalars()
        .first()
    )

    for plan in PLAN:
        _seed_school(db, plan, admin, summary)

    # The screens that would otherwise be empty. A feature that works and
    # shows nothing reads as unfinished.
    _seed_applications(db, summary)
    _seed_saved_items(db, summary)
    _seed_moderation(db, summary)

    owner = (
        admin
        or db.execute(select(User).where(User.role == UserRole.RESEARCH_COORDINATOR))
        .scalars()
        .first()
    )
    if owner is not None:
        _seed_funding(db, owner, summary)
        _seed_notifications(db, summary)
    else:
        summary.notes.append("No administrator or coordinator found; funding calls skipped.")

    db.commit()
    return summary


def main() -> int:
    settings = get_settings()
    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)
    print(f"Seeding presentation data into {settings.database_summary()}")
    try:
        with session_factory() as db:
            summary = seed(db)
    finally:
        engine.dispose()

    print("\nCreated (existing rows left untouched):")
    print(f"  schools:        {summary.schools}")
    print(f"  departments:    {summary.departments}")
    print(f"  users:          {summary.users}")
    print(f"  skills:         {summary.skills}")
    print(f"  research areas: {summary.areas}")
    print(f"  projects:       {summary.projects}")
    print(f"  publications:   {summary.publications}")
    print(f"  opportunities:  {summary.opportunities}")
    print(f"  facilities:     {summary.facilities}")
    print(f"  equipment:      {summary.equipment}")
    print(f"  bookings:       {summary.bookings}")
    print(f"  funding calls:  {summary.funding}")
    print(f"  collaborations: {summary.collaborations}")
    print(f"  messages:       {summary.messages}")
    print(f"  applications:   {summary.applications}")
    print(f"  saved items:    {summary.saved_items}")
    print(f"  notifications:  {summary.notifications}")
    print(f"  open reports:   {summary.reports}")
    for note in summary.notes:
        print(f"  note: {note}")
    print("\nPasswords follow first-name + 123456 (Aryan Verma -> Aryan123456).")
    print("Demonstration convenience only. Fictional data throughout.")
    return 0


# --------------------------------------------------- the features that look empty
#
# A feature that works perfectly and shows an empty page reads as unfinished.
# These fill the screens that had nothing on them: applications at several
# stages, saved items, notifications, and one report waiting in the moderation
# queue. Everything below is still fictional and still idempotent.


def _seed_applications(db: Session, summary: Summary) -> None:
    """Applications across the openings, at different stages.

    The status timeline is the point of the applicant view, and a timeline
    with one entry does not show it.
    """
    from app.modules.applications.models import Application, ApplicationStatus

    openings = db.execute(select(Opportunity).order_by(Opportunity.title)).scalars().all()
    students = (
        db.execute(
            select(User)
            .where(User.role == UserRole.STUDENT, User.registration_number.like("124%"))
            .order_by(User.registration_number)
        )
        .scalars()
        .all()
    )
    if not openings or not students:
        return

    stages = [
        ApplicationStatus.SUBMITTED,
        ApplicationStatus.UNDER_REVIEW,
        ApplicationStatus.SHORTLISTED,
        ApplicationStatus.ACCEPTED,
        ApplicationStatus.REJECTED,
    ]
    statements = [
        "I have taken the relevant coursework and would like to work on the data collection.",
        "I have been part of a similar project last semester and can start immediately.",
        "I am interested in the methods side and would like to learn the analysis pipeline.",
    ]

    for index, opening in enumerate(openings):
        for offset in range(2):
            applicant = students[(index * 2 + offset) % len(students)]
            existing = db.execute(
                select(Application).where(
                    Application.opportunity_id == opening.id,
                    Application.applicant_id == applicant.id,
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue
            status = stages[(index + offset) % len(stages)]
            decided = status in {ApplicationStatus.ACCEPTED, ApplicationStatus.REJECTED}
            db.add(
                Application(
                    opportunity_id=opening.id,
                    applicant_id=applicant.id,
                    statement=statements[(index + offset) % len(statements)],
                    status=status,
                    decided_by=opening.created_by if decided else None,
                    decided_at=NOW - timedelta(days=1) if decided else None,
                    note="Strong fit for the fieldwork." if decided else None,
                )
            )
            summary.applications += 1
    db.flush()


def _seed_saved_items(db: Session, summary: Summary) -> None:
    """Bookmarks, so /me/saved is not an empty page during a demonstration."""
    from app.modules.profiles.models import SavedItem

    students = (
        db.execute(
            select(User)
            .where(User.role == UserRole.STUDENT, User.registration_number.like("124%"))
            .order_by(User.registration_number)
        )
        .scalars()
        .all()
    )
    projects = (
        db.execute(select(Project).where(Project.status == ProjectStatus.ACTIVE)).scalars().all()
    )
    openings = db.execute(select(Opportunity)).scalars().all()
    funding = db.execute(select(FundingOpportunity)).scalars().all()
    researchers = db.execute(select(User).where(User.role == UserRole.FACULTY)).scalars().all()
    if not students:
        return

    def save(user: User, **target: uuid.UUID) -> None:
        column, value = next(iter(target.items()))
        exists = db.execute(
            select(SavedItem).where(
                SavedItem.user_id == user.id,
                getattr(SavedItem, column) == value,
            )
        ).scalar_one_or_none()
        if exists is None:
            db.add(SavedItem(user_id=user.id, **target))
            summary.saved_items += 1

    for index, student in enumerate(students[:8]):
        if projects:
            save(student, project_id=projects[index % len(projects)].id)
        if openings:
            save(student, opportunity_id=openings[index % len(openings)].id)
        if researchers:
            save(student, researcher_id=researchers[index % len(researchers)].id)
        if funding:
            save(student, funding_id=funding[index % len(funding)].id)
    db.flush()


def _seed_notifications(db: Session, summary: Summary) -> None:
    """A populated bell. Written directly rather than through the event bus,
    because these describe things that already happened in the seed."""
    from app.modules.notifications.models import Notification, NotificationType

    people = (
        db.execute(
            select(User)
            .where(User.registration_number.like("124%"), User.role != UserRole.ADMIN)
            .order_by(User.registration_number)
        )
        .scalars()
        .all()
    )
    funding = (
        db.execute(select(FundingOpportunity).order_by(FundingOpportunity.deadline))
        .scalars()
        .first()
    )
    openings = db.execute(select(Opportunity).order_by(Opportunity.deadline)).scalars().all()
    if not people or not openings:
        return

    for index, person in enumerate(people[:14]):
        opening = openings[index % len(openings)]
        entries: list[tuple[NotificationType, dict[str, object], str]] = [
            (
                NotificationType.RELEVANT_OPPORTUNITY,
                {
                    "opportunity_id": str(opening.id),
                    "opportunity_title": opening.title,
                    "reasons": ["Matches your declared skills"],
                },
                f"opportunity:{opening.id}",
            )
        ]
        if funding is not None and index % 3 == 0:
            entries.append(
                (
                    NotificationType.DEADLINE_REMINDER,
                    {
                        "kind": "funding",
                        "item_id": str(funding.id),
                        "title": funding.title,
                        "days_left": max((funding.deadline - TODAY).days, 1),
                    },
                    f"funding:{funding.id}:7",
                )
            )
        for kind, payload, key in entries:
            exists = db.execute(
                select(Notification).where(
                    Notification.user_id == person.id, Notification.dedupe_key == key
                )
            ).scalar_one_or_none()
            if exists is None:
                db.add(
                    Notification(
                        user_id=person.id,
                        notification_type=kind,
                        payload=payload,
                        dedupe_key=key,
                    )
                )
                summary.notifications += 1
    db.flush()


def _seed_moderation(db: Session, summary: Summary) -> None:
    """One open report, so the moderation queue has something to decide."""
    from app.modules.reports.models import ContentReport, ReportStatus, ReportTargetType

    project = (
        db.execute(
            select(Project).where(Project.status == ProjectStatus.ACTIVE).order_by(Project.title)
        )
        .scalars()
        .first()
    )
    reporter = (
        db.execute(
            select(User).where(User.role == UserRole.STUDENT, User.registration_number.like("124%"))
        )
        .scalars()
        .first()
    )
    if project is None or reporter is None:
        return
    exists = db.execute(
        select(ContentReport).where(
            ContentReport.reporter_id == reporter.id, ContentReport.target_id == project.id
        )
    ).scalar_one_or_none()
    if exists is not None:
        return
    db.add(
        ContentReport(
            reporter_id=reporter.id,
            target_type=ReportTargetType.PROJECT,
            target_id=project.id,
            reason=(
                "The summary claims results that are not in the linked publication. "
                "Please check before this is shown to applicants."
            ),
            status=ReportStatus.OPEN,
        )
    )
    summary.reports += 1
    db.flush()


if __name__ == "__main__":
    sys.exit(main())

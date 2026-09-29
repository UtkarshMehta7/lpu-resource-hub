"""Measure expertise-search latency against a realistically sized directory.

    TEST_DATABASE_URL=... python scripts/benchmark_search.py --records 5000

The specification asks that expertise search "returns relevant researchers
across departments in under 1 second". That is a claim about latency, so it
needs measuring rather than asserting.

**Latency here means request received to response returned** -- the search is
driven through the ASGI application, so the number includes routing,
authorisation, the query, tag loading and JSON serialisation. Timing the SQL
alone would flatter the result by leaving out most of what a user waits for.

It writes to the **test** database by default, never the development or
production one, and every row it creates is removable with --cleanup.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.db.model_registry  # noqa: F401,E402  - registers every table
from app.core.config import Settings, get_settings  # noqa: E402
from app.core.rate_limit import RateLimiter  # noqa: E402
from app.core.security import create_access_token, hash_password  # noqa: E402
from app.main import create_app  # noqa: E402
from app.modules.admin.models import Department, School  # noqa: E402
from app.modules.profiles.models import (  # noqa: E402
    ResearcherProfile,
    UserResearchArea,
    UserSkill,
    VerificationStatus,
)
from app.modules.taxonomy.models import ResearchArea, Skill  # noqa: E402
from app.modules.users.models import User, UserRole  # noqa: E402

#: Benchmark rows are marked so --cleanup can find every one of them.
PREFIX = "BENCH"

SKILL_WORDS = (
    "Machine Learning",
    "Deep Learning",
    "Computer Vision",
    "Natural Language Processing",
    "Robotics",
    "Soil Science",
    "Remote Sensing",
    "Hydrology",
    "Structural Engineering",
    "Thermodynamics",
    "Quantum Computing",
    "Cryptography",
    "Data Mining",
    "Bioinformatics",
    "Pharmacology",
    "Organic Chemistry",
    "Materials Science",
    "Renewable Energy",
    "Signal Processing",
    "Control Systems",
    "Epidemiology",
    "Genomics",
    "Astrophysics",
    "Number Theory",
    "Optimisation",
    "Graph Theory",
    "Distributed Systems",
    "Databases",
)
AREA_WORDS = (
    "Artificial Intelligence",
    "Sustainable Agriculture",
    "Climate Modelling",
    "Public Health",
    "Smart Cities",
    "Energy Storage",
    "Precision Medicine",
    "Water Resources",
    "Advanced Manufacturing",
    "Computational Biology",
)
GIVEN = (
    "Aarav",
    "Diya",
    "Kabir",
    "Meera",
    "Rohan",
    "Ananya",
    "Vikram",
    "Priya",
    "Arjun",
    "Ishita",
    "Karan",
    "Neha",
    "Rahul",
    "Sneha",
    "Manish",
    "Kavya",
)
FAMILY = (
    "Sharma",
    "Verma",
    "Gupta",
    "Singh",
    "Mehta",
    "Chopra",
    "Bansal",
    "Arora",
    "Joshi",
    "Khanna",
    "Mittal",
    "Pandey",
    "Rana",
    "Saini",
    "Thakur",
    "Yadav",
)

#: The queries the criterion is really about, plus the shapes that stress it.
QUERIES: tuple[tuple[str, dict[str, object]], ...] = (
    ("single common term", {"q": "machine"}),
    ("multi-word phrase", {"q": "machine learning"}),
    ("cross-department, broad", {"q": "engineering"}),
    ("rare term", {"q": "astrophysics"}),
    ("two terms, few hits", {"q": "quantum cryptography"}),
    ("filtered by skill", {"q": "learning", "verified_only": True}),
    ("deep pagination", {"q": "machine", "page": 5}),
    ("no query, first page", {}),
    ("registration-number prefix", {"q": f"{PREFIX}0001"}),
)


@dataclass(frozen=True, slots=True)
class Timing:
    label: str
    samples: list[float]
    results: int

    def percentile(self, fraction: float) -> float:
        ordered = sorted(self.samples)
        index = min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))
        return ordered[index]

    @property
    def p50(self) -> float:
        return statistics.median(self.samples)


def _settings() -> Settings:
    url = os.environ.get("BENCHMARK_DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")
    if not url:
        raise SystemExit("Set TEST_DATABASE_URL (or BENCHMARK_DATABASE_URL) first.")
    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    return get_settings()


def seed(db: Session, count: int) -> None:
    """Create `count` researchers spread across departments, skills and areas."""
    existing = db.scalar(
        select(func.count()).select_from(User).where(User.registration_number.like(f"{PREFIX}%"))
    )
    if existing:
        print(f"  {existing} benchmark researchers already present; reusing them.")
        return

    school = db.scalar(select(School).limit(1))
    if school is None:
        school = School(name="Benchmark School")
        db.add(school)
        db.flush()
    departments = list(db.scalars(select(Department)).all())
    if len(departments) < 8:
        for index in range(8 - len(departments)):
            department = Department(school_id=school.id, name=f"Benchmark Department {index}")
            db.add(department)
            departments.append(department)
        db.flush()

    skills = {s.name: s for s in db.scalars(select(Skill)).all()}
    for name in SKILL_WORDS:
        if name not in skills:
            skill = Skill(name=name)
            db.add(skill)
            skills[name] = skill
    areas = {a.name: a for a in db.scalars(select(ResearchArea)).all()}
    for name in AREA_WORDS:
        if name not in areas:
            area = ResearchArea(name=name)
            db.add(area)
            areas[name] = area
    db.flush()

    skill_list = [skills[name] for name in SKILL_WORDS]
    area_list = [areas[name] for name in AREA_WORDS]
    password = hash_password("benchmark-password-123")

    print(f"  inserting {count} researchers…")
    for index in range(count):
        given = GIVEN[index % len(GIVEN)]
        family = FAMILY[(index // len(GIVEN)) % len(FAMILY)]
        department = departments[index % len(departments)]
        user = User(
            registration_number=f"{PREFIX}{index:05d}",
            email=f"bench{index:05d}@example.com",
            password_hash=password,
            full_name=f"{given} {family}",
            role=UserRole.FACULTY,
            is_active=True,
            is_demo=True,
            department_id=department.id,
        )
        db.add(user)
        db.flush()
        db.add(
            ResearcherProfile(
                user_id=user.id,
                designation="Professor" if index % 3 else "Associate Professor",
                bio=(
                    f"Works on {skill_list[index % len(skill_list)].name.lower()} "
                    f"and {area_list[index % len(area_list)].name.lower()}."
                ),
                verification_status=(
                    VerificationStatus.VERIFIED if index % 4 else VerificationStatus.PENDING
                ),
            )
        )
        # Three skills and two areas each, rotated so terms are spread rather
        # than clustered -- a directory where everybody shares one skill would
        # not exercise the index.
        for offset in range(3):
            db.add(
                UserSkill(
                    user_id=user.id,
                    skill_id=skill_list[(index + offset * 7) % len(skill_list)].id,
                    proficiency=(index % 5) + 1,
                )
            )
        for offset in range(2):
            db.add(
                UserResearchArea(
                    user_id=user.id,
                    research_area_id=area_list[(index + offset * 3) % len(area_list)].id,
                    is_expertise=offset == 0,
                )
            )
        if index % 500 == 499:
            db.flush()
            print(f"    {index + 1}…")
    db.commit()

    print("  building search documents…")
    db.execute(
        text("""
        UPDATE researcher_profiles AS rp
        SET search_document =
               setweight(to_tsvector('english', coalesce(u.full_name, '')), 'A')
            || setweight(to_tsvector('english',
                   coalesce(rp.designation, '') || ' '
                || coalesce((SELECT string_agg(s.name, ' ')
                               FROM user_skills us
                               JOIN skills s ON s.id = us.skill_id
                              WHERE us.user_id = rp.user_id), '') || ' '
                || coalesce((SELECT string_agg(ra.name, ' ')
                               FROM user_research_areas ura
                               JOIN research_areas ra ON ra.id = ura.research_area_id
                              WHERE ura.user_id = rp.user_id), '')
               ), 'B')
            || setweight(to_tsvector('english', coalesce(rp.bio, '')), 'C')
        FROM users u
        WHERE u.id = rp.user_id
    """)
    )
    db.execute(text("ANALYZE researcher_profiles"))
    db.execute(text("ANALYZE users"))
    db.commit()


def cleanup(db: Session) -> int:
    removed = db.execute(
        text("DELETE FROM users WHERE registration_number LIKE :p"), {"p": f"{PREFIX}%"}
    ).rowcount
    db.commit()
    return int(removed)


def explain(db: Session, query: str) -> str:
    rows = db.execute(
        text("""
        EXPLAIN (ANALYZE, BUFFERS)
        SELECT rp.user_id
          FROM researcher_profiles rp
          JOIN users u ON u.id = rp.user_id
         WHERE rp.search_document @@ websearch_to_tsquery('english', :q)
         ORDER BY ts_rank(rp.search_document, websearch_to_tsquery('english', :q)) DESC
         LIMIT 20
    """),
        {"q": query},
    ).all()
    return "\n".join(row[0] for row in rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=int, default=5000)
    parser.add_argument("--repeats", type=int, default=30, help="samples per query")
    parser.add_argument("--cleanup", action="store_true", help="remove benchmark rows and exit")
    args = parser.parse_args()

    settings = _settings()
    engine = create_engine(str(settings.database_url))
    factory = sessionmaker(bind=engine)

    if args.cleanup:
        with factory() as db:
            print(f"Removed {cleanup(db)} benchmark rows.")
        engine.dispose()
        return 0

    with factory() as db:
        seed(db, args.records)
        total = db.scalar(select(func.count()).select_from(ResearcherProfile))
        viewer = db.scalar(select(User).where(User.role == UserRole.ADMIN).limit(1))
        if viewer is None:
            viewer = User(
                registration_number=f"{PREFIX}ADMIN",
                email="benchadmin@example.com",
                password_hash=hash_password("benchmark-password-123"),
                full_name="Benchmark Admin",
                role=UserRole.ADMIN,
                is_active=True,
                is_demo=True,
            )
            db.add(viewer)
            db.commit()
        token = create_access_token(viewer.id, viewer.role.value, settings)
        plan = explain(db, "machine learning")

    print(f"\nDirectory size: {total} researcher profiles")
    print(f"Samples per query: {args.repeats}\n")

    timings: list[Timing] = []
    application = create_app(settings)
    # The search endpoint is rate-limited to 60 requests a minute per IP. A
    # benchmark fires hundreds, so without this every sample after the first
    # minute measures how fast the limiter says no -- which looks like a very
    # fast search and is worthless. Swapped out explicitly: we are measuring
    # search, and the limiter has its own tests.
    application.state.search_rate_limiter = RateLimiter(
        max_requests=10_000_000, window_seconds=60.0
    )
    with TestClient(application) as client:
        headers = {"Authorization": f"Bearer {token}", "X-Requested-With": "XMLHttpRequest"}
        for label, params in QUERIES:
            # Warm once so the first sample is not paying for a cold plan.
            client.get("/api/v1/researchers", headers=headers, params=params)
            samples: list[float] = []
            results = 0
            for _ in range(args.repeats):
                started = time.perf_counter()
                response = client.get("/api/v1/researchers", headers=headers, params=params)
                samples.append((time.perf_counter() - started) * 1000)
                if response.status_code != 200:
                    raise SystemExit(
                        f"{label!r} returned {response.status_code}; the sample would "
                        "measure the error path rather than the search."
                    )
                results = len(response.json().get("items", []))
            timings.append(Timing(label=label, samples=samples, results=results))

    print(f"{'Query':<30}{'hits':>6}{'p50':>9}{'p95':>9}{'p99':>9}{'max':>9}")
    print("-" * 72)
    worst_p95 = 0.0
    for timing in timings:
        p95 = timing.percentile(0.95)
        worst_p95 = max(worst_p95, p95)
        print(
            f"{timing.label:<30}{timing.results:>6}{timing.p50:>8.1f}ms"
            f"{p95:>8.1f}ms{timing.percentile(0.99):>8.1f}ms{max(timing.samples):>8.1f}ms"
        )
    print("-" * 72)
    print(f"Worst p95 across all queries: {worst_p95:.1f} ms   target < 1000 ms")
    print(f"Status: {'PASS' if worst_p95 < 1000 else 'FAIL'}\n")
    print("Query plan for 'machine learning':\n")
    print(plan)

    engine.dispose()
    return 0 if worst_p95 < 1000 else 1


if __name__ == "__main__":
    raise SystemExit(main())

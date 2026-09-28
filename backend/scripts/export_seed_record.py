"""Write an XLSX record of the demo data in a database.

Run after seeding, so there is a durable record of exactly what was created,
in what department, by whom, and when -- the sort of thing that is obvious on
the day and impossible to reconstruct six months later.

    DATABASE_URL=... python scripts/export_seed_record.py [-o record.xlsx]

Two deliberate omissions:

* **No passwords.** Every seeded account shares one password, and writing it
  into a file that gets emailed around would turn this record into a
  credential. It is reported once, on the terminal, by the seed script.
* **No real people.** Only rows the seed created (`users.is_demo`) are listed.
  Accounts somebody made by hand are counted so the totals reconcile, but
  their names and addresses are nobody's business.

The workbook also records what was deliberately NOT seeded: the publication
register and the ORCID/OpenAlex/Crossref import carry no fabricated data, so
that anything appearing there came from a genuine import against the real
APIs. Demonstrating a research tool with invented research would be worse
than demonstrating it empty.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.db.model_registry  # noqa: F401,E402  - registers every table
from app.core.config import get_settings  # noqa: E402
from app.modules.admin.models import Department, School  # noqa: E402
from app.modules.funding.models import FundingOpportunity  # noqa: E402
from app.modules.milestones.models import (  # noqa: E402
    Milestone,
    MilestoneDependency,
)
from app.modules.profiles.models import ResearcherProfile  # noqa: E402
from app.modules.projects.models import Project  # noqa: E402
from app.modules.publications.models import Publication  # noqa: E402
from app.modules.taxonomy.models import ResearchArea, Skill  # noqa: E402
from app.modules.users.models import User  # noqa: E402

FONT = "Arial"
HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(name=FONT, bold=True, color="FFFFFF", size=10)
BODY_FONT = Font(name=FONT, size=10)
TITLE_FONT = Font(name=FONT, bold=True, size=13)
NOTE_FONT = Font(name=FONT, italic=True, size=9, color="595959")


def _style_header(sheet: Worksheet, columns: list[str]) -> None:
    sheet.append(columns)
    for index in range(1, len(columns) + 1):
        cell = sheet.cell(row=1, column=index)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center")
    sheet.freeze_panes = "A2"


def _autosize(sheet: Worksheet, *, maximum: int = 52) -> None:
    for column in sheet.columns:
        cells = [c for c in column if c.value is not None]
        if not cells:
            continue
        longest = max(len(str(c.value)) for c in cells)
        letter = get_column_letter(cells[0].column)
        sheet.column_dimensions[letter].width = min(max(11, longest + 2), maximum)


def _write(sheet: Worksheet, columns: list[str], rows: list[list[Any]]) -> None:
    _style_header(sheet, columns)
    for row in rows:
        sheet.append(row)
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.font = BODY_FONT
    _autosize(sheet)


def _accounts(db: Session) -> list[list[Any]]:
    departments = {d.id: d.name for d in db.scalars(select(Department)).all()}
    names = {u.id: u.full_name for u in db.scalars(select(User)).all()}
    rows = []
    for user in db.scalars(
        select(User).where(User.is_demo.is_(True)).order_by(User.role, User.registration_number)
    ).all():
        rows.append(
            [
                user.registration_number,
                user.full_name,
                user.role.value,
                departments.get(user.department_id, "—") if user.department_id else "—",
                user.email or "—",
                names.get(user.created_by, "—") if user.created_by else "—",
                "yes" if user.is_active else "no",
                user.created_at.strftime("%Y-%m-%d %H:%M") if user.created_at else "—",
            ]
        )
    return rows


def _organisation(db: Session) -> list[list[Any]]:
    schools = {s.id: s.name for s in db.scalars(select(School)).all()}
    return [
        [schools.get(d.school_id, "—"), d.name]
        for d in db.scalars(select(Department).order_by(Department.name)).all()
    ]


def _projects(db: Session) -> list[list[Any]]:
    owners = {u.id: (u.full_name, u.registration_number) for u in db.scalars(select(User)).all()}
    departments = {d.id: d.name for d in db.scalars(select(Department)).all()}
    counts = dict(
        db.execute(select(Milestone.project_id, func.count()).group_by(Milestone.project_id)).all()
    )
    rows = []
    for project in db.scalars(select(Project).order_by(Project.title)).all():
        owner = owners.get(project.owner_id, ("—", "—"))
        rows.append(
            [
                project.title,
                project.status.value,
                owner[0],
                owner[1],
                departments.get(project.department_id, "—") if project.department_id else "—",
                project.start_date.isoformat() if project.start_date else "—",
                project.end_date.isoformat() if project.end_date else "—",
                counts.get(project.id, 0),
            ]
        )
    return rows


def _milestones(db: Session) -> list[list[Any]]:
    project_titles = {p.id: p.title for p in db.scalars(select(Project)).all()}
    titles = {m.id: m.title for m in db.scalars(select(Milestone)).all()}
    waits: dict[Any, list[str]] = {}
    for milestone_id, depends_on_id in db.execute(
        select(MilestoneDependency.milestone_id, MilestoneDependency.depends_on_id)
    ).all():
        waits.setdefault(milestone_id, []).append(titles.get(depends_on_id, "—"))

    today = datetime.now(UTC).date()
    rows = []
    for milestone in db.scalars(
        select(Milestone).order_by(Milestone.project_id, Milestone.position)
    ).all():
        days = (milestone.due_date - today).days
        rows.append(
            [
                project_titles.get(milestone.project_id, "—"),
                milestone.position,
                milestone.title,
                milestone.due_date.isoformat(),
                milestone.status.value,
                days,
                "; ".join(waits.get(milestone.id, [])) or "—",
            ]
        )
    return rows


def _summary_sheet(sheet: Worksheet, db: Session, database_label: str) -> None:
    sheet["A1"] = "LPU Research Intelligence & Collaboration Hub"
    sheet["A1"].font = TITLE_FONT
    sheet["A2"] = "Record of seeded demonstration data"
    sheet["A2"].font = Font(name=FONT, size=11)

    real_users = db.scalar(select(func.count()).select_from(User).where(User.is_demo.is_(False)))
    meta = [
        ("Generated (UTC)", datetime.now(UTC).strftime("%Y-%m-%d %H:%M")),
        ("Database", database_label),
        ("Accounts created by hand (left untouched)", real_users or 0),
    ]
    for offset, (label, value) in enumerate(meta, start=4):
        sheet.cell(row=offset, column=1, value=label).font = Font(name=FONT, bold=True, size=10)
        sheet.cell(row=offset, column=2, value=value).font = BODY_FONT

    sheet["A8"] = "What the seed created"
    sheet["A8"].font = Font(name=FONT, bold=True, size=11)

    # Counted with formulas rather than written as numbers, so the totals
    # still agree if somebody edits a sheet by hand.
    rows: list[tuple[str, str]] = [
        ("Demo accounts", "=COUNTA(Accounts!A:A)-1"),
        ("  of which administrators", '=COUNTIF(Accounts!C:C,"admin")'),
        ("  of which coordinators", '=COUNTIF(Accounts!C:C,"research_coordinator")'),
        ("  of which faculty", '=COUNTIF(Accounts!C:C,"faculty")'),
        ("  of which students", '=COUNTIF(Accounts!C:C,"student")'),
        ("Departments", "=COUNTA(Organisation!B:B)-1"),
        ("Projects", "=COUNTA(Projects!A:A)-1"),
        ("Milestones", "=COUNTA(Milestones!C:C)-1"),
        ("  overdue today", '=COUNTIF(Milestones!F:F,"<0")'),
        ("Skills", "=COUNTA(Taxonomy!A:A)-1"),
        ("Research areas", "=COUNTA(Taxonomy!B:B)-1"),
        ("Funding calls", "=COUNTA(Funding!A:A)-1"),
    ]
    sheet.cell(row=9, column=1, value="Item").font = HEADER_FONT
    sheet.cell(row=9, column=1).fill = HEADER_FILL
    sheet.cell(row=9, column=2, value="Count").font = HEADER_FONT
    sheet.cell(row=9, column=2).fill = HEADER_FILL
    for offset, (label, formula) in enumerate(rows, start=10):
        sheet.cell(row=offset, column=1, value=label).font = BODY_FONT
        sheet.cell(row=offset, column=2, value=formula).font = BODY_FONT

    note = sheet.cell(
        row=len(rows) + 12,
        column=1,
        value=(
            "Counts are formulas over the other sheets, so they stay correct if a "
            "sheet is edited. Passwords are deliberately not recorded here."
        ),
    )
    note.font = NOTE_FONT
    _autosize(sheet, maximum=58)


def _notes_sheet(sheet: Worksheet, db: Session) -> None:
    publications = db.scalar(select(func.count()).select_from(Publication)) or 0
    linked_orcids = (
        db.scalar(
            select(func.count())
            .select_from(ResearcherProfile)
            .where(ResearcherProfile.orcid_id.is_not(None))
        )
        or 0
    )

    sheet["A1"] = "What was deliberately NOT seeded"
    sheet["A1"].font = TITLE_FONT

    lines = [
        "",
        "The research-import features carry no fabricated data, by design.",
        "",
        "A tool whose point is to pull real publications from ORCID, OpenAlex,",
        "Crossref and Semantic Scholar would be misrepresented by demonstrating",
        "it with invented publications. Anything that appears in the publication",
        "register, or against a researcher's ORCID iD, therefore came from a",
        "genuine import against the live public APIs -- never from this seed.",
        "",
        "Verified at the time this record was written:",
    ]
    for offset, line in enumerate(lines, start=2):
        cell = sheet.cell(row=offset, column=1, value=line)
        cell.font = BODY_FONT

    start = len(lines) + 3
    checks = [
        ("Publications created by the seed", 0),
        ("Publications in the register (all genuinely imported)", publications),
        ("Researcher profiles with an ORCID iD linked", linked_orcids),
        ("ORCID iDs invented by the seed", 0),
    ]
    sheet.cell(row=start, column=1, value="Check").font = HEADER_FONT
    sheet.cell(row=start, column=1).fill = HEADER_FILL
    sheet.cell(row=start, column=2, value="Value").font = HEADER_FONT
    sheet.cell(row=start, column=2).fill = HEADER_FILL
    for offset, (label, value) in enumerate(checks, start=start + 1):
        sheet.cell(row=offset, column=1, value=label).font = BODY_FONT
        sheet.cell(row=offset, column=2, value=value).font = BODY_FONT

    tail = sheet.cell(
        row=start + len(checks) + 2,
        column=1,
        value=(
            "Source: scripts/seed_demo_data.py contains no reference to ORCID, "
            "publications, DOIs or imports. See docs/adr/0025."
        ),
    )
    tail.font = NOTE_FONT
    _autosize(sheet, maximum=72)


def build(db: Session, database_label: str) -> Workbook:
    workbook = Workbook()

    summary = workbook.active
    summary.title = "Summary"

    _write(
        workbook.create_sheet("Accounts"),
        [
            "Registration number",
            "Name",
            "Role",
            "Department",
            "Email",
            "Provisioned by",
            "Active",
            "Created (UTC)",
        ],
        _accounts(db),
    )
    _write(workbook.create_sheet("Organisation"), ["School", "Department"], _organisation(db))
    _write(
        workbook.create_sheet("Projects"),
        [
            "Project",
            "Status",
            "Owner",
            "Owner UID",
            "Department",
            "Starts",
            "Ends",
            "Milestones",
        ],
        _projects(db),
    )
    _write(
        workbook.create_sheet("Milestones"),
        ["Project", "#", "Milestone", "Due", "Status", "Days until due", "Waits on"],
        _milestones(db),
    )

    skills = [s.name for s in db.scalars(select(Skill).order_by(Skill.name)).all()]
    areas = [a.name for a in db.scalars(select(ResearchArea).order_by(ResearchArea.name)).all()]
    taxonomy = [
        [skills[i] if i < len(skills) else None, areas[i] if i < len(areas) else None]
        for i in range(max(len(skills), len(areas)))
    ]
    _write(workbook.create_sheet("Taxonomy"), ["Skill", "Research area"], taxonomy)

    _write(
        workbook.create_sheet("Funding"),
        ["Title", "Funder", "Status", "Deadline"],
        [
            [
                f.title,
                getattr(f, "funder", "—"),
                f.status.value,
                f.deadline.isoformat() if f.deadline else "—",
            ]
            for f in db.scalars(select(FundingOpportunity).order_by(FundingOpportunity.title)).all()
        ],
    )

    _notes_sheet(workbook.create_sheet("Notes"), db)
    _summary_sheet(summary, db, database_label)
    return workbook


def _database_label() -> str:
    """Host and database name only -- never the credentials."""
    settings = get_settings()
    url = settings.database_url
    # A PostgresDsn is a MultiHostUrl: it can carry several hosts, so there is
    # no `.host`. Take the first, and never touch username or password.
    hosts = url.hosts()
    host = (hosts[0].get("host") if hosts else None) or "unknown"
    name = (url.path or "/").lstrip("/")
    return f"{name} at {host}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--output",
        default="seed-record.xlsx",
        help="where to write the workbook (default: seed-record.xlsx)",
    )
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(str(settings.database_url))
    factory = sessionmaker(bind=engine)
    try:
        with factory() as db:
            workbook = build(db, _database_label())
    finally:
        engine.dispose()

    destination = Path(args.output).expanduser()
    workbook.save(destination)
    print(f"Wrote {destination}")
    print("Passwords are not recorded in this file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Rendering the institutional report to CSV and PDF.

Both renderers walk the same `InstitutionalReport` the API returns, so a
figure in the PDF is the figure in the CSV is the figure on the screen. There
is no second aggregation that could drift.

Each table carries its definition into the output. A number handed to somebody
without the rule that produced it invites the wrong reading, and a report is
exactly the artefact that outlives the conversation explaining it.
"""

from __future__ import annotations

import csv
import io

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.modules.analytics.institutional import InstitutionalReport

BRAND = colors.HexColor("#B74A09")
INK = colors.HexColor("#1F2933")
MUTED = colors.HexColor("#5C6670")
RULE = colors.HexColor("#D9DEE3")


def to_csv(report: InstitutionalReport) -> str:
    """One flat file: metadata, then every section and table in order.

    A blank line separates blocks and each block names itself, so the file is
    readable in a spreadsheet without a legend beside it.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    writer.writerow(["Institutional Research Report"])
    writer.writerow(["Academic year", report.academic_year])
    writer.writerow(["Period", report.period_start, report.period_end])
    writer.writerow(["Scope", report.scope])
    writer.writerow(["Generated", report.generated_at])
    writer.writerow([])

    for section in report.sections:
        writer.writerow(["Section", section.title])
        if section.summary:
            writer.writerow(["Measure", "Value"])
            for label, value in section.summary:
                writer.writerow([label, value])
            writer.writerow([])
        for table in section.tables:
            writer.writerow(["Table", table.title])
            if table.definition:
                writer.writerow(["Definition", table.definition])
            writer.writerow(list(table.columns))
            for row in table.rows:
                writer.writerow(list(row))
            writer.writerow([])
    return buffer.getvalue()


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=20,
            textColor=INK,
            spaceAfter=2 * mm,
            alignment=TA_LEFT,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            parent=base["Normal"],
            fontSize=10,
            textColor=MUTED,
            spaceAfter=6 * mm,
        ),
        "section": ParagraphStyle(
            "section",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            textColor=BRAND,
            spaceBefore=6 * mm,
            spaceAfter=2 * mm,
        ),
        "table": ParagraphStyle(
            "tabletitle",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=10,
            textColor=INK,
            spaceBefore=4 * mm,
            spaceAfter=1 * mm,
        ),
        "definition": ParagraphStyle(
            "definition",
            parent=base["Normal"],
            fontSize=7.5,
            textColor=MUTED,
            spaceAfter=1.5 * mm,
            leading=10,
        ),
        "note": ParagraphStyle(
            "note",
            parent=base["Normal"],
            fontSize=7.5,
            textColor=MUTED,
            leading=10,
        ),
    }


def _grid(data: list[list[str]], *, widths: list[float] | None = None) -> Table:
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
                ("FONT", (0, 1), (-1, -1), "Helvetica", 8),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, 0), (-1, 0), INK),
                ("TEXTCOLOR", (0, 1), (-1, -1), INK),
                ("LINEBELOW", (0, 1), (-1, -1), 0.25, RULE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ]
        )
    )
    return table


def to_pdf(report: InstitutionalReport) -> bytes:
    """Render to PDF with reportlab: pure Python, so it runs anywhere the API does."""
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Institutional Research Report {report.academic_year}",
        author="LPU Research Intelligence & Collaboration Hub",
    )
    style = _styles()
    story: list[object] = [
        Paragraph("Institutional Research Report", style["title"]),
        Paragraph(
            f"Lovely Professional University (LPU) &middot; academic year "
            f"{report.academic_year} &middot; {report.period_start} to "
            f"{report.period_end}<br/>Covering {report.scope}. Generated "
            f"{report.generated_at}.",
            style["subtitle"],
        ),
        Paragraph(
            "Every figure in this report is counted from the platform's own records at "
            "the moment it was generated. Nothing is estimated or carried forward. Each "
            "table states the rule it was produced under.",
            style["note"],
        ),
        Spacer(1, 4 * mm),
    ]

    usable = document.width
    for section in report.sections:
        story.append(Paragraph(section.title, style["section"]))
        if section.summary:
            story.append(
                _grid(
                    [["Measure", "Value"], *[[k, v] for k, v in section.summary]],
                    widths=[usable * 0.66, usable * 0.34],
                )
            )
        for table in section.tables:
            block: list[object] = [Paragraph(table.title, style["table"])]
            if table.definition:
                block.append(Paragraph(table.definition, style["definition"]))
            if table.rows:
                first = usable * (0.62 if len(table.columns) == 2 else 0.46)
                rest = (usable - first) / max(1, len(table.columns) - 1)
                block.append(
                    _grid(
                        [list(table.columns), *[list(r) for r in table.rows]],
                        widths=[first, *[rest] * (len(table.columns) - 1)],
                    )
                )
            else:
                block.append(Paragraph("No records in this period.", style["definition"]))
            # Keep a heading with at least the start of its table.
            story.append(KeepTogether(block))

    story.append(PageBreak())
    story.append(Paragraph("How to read this report", style["section"]))
    story.append(
        Paragraph(
            "<b>Academic year.</b> The year runs from the configured start month, so "
            f"{report.academic_year} means {report.period_start} to {report.period_end}. "
            "Figures spanning two calendar years are expected.<br/><br/>"
            "<b>Publications by department.</b> Credited to every department among a "
            "publication's linked authors, so departmental figures sum to more than the "
            "total. Authors held only as text carry no department.<br/><br/>"
            "<b>Cross-department collaboration rate.</b> cross / (cross + same). Pairs "
            "where either person has no department are excluded from both halves.<br/><br/>"
            "<b>Application success rate.</b> accepted / (accepted + rejected). Pending "
            "applications are not in the denominator; withdrawn ones are in neither "
            "half.<br/><br/>"
            "<b>Milestone risk.</b> Derived when the report ran, from each milestone's "
            "status, due date and dependencies. It describes the position today rather "
            "than the year as a whole.",
            style["note"],
        )
    )

    document.build(story)
    return buffer.getvalue()


__all__ = ["to_csv", "to_pdf"]

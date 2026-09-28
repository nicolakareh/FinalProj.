"""Demo project: a fictional fire-station renovation with three OAC meetings.

Every name, firm and town in the sample data is invented.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from ..extract import Extractor, MockExtractor
from ..formats import load_builtin_format
from ..models import Firm, Meeting, Project
from ..pipeline import finalize, generate_draft
from ..storage import Store

SAMPLES_DIR = Path(__file__).parent
DEMO_FIRM_NAME = "Harborline Project Management"
DEMO_PROJECT_NAME = "Bramford Fire Station Renovation & Addition"

DEMO_MEETINGS = [
    ("oac_meeting_01.txt", 1, date(2026, 9, 1)),
    ("oac_meeting_02.txt", 2, date(2026, 9, 8)),
    ("oac_meeting_03.txt", 3, date(2026, 9, 15)),
]

DEMO_ATTENDEES = """Dana Whitfield – Harborline Project Management – OPM
Tom Reilly – Town of Bramford – Owner, Facilities Director
Chief Laura Benson – Bramford Fire Department – Owner, Fire Chief
Maya Chen – Ridgeway Architects – Project Architect
Sam Okafor – Ridgeway Architects – Architect
Jorge Alvarez – Castellan Builders – GC Project Manager
Kelly Nguyen – Castellan Builders – GC Superintendent
Ravi Patel – NorthStar Cx – Commissioning Agent"""

DEMO_NOTES = """"The Town" and "the Owner" both mean the Town of Bramford.
Chris is Harborline's field representative and signs T&M tickets.
Station 1 is the project site; Station 2 is the Town's other fire station.
Merrimack Steel is the structural steel fabricator. DPW is the Town Department of Public Works.
Mike is the DPW Director. Cx = commissioning."""


def sample_transcript(filename: str) -> str:
    return (SAMPLES_DIR / filename).read_text(encoding="utf-8")


def make_demo_firm(name: str = DEMO_FIRM_NAME) -> Firm:
    return Firm(name=name, format=load_builtin_format("standard_opm"))


def make_demo_project(firm: Firm) -> Project:
    return Project(
        firm_id=firm.id,
        name=DEMO_PROJECT_NAME,
        number="24-118",
        location="Job trailer, 40 Hollis Street, Bramford, MA",
        owner="Town of Bramford",
        architect="Ridgeway Architects",
        contractor="Castellan Builders",
        opm_firm=firm.name,
        prepared_by="Dana Whitfield, " + firm.name,
        distribution="Attendees; Town Administrator; project file",
        meeting_time="9:00 AM",
        default_attendees=DEMO_ATTENDEES,
        extractor_notes=DEMO_NOTES,
    )


def load_demo_project(store: Store, output_dir: str | Path, *, extractor: Extractor | None = None, firm_name: str = DEMO_FIRM_NAME) -> tuple[Firm, Project, list[Meeting]]:
    """Create the demo firm and project and run all three meetings through the pipeline."""
    extractor = extractor or MockExtractor()
    firm = store.save_firm(make_demo_firm(firm_name))
    project = store.save_project(make_demo_project(firm))
    meetings: list[Meeting] = []
    for filename, meeting_no, meeting_date in DEMO_MEETINGS:
        draft = generate_draft(
            store, firm, project,
            transcript=sample_transcript(filename),
            extractor=extractor,
            meeting_no=meeting_no,
            meeting_date=meeting_date,
            source_name=filename,
            meeting_time="9:00 AM",
            location="Job trailer, Station 1",
        )
        meeting, _ = finalize(store, firm, project, draft.meeting, output_dir)
        meetings.append(meeting)
    return firm, project, meetings

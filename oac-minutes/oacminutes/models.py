"""Pydantic models shared by the engine, storage, extractor and renderers."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


def new_id() -> str:
    return uuid.uuid4().hex[:12]


class ItemStatus(str, Enum):
    OPEN = "open"
    ON_HOLD = "on_hold"
    CLOSED = "closed"


# --------------------------------------------------------------------------
# Firm format: how a firm wants its minutes and open-items log to look.
# --------------------------------------------------------------------------
class HeaderField(BaseModel):
    key: str = Field(description="One of: project_name, project_number, meeting_number, meeting_date, meeting_time, location, owner, architect, contractor, opm_firm, prepared_by, distribution")
    label: str


class SectionSpec(BaseModel):
    key: str
    title: str
    hint: str = Field(default="", description="What belongs in this section; shown to the extractor")


class NumberingSpec(BaseModel):
    style: Literal["meeting_item", "sequential"] = "meeting_item"
    separator: str = "."
    item_pad: int = 2
    prefix: str = ""


class ColumnSpec(BaseModel):
    key: Literal["item_number", "description", "section", "responsible", "date_raised", "due_date", "status", "notes", "last_update"]
    label: str
    width_in: float | None = None


class FirmFormat(BaseModel):
    name: str = "Standard OPM format"
    minutes_title: str = "OAC Meeting Minutes"
    header_fields: list[HeaderField] = Field(default_factory=list)
    sections: list[SectionSpec] = Field(default_factory=list)
    open_items_columns: list[ColumnSpec] = Field(default_factory=list)
    numbering: NumberingSpec = Field(default_factory=NumberingSpec)
    status_labels: dict[str, str] = Field(default_factory=lambda: {
        "open": "Open", "on_hold": "On Hold", "closed": "Closed",
        "overdue": "OVERDUE", "new": "New",
    })
    show_attendees_table: bool = True
    show_decisions: bool = True
    show_closed_items: bool = True
    show_item_history: bool = True
    not_discussed_text: str = "Not discussed – carried forward."
    disclaimer: str = (
        "These minutes represent the author's understanding of the items discussed "
        "and decisions reached. Any corrections or additions must be submitted in "
        "writing within five (5) business days of receipt; otherwise the minutes "
        "will stand as the record of the meeting."
    )
    date_format: str = "%m/%d/%Y"
    font_name: str = "Calibri"
    font_size: int = 10
    accent_color: str = "1F3864"

    def section_keys(self) -> list[str]:
        return [s.key for s in self.sections]

    def section_title(self, key: str) -> str:
        for s in self.sections:
            if s.key == key:
                return s.title
        return key.replace("_", " ").title()


class Firm(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    format: FirmFormat = Field(default_factory=FirmFormat)
    created_at: datetime = Field(default_factory=datetime.now)


# --------------------------------------------------------------------------
# Projects and meetings
# --------------------------------------------------------------------------
class Project(BaseModel):
    id: str = Field(default_factory=new_id)
    firm_id: str
    name: str
    number: str = ""
    location: str = ""
    owner: str = ""
    architect: str = ""
    contractor: str = ""
    opm_firm: str = ""
    prepared_by: str = ""
    distribution: str = ""
    meeting_time: str = ""
    default_attendees: str = Field(default="", description="One per line: Name – Company – Role")
    extractor_notes: str = Field(default="", description="Glossary and context for the extractor, e.g. who 'the Town' is")
    created_at: datetime = Field(default_factory=datetime.now)

    def header_value(self, key: str, meeting: "Meeting") -> str:
        mapping = {
            "project_name": self.name,
            "project_number": self.number,
            "meeting_number": str(meeting.meeting_no),
            "meeting_date": meeting.meeting_date.strftime("%m/%d/%Y"),
            "meeting_time": meeting.meeting_time or self.meeting_time,
            "location": meeting.location or self.location,
            "owner": self.owner,
            "architect": self.architect,
            "contractor": self.contractor,
            "opm_firm": self.opm_firm,
            "prepared_by": self.prepared_by,
            "distribution": self.distribution,
        }
        return mapping.get(key, "")


class MeetingStatus(str, Enum):
    DRAFT = "draft"
    FINAL = "final"


# --------------------------------------------------------------------------
# Extraction result: what the language model returns for one transcript.
# Kept flat and string-typed on purpose so it doubles as the JSON schema
# for structured output.
# --------------------------------------------------------------------------
class Attendee(BaseModel):
    name: str
    company: str = ""
    role: str = Field(default="", description="Owner, OPM, Architect, GC, Sub, Commissioning, etc.")
    present: bool = True


class SectionNotes(BaseModel):
    section_key: str = Field(description="Must be one of the firm's section keys")
    bullets: list[str] = Field(default_factory=list, description="Concise minute-style statements, past tense, one topic each")


class PriorItemUpdate(BaseModel):
    item_number: str = Field(description="Exactly as listed in the prior open items")
    status: Literal["open", "on_hold", "closed", "not_discussed"]
    note: str = Field(default="", description="What was said about this item at this meeting, minute style")
    new_due_date: Optional[str] = Field(default=None, description="ISO date YYYY-MM-DD if a new date was agreed")
    new_responsible: Optional[str] = Field(default=None, description="Only if responsibility changed")


class NewItem(BaseModel):
    description: str = Field(description="The action item, one or two sentences, starting with the deliverable")
    responsible: str = Field(default="", description="Party and person, e.g. 'GC – J. Alvarez'")
    due_date: Optional[str] = Field(default=None, description="ISO date YYYY-MM-DD if a date was agreed")
    section_key: str = Field(default="general", description="Firm section this item belongs under")
    priority: Literal["normal", "high"] = "normal"
    note: str = Field(default="", description="Context from the discussion worth keeping in the log")


class NextMeeting(BaseModel):
    date: Optional[str] = Field(default=None, description="ISO date YYYY-MM-DD")
    time: Optional[str] = None
    location: Optional[str] = None


class MeetingExtraction(BaseModel):
    attendees: list[Attendee] = Field(default_factory=list)
    sections: list[SectionNotes] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list, description="Decisions formally made at the meeting")
    prior_item_updates: list[PriorItemUpdate] = Field(default_factory=list, description="One entry per prior open item; use status not_discussed when it never came up")
    new_items: list[NewItem] = Field(default_factory=list)
    next_meeting: Optional[NextMeeting] = None
    review_flags: list[str] = Field(default_factory=list, description="Things the PM should verify before issuing: unclear owners, conflicting dates, inaudible passages")


class Meeting(BaseModel):
    id: str = Field(default_factory=new_id)
    project_id: str
    meeting_no: int
    meeting_date: date
    meeting_time: str = ""
    location: str = ""
    source_name: str = ""
    transcript: str = ""
    extraction: Optional[MeetingExtraction] = None
    status: MeetingStatus = MeetingStatus.DRAFT
    minutes_docx_path: Optional[str] = None
    items_log_xlsx_path: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    finalized_at: Optional[datetime] = None


# --------------------------------------------------------------------------
# Open items: the cross-meeting tracker rows.
# --------------------------------------------------------------------------
class ItemHistoryEntry(BaseModel):
    meeting_no: int
    date: date
    note: str
    status: ItemStatus


class OpenItem(BaseModel):
    id: str = Field(default_factory=new_id)
    project_id: str
    item_number: str
    description: str
    section_key: str = "general"
    responsible: str = ""
    date_raised: date
    raised_meeting_no: int
    due_date: Optional[date] = None
    status: ItemStatus = ItemStatus.OPEN
    closed_meeting_no: Optional[int] = None
    closed_date: Optional[date] = None
    last_discussed_meeting_no: int
    priority: Literal["normal", "high"] = "normal"
    history: list[ItemHistoryEntry] = Field(default_factory=list)

    def is_overdue(self, as_of: date) -> bool:
        return self.status == ItemStatus.OPEN and self.due_date is not None and self.due_date < as_of

    def latest_note(self) -> str:
        return self.history[-1].note if self.history else ""

    def meetings_open(self, current_meeting_no: int) -> int:
        """How many meetings this item has been carried (0 = raised this meeting)."""
        end = self.closed_meeting_no if self.closed_meeting_no is not None else current_meeting_no
        return max(0, end - self.raised_meeting_no)

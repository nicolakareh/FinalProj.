"""Shared presentation logic so DOCX, Markdown and XLSX agree on labels."""
from __future__ import annotations

import re
from datetime import date

from .carryforward import CarryForwardResult
from .dates import fmt_date
from .models import FirmFormat, ItemStatus, MeetingExtraction, OpenItem


def status_label(item: OpenItem, fmt: FirmFormat, *, meeting_no: int, as_of: date) -> str:
    labels = fmt.status_labels
    if item.status == ItemStatus.CLOSED:
        return labels.get("closed", "Closed")
    if item.is_overdue(as_of):
        return labels.get("overdue", "OVERDUE")
    if item.raised_meeting_no == meeting_no:
        return labels.get("new", "New")
    return labels.get(item.status.value, item.status.value.replace("_", " ").title())


def row_kind(item: OpenItem, *, meeting_no: int, as_of: date) -> str:
    """'closed' | 'overdue' | 'new' | 'not_discussed' | 'normal' — drives row styling."""
    if item.status == ItemStatus.CLOSED:
        return "closed"
    if item.is_overdue(as_of):
        return "overdue"
    if item.raised_meeting_no == meeting_no:
        return "new"
    if item.last_discussed_meeting_no < meeting_no:
        return "not_discussed"
    return "normal"


def latest_update_text(item: OpenItem, fmt: FirmFormat, *, meeting_no: int) -> str:
    if item.raised_meeting_no == meeting_no:
        note = item.latest_note()
        return "" if note == "Raised." else note
    if item.last_discussed_meeting_no < meeting_no and item.status != ItemStatus.CLOSED:
        return fmt.not_discussed_text
    return item.latest_note()


def history_lines(item: OpenItem, fmt: FirmFormat) -> list[str]:
    lines = []
    for entry in item.history:
        note = entry.note
        if note == "Not discussed – carried forward.":
            note = fmt.not_discussed_text
        lines.append(f"Mtg {entry.meeting_no} ({fmt_date(entry.date, fmt.date_format)}): {note}")
    return lines


def cell_text(item: OpenItem, key: str, fmt: FirmFormat, *, meeting_no: int, as_of: date) -> str:
    if key == "item_number":
        return item.item_number
    if key == "description":
        return item.description
    if key == "section":
        return fmt.section_title(item.section_key)
    if key == "responsible":
        return item.responsible
    if key == "date_raised":
        return fmt_date(item.date_raised, fmt.date_format)
    if key == "due_date":
        return fmt_date(item.due_date, fmt.date_format)
    if key == "status":
        return status_label(item, fmt, meeting_no=meeting_no, as_of=as_of)
    if key == "last_update":
        return latest_update_text(item, fmt, meeting_no=meeting_no)
    if key == "notes":
        return "\n".join(history_lines(item, fmt))
    return ""


def visible_items(result: CarryForwardResult, fmt: FirmFormat) -> list[OpenItem]:
    if fmt.show_closed_items:
        return list(result.active_items)
    return [i for i in result.active_items if i.status != ItemStatus.CLOSED]


def sections_with_content(extraction: MeetingExtraction | None, fmt: FirmFormat) -> list[tuple[str, list[str]]]:
    if extraction is None:
        return []
    by_key = {s.section_key: s.bullets for s in extraction.sections}
    ordered = [(s.title, by_key[s.key]) for s in fmt.sections if by_key.get(s.key)]
    known = set(fmt.section_keys())
    for key, bullets in by_key.items():
        if key not in known and bullets:
            ordered.append((fmt.section_title(key), bullets))
    return ordered


def slugify(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")
    return text[:60] or "project"


def output_basename(project_name: str, meeting_no: int, meeting_date: date) -> str:
    return f"{slugify(project_name)}_OAC-{meeting_no:02d}_{meeting_date.isoformat()}"

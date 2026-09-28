"""The open-items carry-forward engine.

This is deliberately plain, deterministic Python: the language model only
reports *what was said* about each numbered item; this module decides what
that means for the tracker. Nothing here calls the network.

Rules
-----
* Every prior open/on-hold item survives the meeting. If nobody mentioned it,
  it is carried forward with a "not discussed" note rather than silently
  dropped, which is the failure mode of generic note-takers.
* Items keep their number for life. Closed items appear once more in the
  minutes of the meeting that closed them, then drop off the tracker.
* Overdue is computed, never asserted by the model: open + due date before the
  as-of date.
* A closed item that comes up again is reopened, with the reopening logged.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Iterable

from pydantic import BaseModel, Field

from .dates import parse_date
from .models import (
    ItemHistoryEntry,
    ItemStatus,
    MeetingExtraction,
    NumberingSpec,
    OpenItem,
)


# --------------------------------------------------------------------------
# Item numbers
# --------------------------------------------------------------------------
def format_item_number(numbering: NumberingSpec, meeting_no: int, seq: int) -> str:
    if numbering.style == "sequential":
        return f"{numbering.prefix}{seq:0{numbering.item_pad}d}"
    return f"{numbering.prefix}{meeting_no}{numbering.separator}{seq:0{numbering.item_pad}d}"


def parse_item_number(value: str) -> tuple[int, int]:
    """Return a sort key (meeting, seq) for any reasonable item number string."""
    nums = [int(n) for n in re.findall(r"\d+", value or "")]
    if len(nums) >= 2:
        return nums[0], nums[1]
    if len(nums) == 1:
        return 0, nums[0]
    return 0, 0


def normalize_item_number(value: str) -> str:
    """Normalise user/model spelling so '3.4', '3.04', ' 3-04 ' all match '3.04'."""
    meeting, seq = parse_item_number(value)
    return f"{meeting}:{seq}"


def next_sequential_number(items: Iterable[OpenItem]) -> int:
    highest = 0
    for item in items:
        _, seq = parse_item_number(item.item_number)
        highest = max(highest, seq)
    return highest + 1


# --------------------------------------------------------------------------
# Result container
# --------------------------------------------------------------------------
class CarryForwardResult(BaseModel):
    items: list[OpenItem] = Field(default_factory=list, description="Every item in the project after this meeting")
    active_items: list[OpenItem] = Field(default_factory=list, description="Rows for this meeting's tracker: open, on hold, and closed this meeting")
    new_items: list[OpenItem] = Field(default_factory=list)
    closed_this_meeting: list[OpenItem] = Field(default_factory=list)
    reopened: list[OpenItem] = Field(default_factory=list)
    not_discussed: list[OpenItem] = Field(default_factory=list)
    overdue: list[OpenItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def by_number(self) -> dict[str, OpenItem]:
        return {i.item_number: i for i in self.items}


def _sorted(items: Iterable[OpenItem]) -> list[OpenItem]:
    return sorted(items, key=lambda i: parse_item_number(i.item_number))


def _word_set(text: str) -> set[str]:
    stop = {"the", "a", "an", "to", "of", "and", "for", "on", "in", "by", "with", "is", "be", "will", "at"}
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in stop and len(w) > 2}


def looks_like_duplicate(a: str, b: str, threshold: float = 0.6) -> bool:
    wa, wb = _word_set(a), _word_set(b)
    if not wa or not wb:
        return False
    return len(wa & wb) / len(wa | wb) >= threshold


# --------------------------------------------------------------------------
# The engine
# --------------------------------------------------------------------------
def carry_forward(
    items: list[OpenItem],
    extraction: MeetingExtraction,
    *,
    project_id: str,
    meeting_no: int,
    meeting_date: date,
    numbering: NumberingSpec | None = None,
) -> CarryForwardResult:
    """Apply one meeting's extraction to the project's items.

    ``items`` is the full item list as of the previous finalized meeting
    (open, on hold and closed). The input is not mutated.
    """
    numbering = numbering or NumberingSpec()
    result = CarryForwardResult()
    working: list[OpenItem] = [i.model_copy(deep=True) for i in items]
    by_key: dict[str, OpenItem] = {}
    for item in working:
        key = normalize_item_number(item.item_number)
        if key in by_key:
            result.warnings.append(f"Duplicate item number {item.item_number} in existing items; using the first one.")
            continue
        by_key[key] = item

    was_closed_before = {i.id for i in working if i.status == ItemStatus.CLOSED}
    touched: set[str] = set()

    # 1. Apply what the meeting said about prior items.
    for update in extraction.prior_item_updates:
        key = normalize_item_number(update.item_number)
        item = by_key.get(key)
        if item is None:
            result.warnings.append(f"Update refers to item {update.item_number!r}, which does not exist; ignored.")
            continue
        if update.status == "not_discussed":
            continue  # treated exactly like an untouched item below
        if item.id in touched:
            result.warnings.append(f"Item {item.item_number} was updated twice; keeping the first update.")
            continue
        touched.add(item.id)

        if item.status == ItemStatus.CLOSED and item.id in was_closed_before:
            if update.status == "closed":
                result.warnings.append(f"Item {item.item_number} was already closed at meeting {item.closed_meeting_no}; nothing to do.")
                continue
            # Reopen
            item.status = ItemStatus.OPEN if update.status == "open" else ItemStatus.ON_HOLD
            item.closed_meeting_no = None
            item.closed_date = None
            result.reopened.append(item)
            note = update.note.strip() or "Reopened."
            item.history.append(ItemHistoryEntry(meeting_no=meeting_no, date=meeting_date, note=f"Reopened. {note}".strip(), status=item.status))
        elif update.status == "closed":
            item.status = ItemStatus.CLOSED
            item.closed_meeting_no = meeting_no
            item.closed_date = meeting_date
            item.history.append(ItemHistoryEntry(meeting_no=meeting_no, date=meeting_date, note=update.note.strip() or "Closed.", status=ItemStatus.CLOSED))
            result.closed_this_meeting.append(item)
        else:
            item.status = ItemStatus.OPEN if update.status == "open" else ItemStatus.ON_HOLD
            notes: list[str] = []
            if update.note.strip():
                notes.append(update.note.strip())
            new_due = parse_date(update.new_due_date, default_year=meeting_date.year)
            if update.new_due_date and new_due is None:
                result.warnings.append(f"Could not read new due date {update.new_due_date!r} for item {item.item_number}.")
            if new_due is not None and new_due != item.due_date:
                notes.append(f"Due date revised to {new_due.strftime('%m/%d/%Y')}.")
                item.due_date = new_due
            if update.new_responsible and update.new_responsible.strip() and update.new_responsible.strip() != item.responsible:
                notes.append(f"Reassigned to {update.new_responsible.strip()}.")
                item.responsible = update.new_responsible.strip()
            item.history.append(ItemHistoryEntry(meeting_no=meeting_no, date=meeting_date, note=" ".join(notes) or "Discussed; remains open.", status=item.status))
        item.last_discussed_meeting_no = meeting_no

    # 2. Everything open that was not touched is carried forward, visibly.
    for item in working:
        if item.id in touched or item.id in was_closed_before:
            continue
        if item.status in (ItemStatus.OPEN, ItemStatus.ON_HOLD):
            item.history.append(ItemHistoryEntry(meeting_no=meeting_no, date=meeting_date, note="Not discussed – carried forward.", status=item.status))
            result.not_discussed.append(item)

    # 3. New items get numbers and join the list.
    open_descriptions = [(i.item_number, i.description) for i in working if i.status != ItemStatus.CLOSED]
    seq = next_sequential_number(working) if numbering.style == "sequential" else 1
    for new in extraction.new_items:
        description = new.description.strip()
        if not description:
            continue
        for number, existing in open_descriptions:
            if looks_like_duplicate(description, existing):
                result.warnings.append(f"New item '{description[:60]}…' looks like existing item {number}; check before issuing.")
                break
        number = format_item_number(numbering, meeting_no, seq)
        seq += 1
        due = parse_date(new.due_date, default_year=meeting_date.year)
        if new.due_date and due is None:
            result.warnings.append(f"Could not read due date {new.due_date!r} for new item '{description[:40]}…'.")
        item = OpenItem(
            project_id=project_id,
            item_number=number,
            description=description,
            section_key=new.section_key or "general",
            responsible=new.responsible.strip(),
            date_raised=meeting_date,
            raised_meeting_no=meeting_no,
            due_date=due,
            status=ItemStatus.OPEN,
            last_discussed_meeting_no=meeting_no,
            priority=new.priority,
            history=[ItemHistoryEntry(meeting_no=meeting_no, date=meeting_date, note=new.note.strip() or "Raised.", status=ItemStatus.OPEN)],
        )
        working.append(item)
        result.new_items.append(item)

    # 4. Assemble.
    result.items = _sorted(working)
    result.active_items = _sorted(
        i for i in result.items
        if i.status != ItemStatus.CLOSED or i.closed_meeting_no == meeting_no
    )
    result.overdue = [i for i in result.active_items if i.is_overdue(meeting_date)]
    result.new_items = _sorted(result.new_items)
    result.closed_this_meeting = _sorted(result.closed_this_meeting)
    result.not_discussed = _sorted(result.not_discussed)
    return result


def tracker_rows(items: Iterable[OpenItem], as_of: date, current_meeting_no: int | None = None) -> list[dict]:
    """Flatten items for tables (tracker page, CSV). Includes computed flags."""
    rows = []
    for item in _sorted(items):
        overdue = item.is_overdue(as_of)
        meeting_no = current_meeting_no if current_meeting_no is not None else item.last_discussed_meeting_no
        rows.append({
            "item_number": item.item_number,
            "description": item.description,
            "section_key": item.section_key,
            "responsible": item.responsible,
            "date_raised": item.date_raised,
            "due_date": item.due_date,
            "status": item.status.value,
            "overdue": overdue,
            "days_overdue": (as_of - item.due_date).days if overdue and item.due_date else 0,
            "meetings_open": item.meetings_open(meeting_no),
            "last_discussed": item.last_discussed_meeting_no,
            "last_update": item.latest_note(),
            "priority": item.priority,
        })
    return rows

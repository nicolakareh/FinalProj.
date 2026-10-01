"""Orchestration: transcript -> draft -> review -> finalized minutes + updated log.

The Streamlit app and the demo loader both go through these functions, so the
UI never has to know about the engine or the renderers directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from .carryforward import CarryForwardResult, carry_forward
from .extract import ExtractionContext, Extractor
from .models import Firm, ItemStatus, Meeting, MeetingExtraction, MeetingStatus, Project
from .render_common import output_basename
from .render_docx import render_docx
from .render_xlsx import render_xlsx
from .storage import Store


class PipelineError(RuntimeError):
    pass


@dataclass
class Draft:
    meeting: Meeting
    result: CarryForwardResult
    warnings: list[str] = field(default_factory=list)


def build_context(store: Store, firm: Firm, project: Project, *, meeting_no: int, meeting_date: date, meeting_time: str = "", location: str = "") -> ExtractionContext:
    prior = [i for i in store.list_items(project.id) if i.status != ItemStatus.CLOSED]
    last = store.last_final_meeting(project.id)
    return ExtractionContext(
        firm_name=firm.name,
        firm_format=firm.format,
        project=project,
        meeting_no=meeting_no,
        meeting_date=meeting_date,
        prior_items=prior,
        previous_meeting_date=last.meeting_date if last else None,
        meeting_time=meeting_time,
        location=location,
    )


def compute(store: Store, firm: Firm, project: Project, meeting: Meeting) -> CarryForwardResult:
    """Run the carry-forward engine for a meeting against the project's current items."""
    extraction = meeting.extraction or MeetingExtraction()
    return carry_forward(
        store.list_items(project.id),
        extraction,
        project_id=project.id,
        meeting_no=meeting.meeting_no,
        meeting_date=meeting.meeting_date,
        numbering=firm.format.numbering,
    )


def generate_draft(
    store: Store,
    firm: Firm,
    project: Project,
    *,
    transcript: str,
    extractor: Extractor,
    meeting_no: int,
    meeting_date: date,
    source_name: str = "",
    meeting_time: str = "",
    location: str = "",
) -> Draft:
    if not transcript.strip():
        raise PipelineError("The transcript is empty.")
    last = store.last_final_meeting(project.id)
    if last is not None and meeting_no <= last.meeting_no:
        raise PipelineError(f"Meeting {last.meeting_no} is already finalized; the next meeting must be number {last.meeting_no + 1} or higher.")
    ctx = build_context(store, firm, project, meeting_no=meeting_no, meeting_date=meeting_date, meeting_time=meeting_time, location=location)
    extraction = extractor.extract(transcript, ctx, source_name=source_name)
    # Replace any earlier draft with the same number so drafts never pile up.
    for existing in store.list_meetings(project.id, MeetingStatus.DRAFT):
        if existing.meeting_no == meeting_no:
            store.delete_meeting(existing.id)
    meeting = Meeting(
        project_id=project.id,
        meeting_no=meeting_no,
        meeting_date=meeting_date,
        meeting_time=meeting_time,
        location=location,
        source_name=source_name,
        transcript=transcript,
        extraction=extraction,
        status=MeetingStatus.DRAFT,
    )
    store.save_meeting(meeting)
    result = compute(store, firm, project, meeting)
    return Draft(meeting=meeting, result=result, warnings=list(extraction.review_flags) + list(result.warnings))


def finalize(store: Store, firm: Firm, project: Project, meeting: Meeting, output_dir: str | Path) -> tuple[Meeting, CarryForwardResult]:
    """Issue the minutes: render files, commit the item list, mark the meeting final."""
    last = store.last_final_meeting(project.id)
    if last is not None and meeting.meeting_no <= last.meeting_no:
        raise PipelineError(f"Meeting {last.meeting_no} is already finalized; cannot finalize meeting {meeting.meeting_no} before it.")
    result = compute(store, firm, project, meeting)
    output_dir = Path(output_dir)
    base = output_basename(project.name, meeting.meeting_no, meeting.meeting_date)
    docx_path = render_docx(firm, project, meeting, result, output_dir / f"{base}_Minutes.docx")
    xlsx_path = render_xlsx(result.items, output_dir / f"{base}_Open-Items.xlsx", fmt=firm.format, as_of=meeting.meeting_date, meeting_no=meeting.meeting_no, project_name=project.name)
    store.replace_items(project.id, result.items)
    meeting.status = MeetingStatus.FINAL
    meeting.finalized_at = datetime.now()
    meeting.minutes_docx_path = str(docx_path)
    meeting.items_log_xlsx_path = str(xlsx_path)
    store.save_meeting(meeting)
    return meeting, result


def replay_items(store: Store, firm: Firm, project: Project) -> None:
    """Rebuild the project's item list from its finalized meetings, in order.

    The engine is deterministic, so this is how a meeting can be withdrawn and
    redone without hand-editing the log.
    """
    items = []
    for meeting in store.list_meetings(project.id, MeetingStatus.FINAL):
        result = carry_forward(
            items,
            meeting.extraction or MeetingExtraction(),
            project_id=project.id,
            meeting_no=meeting.meeting_no,
            meeting_date=meeting.meeting_date,
            numbering=firm.format.numbering,
        )
        items = result.items
    store.replace_items(project.id, items)


def withdraw_last_meeting(store: Store, firm: Firm, project: Project) -> Meeting | None:
    """Un-finalize the most recent meeting (kept as a draft) and rebuild the log."""
    last = store.last_final_meeting(project.id)
    if last is None:
        return None
    last.status = MeetingStatus.DRAFT
    last.finalized_at = None
    store.save_meeting(last)
    replay_items(store, firm, project)
    return last


def result_for_meeting(store: Store, firm: Firm, project: Project, meeting: Meeting) -> CarryForwardResult:
    """Recreate the tracker exactly as it stood when this meeting was issued."""
    items = []
    for earlier in store.list_meetings(project.id, MeetingStatus.FINAL):
        if earlier.meeting_no >= meeting.meeting_no:
            break
        items = carry_forward(
            items,
            earlier.extraction or MeetingExtraction(),
            project_id=project.id,
            meeting_no=earlier.meeting_no,
            meeting_date=earlier.meeting_date,
            numbering=firm.format.numbering,
        ).items
    return carry_forward(
        items,
        meeting.extraction or MeetingExtraction(),
        project_id=project.id,
        meeting_no=meeting.meeting_no,
        meeting_date=meeting.meeting_date,
        numbering=firm.format.numbering,
    )


# --------------------------------------------------------------------------
# Batch: drop several transcripts, get every meeting issued in order.
# --------------------------------------------------------------------------
@dataclass
class BatchItem:
    name: str
    transcript: str
    meeting_no: int
    meeting_date: date


@dataclass
class IssuedMeeting:
    meeting: Meeting
    result: CarryForwardResult
    flags: list[str] = field(default_factory=list)


def process_batch(
    store: Store,
    firm: Firm,
    project: Project,
    items: list[BatchItem],
    *,
    extractor: Extractor,
    output_dir: str | Path,
    meeting_time: str = "",
    location: str = "",
    on_progress=None,
) -> list[IssuedMeeting]:
    """Issue each transcript in meeting order. Stops at the first failure; earlier meetings stay issued."""
    issued: list[IssuedMeeting] = []
    for item in sorted(items, key=lambda i: (i.meeting_no, i.meeting_date)):
        if on_progress:
            on_progress(item)
        draft = generate_draft(
            store, firm, project,
            transcript=item.transcript, extractor=extractor,
            meeting_no=item.meeting_no, meeting_date=item.meeting_date,
            source_name=item.name, meeting_time=meeting_time, location=location,
        )
        meeting, result = finalize(store, firm, project, draft.meeting, output_dir)
        issued.append(IssuedMeeting(meeting=meeting, result=result, flags=list(draft.warnings)))
    return issued

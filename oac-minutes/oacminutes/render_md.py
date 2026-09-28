"""Markdown rendering of the minutes (used for the in-app preview)."""
from __future__ import annotations

from .carryforward import CarryForwardResult
from .dates import fmt_date
from .models import Firm, Meeting, Project
from .render_common import cell_text, sections_with_content, visible_items


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", "<br>")


def render_markdown(firm: Firm, project: Project, meeting: Meeting, result: CarryForwardResult) -> str:
    fmt = firm.format
    out: list[str] = []
    out.append(f"# {fmt.minutes_title}")
    out.append(f"**{firm.name}**  ")
    out.append("")
    out.append("| | |")
    out.append("|---|---|")
    for hf in fmt.header_fields:
        out.append(f"| **{hf.label}** | {_md_escape(project.header_value(hf.key, meeting))} |")
    out.append("")

    extraction = meeting.extraction
    if fmt.show_attendees_table and extraction and extraction.attendees:
        out.append("## Attendees")
        out.append("| Name | Company | Role | Present |")
        out.append("|---|---|---|---|")
        for a in extraction.attendees:
            out.append(f"| {_md_escape(a.name)} | {_md_escape(a.company)} | {_md_escape(a.role)} | {'Yes' if a.present else 'No'} |")
        out.append("")

    for title, bullets in sections_with_content(extraction, fmt):
        out.append(f"## {title}")
        for b in bullets:
            out.append(f"- {b}")
        out.append("")

    if fmt.show_decisions and extraction and extraction.decisions:
        out.append("## Decisions")
        for d in extraction.decisions:
            out.append(f"- {d}")
        out.append("")

    items = visible_items(result, fmt)
    out.append("## Open Items")
    if items:
        cols = fmt.open_items_columns
        out.append("| " + " | ".join(c.label for c in cols) + " |")
        out.append("|" + "---|" * len(cols))
        for item in items:
            cells = [cell_text(item, c.key, fmt, meeting_no=meeting.meeting_no, as_of=meeting.meeting_date) for c in cols]
            out.append("| " + " | ".join(_md_escape(c) for c in cells) + " |")
    else:
        out.append("_No open items._")
    out.append("")

    if extraction and extraction.next_meeting and any([extraction.next_meeting.date, extraction.next_meeting.time, extraction.next_meeting.location]):
        nm = extraction.next_meeting
        parts = [p for p in [fmt_date(_to_date(nm.date), fmt.date_format) or nm.date, nm.time, nm.location] if p]
        out.append("## Next Meeting")
        out.append(", ".join(parts))
        out.append("")

    out.append("---")
    out.append(f"_{fmt.disclaimer}_")
    return "\n".join(out)


def _to_date(value):
    from .dates import parse_date
    return parse_date(value)

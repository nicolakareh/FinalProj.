"""OAC Minutes – upload a meeting transcript, get issued minutes plus a living open-items log.

Run:  streamlit run app.py
"""
from __future__ import annotations

import math
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from oacminutes import __version__  # noqa: E402
from oacminutes.carryforward import tracker_rows  # noqa: E402
from oacminutes.dates import fmt_date, parse_date  # noqa: E402
from oacminutes.extract import DEFAULT_MODEL, ExtractionError, credentials_present, get_extractor  # noqa: E402
from oacminutes.formats import list_builtin_formats, load_builtin_format  # noqa: E402
from oacminutes.models import (  # noqa: E402
    Attendee, Firm, FirmFormat, ItemHistoryEntry, ItemStatus, Meeting, MeetingExtraction,
    MeetingStatus, NewItem, NextMeeting, PriorItemUpdate, Project, SectionNotes,
)
from oacminutes.parsers import AUDIO_EXTENSIONS, TRANSCRIPT_EXTENSIONS, UnsupportedFileType, kind_of, load_transcript, word_count  # noqa: E402
from oacminutes.pipeline import PipelineError, compute, finalize, generate_draft, result_for_meeting, withdraw_last_meeting  # noqa: E402
from oacminutes.render_common import slugify  # noqa: E402
from oacminutes.render_md import render_markdown  # noqa: E402
from oacminutes.render_xlsx import render_csv, render_xlsx  # noqa: E402
from oacminutes.samples import DEMO_MEETINGS, DEMO_PROJECT_NAME, load_demo_project, sample_transcript  # noqa: E402
from oacminutes.storage import Store  # noqa: E402
from oacminutes.transcription import TranscriptionUnavailable, available_provider, transcribe_audio  # noqa: E402

# Hosted Streamlit (Community Cloud etc.) keeps configuration in st.secrets; mirror it into the
# environment so the library code (which never imports streamlit) sees it.
try:
    for _key in ("ANTHROPIC_API_KEY", "OACMINUTES_EXTRACTOR", "OACMINUTES_MODEL", "OACMINUTES_DATA_DIR"):
        if _key not in os.environ and _key in st.secrets:
            os.environ[_key] = str(st.secrets[_key])
except Exception:  # no secrets file locally; that's fine
    pass

DATA_DIR = Path(os.environ.get("OACMINUTES_DATA_DIR", ROOT / "data"))
OUTPUT_DIR = DATA_DIR / "output"
UPLOAD_DIR = DATA_DIR / "uploads"
FORMATS = list_builtin_formats()
STATUS_OPTIONS = ["open", "on_hold", "closed", "not_discussed"]

st.set_page_config(page_title="OAC Minutes", page_icon="📋", layout="wide")


@st.cache_resource
def get_store() -> Store:
    return Store(DATA_DIR / "oacminutes.db")


store = get_store()


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _s(value) -> str:
    """Cell value -> clean string (pandas gives NaN/None for empty cells)."""
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def _lines(text: str) -> list[str]:
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if line.startswith(("-", "•", "*")):
            line = line[1:].strip()
        if line:
            out.append(line)
    return out


def _file_bytes(path: str | None) -> bytes | None:
    if not path or not Path(path).exists():
        return None
    return Path(path).read_bytes()


def _select_id(label: str, options: list, current_key: str, widget_key: str, name_of) -> str | None:
    ids = [o.id for o in options]
    current = st.session_state.get(current_key)
    index = ids.index(current) if current in ids else 0
    chosen = st.sidebar.selectbox(label, ids, index=index, format_func=lambda i: name_of(i), key=widget_key)
    st.session_state[current_key] = chosen
    return chosen


# --------------------------------------------------------------------------
# sidebar: firm + project selection, demo, mode
# --------------------------------------------------------------------------
def sidebar() -> tuple[Firm | None, Project | None]:
    st.sidebar.title("📋 OAC Minutes")
    firm = project = None
    firms = store.list_firms()
    if firms:
        firm_id = _select_id("Firm", firms, "firm_id", "firm_select", lambda i: next(f.name for f in firms if f.id == i))
        firm = store.get_firm(firm_id)
        projects = store.list_projects(firm.id)
        if projects:
            project_id = _select_id("Project", projects, "project_id", "project_select", lambda i: next(p.name for p in projects if p.id == i))
            project = store.get_project(project_id)
        else:
            st.sidebar.caption("No projects yet for this firm.")

    with st.sidebar.expander("New firm"):
        name = st.text_input("Firm name", key="new_firm_name")
        template = st.selectbox("Minutes format template", list(FORMATS), format_func=lambda k: FORMATS[k].name, key="new_firm_format")
        if st.button("Create firm", key="create_firm") and name.strip():
            created = store.save_firm(Firm(name=name.strip(), format=load_builtin_format(template)))
            st.session_state["firm_id"] = created.id
            st.session_state.pop("firm_select", None)
            st.session_state.pop("project_id", None)
            st.session_state.pop("project_select", None)
            st.rerun()
    if firm is not None:
        with st.sidebar.expander("New project"):
            pname = st.text_input("Project name", key="new_project_name")
            pnum = st.text_input("Project number", key="new_project_number")
            if st.button("Create project", key="create_project") and pname.strip():
                created = store.save_project(Project(firm_id=firm.id, name=pname.strip(), number=pnum.strip(), opm_firm=firm.name))
                st.session_state["project_id"] = created.id
                st.session_state.pop("project_select", None)
                st.rerun()

    st.sidebar.divider()
    if not any(p.name == DEMO_PROJECT_NAME for p in store.list_projects()):
        if st.sidebar.button("Load demo project", key="load_demo"):
            with st.spinner("Running three sample meetings through the pipeline…"):
                demo_firm, demo_project, _ = load_demo_project(store, OUTPUT_DIR)
            st.session_state["firm_id"] = demo_firm.id
            st.session_state["project_id"] = demo_project.id
            st.session_state.pop("firm_select", None)
            st.session_state.pop("project_select", None)
            st.rerun()
        st.sidebar.caption("Three sample OAC meetings for a fictional fire-station project.")

    if credentials_present():
        st.sidebar.success(f"Extractor: Claude ({os.environ.get('OACMINUTES_MODEL', DEFAULT_MODEL)})")
    else:
        st.sidebar.warning("Demo mode: no ANTHROPIC_API_KEY found. Only the bundled sample transcripts can be processed.")
    if available_provider() is None:
        st.sidebar.caption("Audio upload needs `pip install faster-whisper`; transcript files work now.")
    st.sidebar.caption(f"OAC Minutes v{__version__}")
    return firm, project


# --------------------------------------------------------------------------
# New meeting
# --------------------------------------------------------------------------
def tab_new_meeting(firm: Firm, project: Project) -> None:
    issued_id = st.session_state.get("issued_meeting_id")
    if issued_id:
        issued = store.get_meeting(issued_id)
        if issued is not None and issued.project_id == project.id:
            box = st.container(border=True)
            box.success(f"Meeting {issued.meeting_no} ({fmt_date(issued.meeting_date, firm.format.date_format)}) issued. The open-items log has been updated.")
            c1, c2, c3 = box.columns(3)
            docx = _file_bytes(issued.minutes_docx_path)
            xlsx = _file_bytes(issued.items_log_xlsx_path)
            if docx:
                c1.download_button("Download minutes (.docx)", docx, file_name=Path(issued.minutes_docx_path).name, key="dl_issued_docx")
            if xlsx:
                c2.download_button("Download open-items log (.xlsx)", xlsx, file_name=Path(issued.items_log_xlsx_path).name, key="dl_issued_xlsx")
            if c3.button("Dismiss", key="dismiss_issued"):
                st.session_state.pop("issued_meeting_id", None)
                st.rerun()

    last = store.last_final_meeting(project.id)
    open_items = [i for i in store.list_items(project.id) if i.status != ItemStatus.CLOSED]
    next_no = (last.meeting_no + 1) if last else 1
    default_date = (last.meeting_date + timedelta(days=7)) if last else date.today()

    st.subheader("1. Meeting details")
    c1, c2, c3, c4 = st.columns(4)
    meeting_no = int(c1.number_input("Meeting number", min_value=1, value=next_no, step=1, key="nm_no"))
    meeting_date = c2.date_input("Meeting date", value=default_date, key="nm_date")
    meeting_time = c3.text_input("Time", value=project.meeting_time, key="nm_time")
    location = c4.text_input("Location", value=project.location, key="nm_location")
    if last:
        st.caption(f"Last issued: Meeting {last.meeting_no} on {fmt_date(last.meeting_date, firm.format.date_format)}. {len(open_items)} open item(s) will be carried into this meeting.")
    else:
        st.caption("This is the first meeting for the project; the open-items log starts here.")

    st.subheader("2. Transcript or recording")
    transcript, source_name = "", ""
    up_tab, paste_tab, sample_tab = st.tabs(["Upload file", "Paste text", "Sample transcript"])
    with up_tab:
        exts = sorted(e.lstrip(".") for e in TRANSCRIPT_EXTENSIONS | AUDIO_EXTENSIONS)
        uploaded = st.file_uploader("Transcript (.txt, .md, .vtt, .srt, .docx) or recording (.mp3, .m4a, .wav, .mp4 …)", type=exts, key="nm_upload")
        if uploaded is not None:
            kind = kind_of(uploaded.name)
            try:
                if kind == "transcript":
                    transcript, source_name = load_transcript(uploaded.getvalue(), uploaded.name), uploaded.name
                elif kind == "audio":
                    cache_key = f"audio_transcript::{uploaded.name}::{uploaded.size}"
                    if cache_key not in st.session_state:
                        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
                        target = UPLOAD_DIR / uploaded.name
                        target.write_bytes(uploaded.getvalue())
                        with st.spinner("Transcribing the recording locally… this can take a few minutes."):
                            st.session_state[cache_key] = transcribe_audio(target)
                    transcript, source_name = st.session_state[cache_key], uploaded.name
                else:
                    st.error("Unsupported file type.")
            except TranscriptionUnavailable as exc:
                st.error(str(exc))
            except UnsupportedFileType as exc:
                st.error(str(exc))
    with paste_tab:
        pasted = st.text_area("Paste the transcript", height=220, key="nm_paste", placeholder="Dana: Good morning, let's get started…")
        if pasted.strip() and not transcript:
            transcript, source_name = pasted, "pasted-transcript.txt"
    with sample_tab:
        options = [None] + [f for f, _, _ in DEMO_MEETINGS]
        choice = st.selectbox("Bundled sample (works without an API key)", options, format_func=lambda f: "—" if f is None else f"{f}  (meeting {int(f.split('_')[2][:2])})", key="nm_sample")
        if choice and not transcript:
            transcript, source_name = sample_transcript(choice), choice

    if transcript:
        st.caption(f"{word_count(transcript):,} words loaded from {source_name}.")
        with st.expander("Transcript preview"):
            st.text(transcript[:6000] + ("\n…" if len(transcript) > 6000 else ""))

    if st.button("Generate minutes", type="primary", disabled=not transcript, key="nm_generate"):
        try:
            extractor = get_extractor()
            with st.spinner("Reading the transcript, matching it against the open items…"):
                draft = generate_draft(
                    store, firm, project,
                    transcript=transcript, extractor=extractor,
                    meeting_no=meeting_no, meeting_date=meeting_date,
                    source_name=source_name, meeting_time=meeting_time, location=location,
                )
            st.session_state["draft_meeting_id"] = draft.meeting.id
            st.session_state.pop("issued_meeting_id", None)
            st.rerun()
        except (ExtractionError, PipelineError) as exc:
            st.error(str(exc))

    meeting = None
    draft_id = st.session_state.get("draft_meeting_id")
    if draft_id:
        meeting = store.get_meeting(draft_id)
    if meeting is None or meeting.project_id != project.id or meeting.status != MeetingStatus.DRAFT:
        drafts = store.list_meetings(project.id, MeetingStatus.DRAFT)
        meeting = drafts[-1] if drafts else None
        if meeting is not None:
            st.session_state["draft_meeting_id"] = meeting.id
    if meeting is not None:
        review_draft(firm, project, meeting)


def _attendee_frame(ext: MeetingExtraction) -> pd.DataFrame:
    rows = [a.model_dump() for a in ext.attendees] or [{"name": "", "company": "", "role": "", "present": True}]
    return pd.DataFrame(rows, columns=["name", "company", "role", "present"])


def _prior_frame(ext: MeetingExtraction, prior_items) -> pd.DataFrame:
    updates = {u.item_number: u for u in ext.prior_item_updates}
    rows = []
    for item in prior_items:
        u = updates.get(item.item_number)
        rows.append({
            "item_number": item.item_number,
            "description": item.description,
            "responsible": item.responsible,
            "due": fmt_date(item.due_date),
            "status": u.status if u else "not_discussed",
            "note": u.note if u else "",
            "new_due_date": (u.new_due_date or "") if u else "",
            "new_responsible": (u.new_responsible or "") if u else "",
        })
    return pd.DataFrame(rows, columns=["item_number", "description", "responsible", "due", "status", "note", "new_due_date", "new_responsible"])


def _new_items_frame(ext: MeetingExtraction) -> pd.DataFrame:
    rows = [n.model_dump() for n in ext.new_items]
    return pd.DataFrame(rows, columns=["description", "responsible", "due_date", "section_key", "priority", "note"])


def review_draft(firm: Firm, project: Project, meeting: Meeting) -> None:
    fmt = firm.format
    st.divider()
    st.subheader(f"3. Review draft – Meeting {meeting.meeting_no}, {fmt_date(meeting.meeting_date, fmt.date_format)}")
    st.caption("Everything below is editable. Nothing is written to the open-items log until you finalize.")
    ext = meeting.extraction or MeetingExtraction()
    result = compute(store, firm, project, meeting)
    prior_items = [i for i in store.list_items(project.id) if i.status != ItemStatus.CLOSED]

    flags = list(ext.review_flags) + list(result.warnings)
    if flags:
        with st.expander(f"⚠️ {len(flags)} thing(s) to check before issuing", expanded=True):
            for flag in flags:
                st.markdown(f"- {flag}")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("New items", len(result.new_items))
    m2.metric("Closed this meeting", len(result.closed_this_meeting))
    m3.metric("Not discussed – carried", len(result.not_discussed))
    m4.metric("Overdue", len(result.overdue))
    m5.metric("Open after this meeting", sum(1 for i in result.items if i.status != ItemStatus.CLOSED))

    key = meeting.id
    top_left, top_right = st.columns([1, 1], gap="large")
    with top_left:
        st.markdown("#### Attendees")
        att_df = st.data_editor(
            _attendee_frame(ext), num_rows="dynamic", hide_index=True, key=f"att_{key}", width="stretch",
            column_config={"present": st.column_config.CheckboxColumn("Present"), "name": "Name", "company": "Company", "role": "Role"},
        )
    with top_right:
        decisions_txt = st.text_area("Decisions (one per line)", value="\n".join(ext.decisions), key=f"dec_{key}", height=120)
        st.markdown("#### Next meeting")
        n1, n2, n3 = st.columns(3)
        nm = ext.next_meeting or NextMeeting()
        nm_date = n1.text_input("Date (YYYY-MM-DD)", value=nm.date or "", key=f"nmd_{key}")
        nm_time = n2.text_input("Time", value=nm.time or "", key=f"nmt_{key}")
        nm_loc = n3.text_input("Location", value=nm.location or "", key=f"nml_{key}")

    st.markdown("#### Discussion by section")
    by_key = {s.section_key: s.bullets for s in ext.sections}
    section_texts: dict[str, str] = {}
    empty_sections = []
    filled = [spec for spec in fmt.sections if by_key.get(spec.key)]
    empty_sections = [spec for spec in fmt.sections if not by_key.get(spec.key)]
    sec_cols = st.columns(2, gap="large")
    for idx, spec in enumerate(filled):
        bullets = by_key.get(spec.key) or []
        with sec_cols[idx % 2]:
            section_texts[spec.key] = st.text_area(spec.title, value="\n".join(bullets), key=f"sec_{key}_{spec.key}", height=max(100, 30 * (len(bullets) + 1)))
    if empty_sections:
        with st.expander("Sections with nothing recorded (add text to include them)"):
            for spec in empty_sections:
                section_texts[spec.key] = st.text_area(spec.title, value="", key=f"sec_{key}_{spec.key}", height=70)

    st.markdown("#### Prior open items – what happened to each")
    st.caption("Items left as *not_discussed* are carried forward unchanged and marked as such in the minutes.")
    prior_df = st.data_editor(
        _prior_frame(ext, prior_items), hide_index=True, key=f"prior_{key}", width="stretch", height=min(600, 60 + 36 * max(len(prior_items), 1)),
        disabled=["item_number", "description", "responsible", "due"],
        column_config={
            "item_number": st.column_config.TextColumn("Item", width="small"),
            "description": st.column_config.TextColumn("Description", width="large"),
            "responsible": st.column_config.TextColumn("Responsible", width="small"),
            "due": st.column_config.TextColumn("Due", width="small"),
            "status": st.column_config.SelectboxColumn("Status", options=STATUS_OPTIONS, required=True, width="small"),
            "note": st.column_config.TextColumn("Update for the minutes", width="large"),
            "new_due_date": st.column_config.TextColumn("New due (YYYY-MM-DD)", width="small"),
            "new_responsible": st.column_config.TextColumn("Reassign to", width="small"),
        },
    )
    st.markdown("#### New action items")
    new_df = st.data_editor(
        _new_items_frame(ext), num_rows="dynamic", hide_index=True, key=f"new_{key}", width="stretch",
        column_config={
            "description": st.column_config.TextColumn("Action item", width="large", required=True),
            "responsible": st.column_config.TextColumn("Responsible", width="small"),
            "due_date": st.column_config.TextColumn("Due (YYYY-MM-DD)", width="small"),
            "section_key": st.column_config.SelectboxColumn("Section", options=fmt.section_keys() + (["general"] if "general" not in fmt.section_keys() else []), width="small"),
            "priority": st.column_config.SelectboxColumn("Priority", options=["normal", "high"], width="small"),
            "note": st.column_config.TextColumn("Note for the log", width="medium"),
        },
    )

    def assembled() -> MeetingExtraction:
        attendees = [
            Attendee(name=_s(r["name"]), company=_s(r["company"]), role=_s(r["role"]), present=bool(r["present"]) if not (isinstance(r["present"], float) and math.isnan(r["present"])) else True)
            for r in att_df.to_dict("records") if _s(r["name"])
        ]
        sections = [SectionNotes(section_key=k, bullets=_lines(v)) for k, v in section_texts.items() if _lines(v)]
        updates = []
        for r in prior_df.to_dict("records"):
            status = _s(r["status"]) or "not_discussed"
            updates.append(PriorItemUpdate(item_number=_s(r["item_number"]), status=status, note=_s(r["note"]), new_due_date=_s(r["new_due_date"]) or None, new_responsible=_s(r["new_responsible"]) or None))
        new_items = []
        for r in new_df.to_dict("records"):
            if not _s(r["description"]):
                continue
            new_items.append(NewItem(description=_s(r["description"]), responsible=_s(r["responsible"]), due_date=_s(r["due_date"]) or None, section_key=_s(r["section_key"]) or "general", priority=_s(r["priority"]) or "normal", note=_s(r["note"])))
        next_meeting = NextMeeting(date=nm_date.strip() or None, time=nm_time.strip() or None, location=nm_loc.strip() or None)
        return MeetingExtraction(attendees=attendees, sections=sections, decisions=_lines(decisions_txt), prior_item_updates=updates, new_items=new_items, next_meeting=next_meeting, review_flags=ext.review_flags)

    b1, b2, b3 = st.columns([1, 1, 1])
    if b1.button("Apply edits & refresh preview", key=f"apply_{key}"):
        meeting.extraction = assembled()
        store.save_meeting(meeting)
        st.rerun()
    if b2.button("Finalize & issue minutes", type="primary", key=f"final_{key}"):
        try:
            meeting.extraction = assembled()
            store.save_meeting(meeting)
            issued, _ = finalize(store, firm, project, meeting, OUTPUT_DIR)
            st.session_state["issued_meeting_id"] = issued.id
            st.session_state.pop("draft_meeting_id", None)
            st.rerun()
        except PipelineError as exc:
            st.error(str(exc))
    if b3.button("Discard draft", key=f"discard_{key}"):
        store.delete_meeting(meeting.id)
        st.session_state.pop("draft_meeting_id", None)
        st.rerun()

    st.markdown("#### Preview (as it will read in the firm's format)")
    with st.container(border=True):
        st.markdown(render_markdown(firm, project, meeting, result))


# --------------------------------------------------------------------------
# Open items tracker
# --------------------------------------------------------------------------
def tab_open_items(firm: Firm, project: Project) -> None:
    fmt = firm.format
    items = store.list_items(project.id)
    if not items:
        st.info("No items yet. Issue the first meeting's minutes to start the log.")
        return
    last = store.last_final_meeting(project.id)
    current_no = last.meeting_no if last else 0
    c1, c2 = st.columns([1, 3])
    as_of = c1.date_input("Overdue as of", value=date.today(), key="oi_asof")
    rows = tracker_rows(items, as_of=as_of, current_meeting_no=current_no)
    df = pd.DataFrame(rows)
    open_df = df[df.status != "closed"]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Open", int((open_df.status == "open").sum()))
    m2.metric("Overdue", int(open_df.overdue.sum()))
    m3.metric("On hold", int((open_df.status == "on_hold").sum()))
    m4.metric("Closed to date", int((df.status == "closed").sum()))

    f1, f2, f3 = st.columns(3)
    statuses = f1.multiselect("Status", ["open", "on_hold", "closed"], default=["open", "on_hold"], key="oi_status")
    sections = f2.multiselect("Section", sorted(df.section_key.unique()), format_func=fmt.section_title, key="oi_section")
    who = f3.text_input("Responsible contains", key="oi_who")
    view = df[df.status.isin(statuses)]
    if sections:
        view = view[view.section_key.isin(sections)]
    if who.strip():
        view = view[view.responsible.str.contains(who.strip(), case=False, na=False)]

    show = view.assign(
        section=view.section_key.map(fmt.section_title),
        status=view.apply(lambda r: fmt.status_labels.get("overdue", "OVERDUE") if r.overdue else fmt.status_labels.get(r.status, r.status), axis=1),
        date_raised=view.date_raised.map(lambda d: fmt_date(d, fmt.date_format)),
        due_date=view.due_date.map(lambda d: fmt_date(d, fmt.date_format)),
    )[["item_number", "description", "section", "responsible", "date_raised", "due_date", "status", "days_overdue", "meetings_open", "last_discussed", "last_update"]]
    show = show.rename(columns={"item_number": "Item", "description": "Description", "section": "Section", "responsible": "Responsible", "date_raised": "Raised", "due_date": "Due", "status": "Status", "days_overdue": "Days overdue", "meetings_open": "Meetings open", "last_discussed": "Last discussed (Mtg)", "last_update": "Latest update"})

    def _style(row):
        if row["Status"] == fmt.status_labels.get("overdue", "OVERDUE"):
            return ["background-color: #fdecec; color: #7a0000"] * len(row)
        if row["Status"] == fmt.status_labels.get("closed", "Closed"):
            return ["color: #808080"] * len(row)
        return [""] * len(row)

    st.dataframe(
        show.style.apply(_style, axis=1), hide_index=True, width="stretch", height=min(700, 60 + 36 * max(len(show), 1)),
        column_config={"Description": st.column_config.TextColumn(width="large"), "Latest update": st.column_config.TextColumn(width="large"), "Item": st.column_config.TextColumn(width="small")},
    )

    d1, d2, d3 = st.columns([1, 1, 4])
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    xlsx_path = render_xlsx(items, OUTPUT_DIR / f"{slugify(project.name)}_Open-Items_as-of_{as_of.isoformat()}.xlsx", fmt=fmt, as_of=as_of, meeting_no=current_no, project_name=project.name)
    d1.download_button("Download log (.xlsx)", xlsx_path.read_bytes(), file_name=xlsx_path.name, key="oi_dl_xlsx")
    d2.download_button("Download log (.csv)", render_csv(items, fmt=fmt, as_of=as_of, meeting_no=current_no), file_name=f"{slugify(project.name)}_Open-Items.csv", key="oi_dl_csv")

    with st.expander("Edit items directly (between meetings)"):
        st.caption("Use this for corrections between meetings, e.g. an item closed by email. Changes are logged in the item's history.")
        editable = pd.DataFrame([
            {"item_number": i.item_number, "description": i.description, "responsible": i.responsible, "due_date": fmt_date(i.due_date, "%Y-%m-%d"), "status": i.status.value, "priority": i.priority, "section_key": i.section_key}
            for i in items if i.status != ItemStatus.CLOSED
        ], columns=["item_number", "description", "responsible", "due_date", "status", "priority", "section_key"])
        edited = st.data_editor(
            editable, hide_index=True, key="oi_edit", width="stretch", disabled=["item_number"],
            column_config={
                "item_number": "Item", "description": st.column_config.TextColumn("Description", width="large"),
                "responsible": "Responsible", "due_date": st.column_config.TextColumn("Due (YYYY-MM-DD)"),
                "status": st.column_config.SelectboxColumn("Status", options=["open", "on_hold", "closed"]),
                "priority": st.column_config.SelectboxColumn("Priority", options=["normal", "high"]),
                "section_key": st.column_config.SelectboxColumn("Section", options=fmt.section_keys()),
            },
        )
        if st.button("Save item edits", key="oi_save"):
            by_number = {i.item_number: i for i in items}
            changed = 0
            for r in edited.to_dict("records"):
                item = by_number.get(_s(r["item_number"]))
                if item is None:
                    continue
                new_status = ItemStatus(_s(r["status"]) or "open")
                new_due = parse_date(_s(r["due_date"]))
                changes = []
                if _s(r["description"]) and _s(r["description"]) != item.description:
                    item.description = _s(r["description"]); changes.append("description")
                if _s(r["responsible"]) != item.responsible:
                    item.responsible = _s(r["responsible"]); changes.append("responsible")
                if new_due != item.due_date:
                    item.due_date = new_due; changes.append(f"due date {fmt_date(new_due) or 'removed'}")
                if _s(r["priority"]) and _s(r["priority"]) != item.priority:
                    item.priority = _s(r["priority"]); changes.append("priority")
                if _s(r["section_key"]) and _s(r["section_key"]) != item.section_key:
                    item.section_key = _s(r["section_key"]); changes.append("section")
                if new_status != item.status:
                    item.status = new_status; changes.append(f"status {new_status.value}")
                    if new_status == ItemStatus.CLOSED:
                        item.closed_meeting_no, item.closed_date = current_no, as_of
                    else:
                        item.closed_meeting_no = item.closed_date = None
                if changes:
                    item.history.append(ItemHistoryEntry(meeting_no=current_no, date=as_of, note="Edited between meetings: " + ", ".join(changes) + ".", status=item.status))
                    store.save_item(item)
                    changed += 1
            st.success(f"Saved {changed} item(s).")
            st.rerun()


# --------------------------------------------------------------------------
# Meeting history
# --------------------------------------------------------------------------
def tab_history(firm: Firm, project: Project) -> None:
    fmt = firm.format
    meetings = store.list_meetings(project.id)
    if not meetings:
        st.info("No meetings yet.")
        return
    summary = pd.DataFrame([{
        "Meeting": m.meeting_no, "Date": fmt_date(m.meeting_date, fmt.date_format), "Status": m.status.value,
        "Source": m.source_name, "Attendees": len(m.extraction.attendees) if m.extraction else 0,
        "New items": len(m.extraction.new_items) if m.extraction else 0,
        "Words": word_count(m.transcript),
    } for m in meetings])
    st.dataframe(summary, hide_index=True, width="stretch")

    finals = [m for m in meetings if m.status == MeetingStatus.FINAL]
    for meeting in reversed(finals):
        with st.expander(f"Meeting {meeting.meeting_no} – {fmt_date(meeting.meeting_date, fmt.date_format)}"):
            result = result_for_meeting(store, firm, project, meeting)
            c1, c2, c3 = st.columns([1, 1, 3])
            docx = _file_bytes(meeting.minutes_docx_path)
            xlsx = _file_bytes(meeting.items_log_xlsx_path)
            if docx:
                c1.download_button("Minutes (.docx)", docx, file_name=Path(meeting.minutes_docx_path).name, key=f"h_docx_{meeting.id}")
            if xlsx:
                c2.download_button("Open-items log (.xlsx)", xlsx, file_name=Path(meeting.items_log_xlsx_path).name, key=f"h_xlsx_{meeting.id}")
            if not docx:
                c3.caption("Output file not found on disk; withdraw and re-issue to regenerate it.")
            st.markdown(render_markdown(firm, project, meeting, result))
            with st.expander("Transcript"):
                st.text(meeting.transcript)

    if finals:
        st.divider()
        st.markdown("**Withdraw the last issued meeting** – turns it back into a draft and rebuilds the log from the remaining meetings.")
        confirm = st.checkbox(f"I want to withdraw meeting {finals[-1].meeting_no}", key="hist_confirm")
        if st.button("Withdraw last meeting", disabled=not confirm, key="hist_withdraw"):
            withdrawn = withdraw_last_meeting(store, firm, project)
            st.session_state["draft_meeting_id"] = withdrawn.id if withdrawn else None
            st.session_state.pop("issued_meeting_id", None)
            st.rerun()


# --------------------------------------------------------------------------
# Firm format
# --------------------------------------------------------------------------
def tab_format(firm: Firm) -> None:
    fmt = firm.format
    st.caption("This is the firm's house style. Every project of the firm uses it; change it here and the next issued minutes follow it.")
    name = st.text_input("Firm name", value=firm.name, key="fmt_firm_name")
    c1, c2 = st.columns([2, 1])
    template = c1.selectbox("Start from a template", list(FORMATS), format_func=lambda k: FORMATS[k].name, key="fmt_template")
    if c2.button("Reset format to template", key="fmt_reset"):
        firm.format = load_builtin_format(template)
        firm.name = name.strip() or firm.name
        store.save_firm(firm)
        for k in list(st.session_state):
            if k.startswith("fmt_") and k not in ("fmt_template",):
                st.session_state.pop(k)
        st.rerun()

    t1, t2 = st.columns(2)
    minutes_title = t1.text_input("Minutes title", value=fmt.minutes_title, key="fmt_title")
    accent = t2.text_input("Accent color (hex)", value=fmt.accent_color, key="fmt_accent")
    st.markdown("**Sections, in the order they appear**")
    sec_df = st.data_editor(pd.DataFrame([s.model_dump() for s in fmt.sections], columns=["key", "title", "hint"]), num_rows="dynamic", hide_index=True, key="fmt_sections", width="stretch",
                            column_config={"key": st.column_config.TextColumn("Key (short, no spaces)", width="small"), "title": "Title in the minutes", "hint": st.column_config.TextColumn("What belongs here (guides the extractor)", width="large")})
    st.markdown("**Open-items table columns**")
    col_df = st.data_editor(pd.DataFrame([c.model_dump() for c in fmt.open_items_columns], columns=["key", "label", "width_in"]), num_rows="dynamic", hide_index=True, key="fmt_columns", width="stretch",
                            column_config={"key": st.column_config.SelectboxColumn("Field", options=["item_number", "description", "section", "responsible", "date_raised", "due_date", "status", "notes", "last_update"], required=True), "label": "Column label", "width_in": st.column_config.NumberColumn("Relative width", min_value=0.3, max_value=5.0, step=0.1)})
    n1, n2, n3, n4 = st.columns(4)
    style = n1.selectbox("Item numbering", ["meeting_item", "sequential"], index=["meeting_item", "sequential"].index(fmt.numbering.style), format_func=lambda s: "Meeting.Item (3.04)" if s == "meeting_item" else "Sequential (004)", key="fmt_numstyle")
    prefix = n2.text_input("Prefix", value=fmt.numbering.prefix, key="fmt_prefix")
    separator = n3.text_input("Separator", value=fmt.numbering.separator, key="fmt_sep")
    pad = int(n4.number_input("Digits", min_value=1, max_value=4, value=fmt.numbering.item_pad, key="fmt_pad"))
    l1, l2, l3, l4 = st.columns(4)
    lab_open = l1.text_input("Label: open", value=fmt.status_labels.get("open", "Open"), key="fmt_lab_open")
    lab_closed = l2.text_input("Label: closed", value=fmt.status_labels.get("closed", "Closed"), key="fmt_lab_closed")
    lab_overdue = l3.text_input("Label: overdue", value=fmt.status_labels.get("overdue", "OVERDUE"), key="fmt_lab_overdue")
    lab_new = l4.text_input("Label: new", value=fmt.status_labels.get("new", "New"), key="fmt_lab_new")
    not_discussed = st.text_input("Text for items not discussed", value=fmt.not_discussed_text, key="fmt_nd")
    disclaimer = st.text_area("Disclaimer at the end of the minutes", value=fmt.disclaimer, key="fmt_disc", height=90)
    o1, o2, o3, o4 = st.columns(4)
    show_att = o1.checkbox("Attendees table", value=fmt.show_attendees_table, key="fmt_show_att")
    show_dec = o2.checkbox("Decisions section", value=fmt.show_decisions, key="fmt_show_dec")
    show_closed = o3.checkbox("Show items closed this meeting", value=fmt.show_closed_items, key="fmt_show_closed")
    show_hist = o4.checkbox("Item history under description", value=fmt.show_item_history, key="fmt_show_hist")
    f1, f2, f3 = st.columns(3)
    font = f1.text_input("Font", value=fmt.font_name, key="fmt_font")
    size = int(f2.number_input("Font size", min_value=8, max_value=14, value=fmt.font_size, key="fmt_size"))
    date_format = f3.text_input("Date format (strftime)", value=fmt.date_format, key="fmt_datefmt")

    if st.button("Save format", type="primary", key="fmt_save"):
        try:
            new_fmt = FirmFormat(
                name=fmt.name, minutes_title=minutes_title.strip() or fmt.minutes_title, header_fields=fmt.header_fields,
                sections=[{"key": _s(r["key"]).lower().replace(" ", "_"), "title": _s(r["title"]), "hint": _s(r["hint"])} for r in sec_df.to_dict("records") if _s(r["key"]) and _s(r["title"])],
                open_items_columns=[{"key": _s(r["key"]), "label": _s(r["label"]) or _s(r["key"]), "width_in": None if _s(r["width_in"]) == "" else float(r["width_in"])} for r in col_df.to_dict("records") if _s(r["key"])],
                numbering={"style": style, "prefix": prefix, "separator": separator, "item_pad": pad},
                status_labels={**fmt.status_labels, "open": lab_open, "closed": lab_closed, "overdue": lab_overdue, "new": lab_new},
                show_attendees_table=show_att, show_decisions=show_dec, show_closed_items=show_closed, show_item_history=show_hist,
                not_discussed_text=not_discussed, disclaimer=disclaimer, date_format=date_format, font_name=font, font_size=size, accent_color=accent.strip().lstrip("#") or fmt.accent_color,
            )
            firm.format = new_fmt
            firm.name = name.strip() or firm.name
            store.save_firm(firm)
            st.success("Format saved.")
            st.rerun()
        except Exception as exc:  # pydantic validation errors are the common case
            st.error(f"Could not save: {exc}")

    with st.expander("Advanced: edit the format as JSON"):
        raw = st.text_area("Format JSON", value=fmt.model_dump_json(indent=2), height=400, key="fmt_json")
        if st.button("Save JSON", key="fmt_json_save"):
            try:
                firm.format = FirmFormat.model_validate_json(raw)
                store.save_firm(firm)
                st.success("Format saved from JSON.")
                st.rerun()
            except Exception as exc:
                st.error(f"Invalid format JSON: {exc}")


# --------------------------------------------------------------------------
# Project settings
# --------------------------------------------------------------------------
def tab_project(firm: Firm, project: Project) -> None:
    with st.form("project_form"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Project name", value=project.name)
        number = c2.text_input("Project number", value=project.number)
        owner = c1.text_input("Owner", value=project.owner)
        architect = c2.text_input("Architect", value=project.architect)
        contractor = c1.text_input("Contractor / CM", value=project.contractor)
        opm_firm = c2.text_input("OPM firm (as printed)", value=project.opm_firm or firm.name)
        prepared_by = c1.text_input("Prepared by", value=project.prepared_by)
        distribution = c2.text_input("Distribution", value=project.distribution)
        location = c1.text_input("Usual meeting location", value=project.location)
        meeting_time = c2.text_input("Usual meeting time", value=project.meeting_time)
        attendees = st.text_area("Usual attendees (one per line: Name – Company – Role)", value=project.default_attendees, height=160)
        notes = st.text_area("Glossary and context for the extractor (who 'the Town' is, nicknames, abbreviations)", value=project.extractor_notes, height=120)
        if st.form_submit_button("Save project", type="primary"):
            project.name, project.number, project.owner, project.architect = name.strip(), number.strip(), owner.strip(), architect.strip()
            project.contractor, project.opm_firm, project.prepared_by, project.distribution = contractor.strip(), opm_firm.strip(), prepared_by.strip(), distribution.strip()
            project.location, project.meeting_time, project.default_attendees, project.extractor_notes = location.strip(), meeting_time.strip(), attendees, notes
            store.save_project(project)
            st.success("Project saved.")
            st.rerun()
    st.divider()
    confirm = st.checkbox("I understand this deletes the project, its meetings and its log", key="proj_del_confirm")
    if st.button("Delete project", disabled=not confirm, key="proj_delete"):
        store.delete_project(project.id)
        for k in ("project_id", "project_select", "draft_meeting_id", "issued_meeting_id"):
            st.session_state.pop(k, None)
        st.rerun()


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main() -> None:
    firm, project = sidebar()
    if firm is None:
        st.title("OAC Minutes")
        st.markdown(
            """
Upload an OAC meeting recording or transcript and get back **issued minutes in your firm's format** plus an
**open-items log that carries forward from meeting to meeting**: every prior item is accounted for, resolved
items are marked closed, anything past its date is flagged overdue.

Create a firm in the sidebar, or press **Load demo project** to see three consecutive meetings already processed.
"""
        )
        return
    if project is None:
        st.title(firm.name)
        st.info("Create a project in the sidebar to get started.")
        tab_format(firm)
        return
    st.title(project.name)
    st.caption(f"{firm.name} · Project No. {project.number or '—'} · format: {firm.format.name}")
    t1, t2, t3, t4, t5 = st.tabs(["New meeting", "Open items", "Meeting history", "Firm format", "Project settings"])
    with t1:
        tab_new_meeting(firm, project)
    with t2:
        tab_open_items(firm, project)
    with t3:
        tab_history(firm, project)
    with t4:
        tab_format(firm)
    with t5:
        tab_project(firm, project)


main()

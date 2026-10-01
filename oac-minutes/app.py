"""OAC Minutes – drop meeting transcripts, get issued minutes in the firm's format and the open-items log.

Run:  streamlit run app.py   (or double-click start.command / start.bat)
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


def _load_dotenv(path: Path) -> None:
    """Read KEY=VALUE lines from .env so nobody has to touch a terminal to set the API key."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(ROOT / ".env")

from oacminutes import __version__  # noqa: E402
from oacminutes.carryforward import tracker_rows  # noqa: E402
from oacminutes.dates import fmt_date, parse_date  # noqa: E402
from oacminutes.detect import detect_meeting  # noqa: E402
from oacminutes.extract import DEFAULT_MODEL, ExtractionError, credentials_present, get_extractor  # noqa: E402
from oacminutes.format_from_minutes import propose_format  # noqa: E402
from oacminutes.formats import list_builtin_formats, load_builtin_format  # noqa: E402
from oacminutes.models import Firm, FirmFormat, ItemHistoryEntry, ItemStatus, MeetingStatus, Project  # noqa: E402
from oacminutes.parsers import AUDIO_EXTENSIONS, TRANSCRIPT_EXTENSIONS, UnsupportedFileType, kind_of, load_transcript, word_count  # noqa: E402
from oacminutes.pipeline import BatchItem, PipelineError, process_batch, result_for_meeting, withdraw_last_meeting  # noqa: E402
from oacminutes.render_common import slugify  # noqa: E402
from oacminutes.render_md import render_markdown  # noqa: E402
from oacminutes.render_xlsx import render_csv, render_xlsx  # noqa: E402
from oacminutes.samples import DEMO_PROJECT_NAME, load_demo_project  # noqa: E402
from oacminutes.storage import Store  # noqa: E402
from oacminutes.transcription import TranscriptionUnavailable, available_provider, transcribe_audio  # noqa: E402

# Hosted Streamlit keeps configuration in st.secrets; mirror it into the environment.
try:
    for _key in ("ANTHROPIC_API_KEY", "OACMINUTES_EXTRACTOR", "OACMINUTES_MODEL", "OACMINUTES_DATA_DIR"):
        if _key not in os.environ and _key in st.secrets:
            os.environ[_key] = str(st.secrets[_key])
except Exception:
    pass

DATA_DIR = Path(os.environ.get("OACMINUTES_DATA_DIR", ROOT / "data"))
OUTPUT_DIR = DATA_DIR / "output"
UPLOAD_DIR = DATA_DIR / "uploads"
USER_FORMATS_DIR = DATA_DIR / "formats"

st.set_page_config(page_title="OAC Minutes", page_icon="📋", layout="wide")


@st.cache_resource
def get_store() -> Store:
    return Store(DATA_DIR / "oacminutes.db")


store = get_store()


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _s(value) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip()


def _to_date(value) -> date | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, date):
        return value
    try:
        return pd.Timestamp(value).date()
    except (ValueError, TypeError):
        return parse_date(str(value))


def _file_bytes(path: str | None) -> bytes | None:
    if path and Path(path).exists():
        return Path(path).read_bytes()
    return None


def available_formats() -> dict[str, FirmFormat]:
    formats = dict(list_builtin_formats())
    for path in sorted(USER_FORMATS_DIR.glob("*.json")):
        try:
            formats[path.stem] = FirmFormat.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            continue
    return formats


def current_firm(project: Project | None) -> Firm:
    if project is not None:
        firm = store.get_firm(project.firm_id)
        if firm is not None:
            return firm
    firms = store.list_firms()
    if firms:
        return firms[0]
    return store.save_firm(Firm(name=os.environ.get("OACMINUTES_FIRM_NAME", "Your firm"), format=load_builtin_format()))


def transcript_for(uploaded) -> str:
    """Decode an uploaded file once per session (audio is transcribed once)."""
    cache = st.session_state.setdefault("texts", {})
    key = f"{uploaded.name}:{uploaded.size}"
    if key in cache:
        return cache[key]
    kind = kind_of(uploaded.name)
    if kind == "transcript":
        text = load_transcript(uploaded.getvalue(), uploaded.name)
    elif kind == "audio":
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        target = UPLOAD_DIR / uploaded.name
        target.write_bytes(uploaded.getvalue())
        with st.spinner(f"Transcribing {uploaded.name} locally… this can take a few minutes."):
            text = transcribe_audio(target)
    else:
        raise UnsupportedFileType(f"Unsupported file type: {uploaded.name}")
    cache[key] = text
    return text


# --------------------------------------------------------------------------
# top bar: project picker, new project, settings
# --------------------------------------------------------------------------
def new_project_popover(firm: Firm) -> None:
    with st.popover("New project"):
        name = st.text_input("Project name", key="np_name")
        number = st.text_input("Project number", key="np_number")
        if st.button("Create", key="np_create", type="primary", disabled=not name.strip()):
            created = store.save_project(Project(firm_id=firm.id, name=name.strip(), number=number.strip(), opm_firm=firm.name, prepared_by=firm.name))
            st.session_state["project_id"] = created.id
            st.session_state.pop("project_select", None)
            st.rerun()


def settings_popover(firm: Firm, project: Project) -> None:
    with st.popover("Settings"):
        st.markdown("**Firm**")
        firm_name = st.text_input("Firm name", value=firm.name, key="set_firm_name")
        formats = available_formats()
        keys = list(formats)
        current_key = next((k for k, f in formats.items() if f.model_dump() == firm.format.model_dump()), None)
        options = keys + ([] if current_key else ["(current custom format)"])
        chosen = st.selectbox("Minutes format", options, index=options.index(current_key) if current_key else len(options) - 1,
                              format_func=lambda k: formats[k].name if k in formats else k, key="set_format")
        with st.expander("Add a format from a sample of the firm's minutes"):
            st.caption("Upload one issued minutes document (.docx, .pdf or .txt). The app proposes a format file you can keep editing in data/formats/.")
            sample = st.file_uploader("Sample minutes", type=["docx", "pdf", "txt", "md"], key="set_sample")
            if st.button("Propose format", key="set_propose", disabled=sample is None):
                if not credentials_present():
                    st.error("This needs the Claude API. Put your key in a .env file next to app.py and restart.")
                else:
                    try:
                        with st.spinner("Reading the sample…"):
                            fmt, notes = propose_format(sample.getvalue(), sample.name, firm_name=firm_name.strip())
                        USER_FORMATS_DIR.mkdir(parents=True, exist_ok=True)
                        path = USER_FORMATS_DIR / f"{slugify(fmt.name).lower()}.json"
                        path.write_text(fmt.model_dump_json(indent=2), encoding="utf-8")
                        firm.format = fmt
                        firm.name = firm_name.strip() or firm.name
                        store.save_firm(firm)
                        st.success(f"Saved {path.name} and applied it. Check it against the sample.")
                        for note in notes:
                            st.caption(f"• {note}")
                    except ExtractionError as exc:
                        st.error(str(exc))
            uploaded_fmt = st.file_uploader("…or upload a format file (.json)", type=["json"], key="set_fmt_json")
            if uploaded_fmt is not None and st.button("Use this format file", key="set_fmt_use"):
                try:
                    fmt = FirmFormat.model_validate_json(uploaded_fmt.getvalue().decode("utf-8"))
                    USER_FORMATS_DIR.mkdir(parents=True, exist_ok=True)
                    (USER_FORMATS_DIR / Path(uploaded_fmt.name).name).write_text(fmt.model_dump_json(indent=2), encoding="utf-8")
                    firm.format = fmt
                    store.save_firm(firm)
                    st.success("Format applied.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Not a valid format file: {exc}")

        st.markdown("**Project**")
        c1, c2 = st.columns(2)
        name = c1.text_input("Project name", value=project.name, key="set_pname")
        number = c2.text_input("Project number", value=project.number, key="set_pnumber")
        owner = c1.text_input("Owner", value=project.owner, key="set_owner")
        architect = c2.text_input("Architect", value=project.architect, key="set_architect")
        contractor = c1.text_input("Contractor / CM", value=project.contractor, key="set_contractor")
        prepared_by = c2.text_input("Prepared by", value=project.prepared_by, key="set_prepared")
        distribution = c1.text_input("Distribution", value=project.distribution, key="set_dist")
        location = c2.text_input("Usual meeting location", value=project.location, key="set_location")
        meeting_time = c1.text_input("Usual meeting time", value=project.meeting_time, key="set_time")
        attendees = st.text_area("Usual attendees (one per line: Name – Company – Role)", value=project.default_attendees, key="set_attendees", height=110)
        notes = st.text_area("Glossary for the transcript reader (who 'the Town' is, nicknames, abbreviations)", value=project.extractor_notes, key="set_notes", height=90)
        if st.button("Save settings", type="primary", key="set_save"):
            firm.name = firm_name.strip() or firm.name
            if chosen in formats:
                firm.format = formats[chosen]
            store.save_firm(firm)
            project.name, project.number, project.owner, project.architect = name.strip(), number.strip(), owner.strip(), architect.strip()
            project.contractor, project.prepared_by, project.distribution = contractor.strip(), prepared_by.strip(), distribution.strip()
            project.location, project.meeting_time = location.strip(), meeting_time.strip()
            project.default_attendees, project.extractor_notes, project.opm_firm = attendees, notes, firm.name
            store.save_project(project)
            st.rerun()
        st.divider()
        confirm = st.checkbox("Delete this project and everything in it", key="set_del_confirm")
        if st.button("Delete project", disabled=not confirm, key="set_delete"):
            store.delete_project(project.id)
            for k in ("project_id", "project_select", "results"):
                st.session_state.pop(k, None)
            st.rerun()


def top_bar() -> tuple[Firm, Project | None]:
    projects = store.list_projects()
    left, right = st.columns([2, 3])
    left.markdown("## OAC Minutes")
    project = None
    with right:
        c1, c2, c3 = st.columns([3, 1, 1])
        if projects:
            ids = [p.id for p in projects]
            wanted = st.session_state.get("project_id")
            index = ids.index(wanted) if wanted in ids else 0
            chosen = c1.selectbox("Project", ids, index=index, format_func=lambda i: next(p.name for p in projects if p.id == i), key="project_select", label_visibility="collapsed")
            st.session_state["project_id"] = chosen
            project = store.get_project(chosen)
        firm = current_firm(project)
        with c2:
            new_project_popover(firm)
        with c3:
            if project is not None:
                settings_popover(firm, project)
    return firm, project


# --------------------------------------------------------------------------
# drop zone
# --------------------------------------------------------------------------
def plan_batch(files, project: Project, last_no: int, last_date: date | None) -> pd.DataFrame:
    rows = []
    for f in files:
        try:
            text = transcript_for(f)
        except (TranscriptionUnavailable, UnsupportedFileType) as exc:
            st.error(f"{f.name}: {exc}")
            continue
        number, when = detect_meeting(f.name, text, default_year=(last_date or date.today()).year)
        rows.append({"file": f.name, "meeting_no": number, "meeting_date": when, "words": word_count(text), "guessed": number is None or when is None})
    # Fill the gaps in order: unknown numbers continue from the last issued meeting; unknown dates step a week.
    rows.sort(key=lambda r: (r["meeting_no"] is None, r["meeting_no"] or 0, r["meeting_date"] or date.max))
    next_no = max([last_no] + [r["meeting_no"] for r in rows if r["meeting_no"]]) + 1
    prev_date = last_date
    for r in rows:
        if r["meeting_no"] is None:
            r["meeting_no"] = next_no
            next_no += 1
        if r["meeting_date"] is None:
            r["meeting_date"] = (prev_date + timedelta(days=7)) if prev_date else date.today()
        prev_date = r["meeting_date"]
    rows.sort(key=lambda r: r["meeting_no"])
    return pd.DataFrame(rows, columns=["file", "meeting_no", "meeting_date", "words", "guessed"])


def drop_zone(firm: Firm, project: Project) -> None:
    last = store.last_final_meeting(project.id)
    last_no = last.meeting_no if last else 0
    exts = sorted(e.lstrip(".") for e in TRANSCRIPT_EXTENSIONS | (AUDIO_EXTENSIONS if available_provider() else set()))
    generation = st.session_state.get("drop_gen", 0)   # bumped after a batch so the uploader clears itself
    files = st.file_uploader(
        "Drop this week's transcript here, or several meetings at once",
        type=exts, accept_multiple_files=True, key=f"drop_{project.id}_{generation}",
        help="Zoom, Teams and Otter transcripts (.vtt, .txt, .docx) work as exported." + ("" if available_provider() else " For audio recordings, install faster-whisper (see README)."),
    )
    if not files:
        return
    plan = plan_batch(files, project, last_no, last.meeting_date if last else None)
    if plan.empty:
        return
    st.caption("Meeting numbers and dates were read from the file names or the first minute of each transcript. Fix anything that looks wrong, then create the minutes.")
    edited = st.data_editor(
        plan, hide_index=True, width="stretch", key=f"plan_{project.id}", disabled=["file", "words", "guessed"],
        column_config={
            "file": st.column_config.TextColumn("File", width="large"),
            "meeting_no": st.column_config.NumberColumn("Meeting no.", min_value=1, step=1, format="%d"),
            "meeting_date": st.column_config.DateColumn("Meeting date", format="MM/DD/YYYY"),
            "words": st.column_config.NumberColumn("Words", format="%d"),
            "guessed": st.column_config.CheckboxColumn("Guessed", help="Checked when the number or date was not found and had to be assumed"),
        },
    )
    label = "Create minutes" if len(files) == 1 else f"Create minutes for {len(files)} meetings"
    if st.button(label, type="primary", key=f"go_{project.id}"):
        items: list[BatchItem] = []
        problems: list[str] = []
        for r in edited.to_dict("records"):
            number = int(r["meeting_no"]) if _s(r["meeting_no"]) else 0
            when = _to_date(r["meeting_date"])
            if number <= last_no:
                problems.append(f"{r['file']}: meeting {number} is already issued (last issued is {last_no}). Use Undo in 'Issued meetings' to redo it.")
            if when is None:
                problems.append(f"{r['file']}: needs a meeting date.")
            uploaded = next(f for f in files if f.name == r["file"])
            items.append(BatchItem(name=r["file"], transcript=transcript_for(uploaded), meeting_no=number, meeting_date=when or date.today()))
        if len({i.meeting_no for i in items}) != len(items):
            problems.append("Two files have the same meeting number.")
        if problems:
            for p in problems:
                st.error(p)
            return
        extractor = get_extractor()
        issued = []
        try:
            with st.status("Creating minutes…", expanded=True) as status:
                def progress(item):
                    status.write(f"Meeting {item.meeting_no} · {fmt_date(item.meeting_date)} · reading {item.name}")
                issued = process_batch(store, firm, project, items, extractor=extractor, output_dir=OUTPUT_DIR,
                                       meeting_time=project.meeting_time, location=project.location, on_progress=progress)
                status.update(label=f"Issued {len(issued)} meeting(s).", state="complete", expanded=False)
        except (ExtractionError, PipelineError) as exc:
            st.error(str(exc))
            if issued:
                st.info(f"{len(issued)} earlier meeting(s) in this batch were issued before the error.")
        if issued:
            st.session_state["results"] = [(i.meeting.id, i.flags) for i in issued]
            st.session_state["drop_gen"] = generation + 1
            st.rerun()


def show_results(firm: Firm, project: Project) -> None:
    results = st.session_state.get("results") or []
    shown = [(store.get_meeting(mid), flags) for mid, flags in results]
    shown = [(m, flags) for m, flags in shown if m is not None and m.project_id == project.id]
    if not shown:
        return
    fmt = firm.format
    for meeting, flags in shown:
        result = result_for_meeting(store, firm, project, meeting)
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 1.2, 1.4])
            c1.markdown(f"**Meeting {meeting.meeting_no} · {fmt_date(meeting.meeting_date, fmt.date_format)}** — "
                        f"{len(result.new_items)} new, {len(result.closed_this_meeting)} closed, {len(result.not_discussed)} carried, "
                        f"{len(result.overdue)} overdue")
            docx = _file_bytes(meeting.minutes_docx_path)
            xlsx = _file_bytes(meeting.items_log_xlsx_path)
            if docx:
                c2.download_button("Minutes (.docx)", docx, file_name=Path(meeting.minutes_docx_path).name, key=f"r_docx_{meeting.id}", width="stretch")
            if xlsx:
                c3.download_button("Open-items log (.xlsx)", xlsx, file_name=Path(meeting.items_log_xlsx_path).name, key=f"r_xlsx_{meeting.id}", width="stretch")
            if flags:
                with st.expander(f"Worth a look before sending ({len(flags)})"):
                    for f in flags:
                        st.markdown(f"- {f}")
            with st.expander("Preview"):
                st.markdown(render_markdown(firm, project, meeting, result))
    if st.button("Clear", key="results_clear"):
        st.session_state.pop("results", None)
        st.rerun()


# --------------------------------------------------------------------------
# open items + issued meetings
# --------------------------------------------------------------------------
def open_items(firm: Firm, project: Project) -> None:
    fmt = firm.format
    items = store.list_items(project.id)
    last = store.last_final_meeting(project.id)
    current_no = last.meeting_no if last else 0
    st.markdown("### Open items")
    if not items:
        st.caption("The log starts with the first meeting you drop.")
        return
    as_of = date.today()
    rows = tracker_rows(items, as_of=as_of, current_meeting_no=current_no)
    df = pd.DataFrame(rows)
    open_df = df[df.status != "closed"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Open", int((open_df.status == "open").sum()))
    c2.metric("Overdue today", int(open_df.overdue.sum()))
    c3.metric("On hold", int((open_df.status == "on_hold").sum()))
    c4.metric("Closed to date", int((df.status == "closed").sum()))

    show_closed = st.toggle("Show closed items", value=False, key="oi_closed")
    view = df if show_closed else open_df
    table = pd.DataFrame({
        "Item": view.item_number,
        "Description": view.description,
        "Responsible": view.responsible,
        "Due": view.due_date.map(lambda d: fmt_date(d, fmt.date_format)),
        "Status": view.apply(lambda r: fmt.status_labels.get("overdue", "OVERDUE") if r.overdue else fmt.status_labels.get(r.status, r.status), axis=1),
        "Mtgs open": view.meetings_open,
        "Latest update": view.last_update,
    })

    def _style(row):
        if row["Status"] == fmt.status_labels.get("overdue", "OVERDUE"):
            return ["background-color: #fdecec; color: #7a0000"] * len(row)
        if row["Status"] == fmt.status_labels.get("closed", "Closed"):
            return ["color: #808080"] * len(row)
        return [""] * len(row)

    st.dataframe(table.style.apply(_style, axis=1), hide_index=True, width="stretch", height=min(560, 60 + 36 * max(len(table), 1)),
                 column_config={"Description": st.column_config.TextColumn(width="large"), "Latest update": st.column_config.TextColumn(width="large"), "Item": st.column_config.TextColumn(width="small")})
    d1, d2, d3 = st.columns([1, 1, 4])
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    xlsx_path = render_xlsx(items, OUTPUT_DIR / f"{slugify(project.name)}_Open-Items_as-of_{as_of.isoformat()}.xlsx", fmt=fmt, as_of=as_of, meeting_no=current_no, project_name=project.name)
    d1.download_button("Log (.xlsx)", xlsx_path.read_bytes(), file_name=xlsx_path.name, key="oi_xlsx", width="stretch")
    d2.download_button("Log (.csv)", render_csv(items, fmt=fmt, as_of=as_of, meeting_no=current_no), file_name=f"{slugify(project.name)}_Open-Items.csv", key="oi_csv", width="stretch")

    with st.expander("Correct an item (for example, closed by email between meetings)"):
        editable = pd.DataFrame([
            {"item_number": i.item_number, "description": i.description, "responsible": i.responsible, "due_date": i.due_date, "status": i.status.value}
            for i in items if i.status != ItemStatus.CLOSED
        ], columns=["item_number", "description", "responsible", "due_date", "status"])
        edited = st.data_editor(
            editable, hide_index=True, key="oi_edit", width="stretch", disabled=["item_number"],
            column_config={
                "item_number": st.column_config.TextColumn("Item", width="small"),
                "description": st.column_config.TextColumn("Description", width="large"),
                "responsible": "Responsible",
                "due_date": st.column_config.DateColumn("Due", format="MM/DD/YYYY"),
                "status": st.column_config.SelectboxColumn("Status", options=["open", "on_hold", "closed"]),
            },
        )
        if st.button("Save corrections", key="oi_save"):
            by_number = {i.item_number: i for i in items}
            changed = 0
            for r in edited.to_dict("records"):
                item = by_number.get(_s(r["item_number"]))
                if item is None:
                    continue
                changes = []
                new_due = _to_date(r["due_date"])
                new_status = ItemStatus(_s(r["status"]) or "open")
                if _s(r["description"]) and _s(r["description"]) != item.description:
                    item.description = _s(r["description"]); changes.append("description")
                if _s(r["responsible"]) != item.responsible:
                    item.responsible = _s(r["responsible"]); changes.append("responsible")
                if new_due != item.due_date:
                    item.due_date = new_due; changes.append(f"due {fmt_date(new_due) or 'removed'}")
                if new_status != item.status:
                    item.status = new_status; changes.append(f"status {new_status.value}")
                    if new_status == ItemStatus.CLOSED:
                        item.closed_meeting_no, item.closed_date = current_no, as_of
                    else:
                        item.closed_meeting_no = item.closed_date = None
                if changes:
                    item.history.append(ItemHistoryEntry(meeting_no=current_no, date=as_of, note="Corrected between meetings: " + ", ".join(changes) + ".", status=item.status))
                    store.save_item(item)
                    changed += 1
            st.success(f"Saved {changed} item(s).")
            st.rerun()


def issued_meetings(firm: Firm, project: Project) -> None:
    finals = store.list_meetings(project.id, MeetingStatus.FINAL)
    if not finals:
        return
    fmt = firm.format
    with st.expander(f"Issued meetings ({len(finals)})"):
        for meeting in reversed(finals):
            c1, c2, c3 = st.columns([3, 1.2, 1.4])
            c1.markdown(f"Meeting {meeting.meeting_no} · {fmt_date(meeting.meeting_date, fmt.date_format)} · {meeting.source_name or 'pasted'}")
            docx = _file_bytes(meeting.minutes_docx_path)
            xlsx = _file_bytes(meeting.items_log_xlsx_path)
            if docx:
                c2.download_button("Minutes (.docx)", docx, file_name=Path(meeting.minutes_docx_path).name, key=f"h_docx_{meeting.id}", width="stretch")
            if xlsx:
                c3.download_button("Log (.xlsx)", xlsx, file_name=Path(meeting.items_log_xlsx_path).name, key=f"h_xlsx_{meeting.id}", width="stretch")
        st.divider()
        c1, c2 = st.columns([3, 1])
        confirm = c1.checkbox(f"Undo meeting {finals[-1].meeting_no} so I can drop its transcript again", key="undo_confirm")
        if c2.button("Undo last meeting", disabled=not confirm, key="undo_btn"):
            withdrawn = withdraw_last_meeting(store, firm, project)
            if withdrawn is not None:
                store.delete_meeting(withdrawn.id)
            st.session_state.pop("results", None)
            st.rerun()


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main() -> None:
    firm, project = top_bar()
    if project is None:
        st.markdown(
            "Drop an OAC meeting transcript and get back the issued minutes in your firm's format plus an "
            "open-items log that carries forward from meeting to meeting. Create a project (top right) or try the sample."
        )
        if not any(p.name == DEMO_PROJECT_NAME for p in store.list_projects()):
            if st.button("Try it with the sample project", type="primary"):
                for f in store.list_firms():          # drop the placeholder firm so the sample firm is the only one
                    if not store.list_projects(f.id):
                        store.delete_firm(f.id)
                with st.spinner("Processing three sample meetings…"):
                    demo_firm, demo_project, _ = load_demo_project(store, OUTPUT_DIR)
                st.session_state["project_id"] = demo_project.id
                st.session_state.pop("project_select", None)
                st.rerun()
        mode = f"Claude connected ({os.environ.get('OACMINUTES_MODEL', DEFAULT_MODEL)})" if credentials_present() else "Demo mode: no API key found, only the sample transcripts can be processed. Put your key in a .env file next to app.py."
        st.caption(mode)
        return

    last = store.last_final_meeting(project.id)
    open_count = sum(1 for i in store.list_items(project.id) if i.status != ItemStatus.CLOSED)
    status_bits = [firm.name, f"format: {firm.format.name}"]
    status_bits.append(f"last issued: Meeting {last.meeting_no} on {fmt_date(last.meeting_date, firm.format.date_format)} · {open_count} open items carry into the next one" if last else "no meetings issued yet")
    status_bits.append("Claude connected" if credentials_present() else "Demo mode (no API key)")
    st.caption(" · ".join(status_bits))

    show_results(firm, project)
    drop_zone(firm, project)
    st.divider()
    open_items(firm, project)
    issued_meetings(firm, project)
    st.caption(f"OAC Minutes v{__version__}")


main()

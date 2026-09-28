from datetime import date
from pathlib import Path

import pytest

from oacminutes.extract import MockExtractor
from oacminutes.models import ItemStatus, MeetingStatus
from oacminutes.pipeline import PipelineError, finalize, generate_draft, withdraw_last_meeting
from oacminutes.samples import load_demo_project, sample_transcript
from oacminutes.storage import Store


@pytest.fixture
def demo(tmp_path):
    store = Store(":memory:")
    firm, project, meetings = load_demo_project(store, tmp_path / "out")
    return store, firm, project, meetings, tmp_path / "out"


def test_demo_project_end_to_end(demo):
    store, firm, project, meetings, out = demo
    assert [m.meeting_no for m in meetings] == [1, 2, 3]
    assert all(m.status == MeetingStatus.FINAL for m in meetings)
    items = store.list_items(project.id)
    assert [i.item_number for i in items] == ["1.01", "1.02", "1.03", "1.04", "1.05", "1.06", "1.07", "2.01", "2.02", "2.03", "2.04", "3.01", "3.02", "3.03", "3.04"]
    status = {i.item_number: i.status for i in items}
    assert status["1.01"] == ItemStatus.CLOSED and status["1.03"] == ItemStatus.CLOSED
    assert status["1.02"] == ItemStatus.OPEN and status["1.05"] == ItemStatus.OPEN
    by = {i.item_number: i for i in items}
    # RFI 007 was skipped at meeting 2 and picked up at meeting 3
    assert [h.note for h in by["1.02"].history][1] == "Not discussed – carried forward."
    assert by["1.02"].last_discussed_meeting_no == 3 and by["1.02"].due_date == date(2026, 9, 17)
    # water tap: overdue at meeting 3 with no new date
    assert by["1.05"].due_date == date(2026, 9, 11) and by["1.05"].is_overdue(date(2026, 9, 15))
    # PCO 004 reassigned to the OPM
    assert by["2.02"].responsible == "OPM – D. Whitfield" and by["2.02"].due_date == date(2026, 9, 22)
    assert by["1.03"].closed_meeting_no == 2 and by["1.06"].closed_meeting_no == 3
    for meeting in meetings:
        assert Path(meeting.minutes_docx_path).exists()
        assert Path(meeting.items_log_xlsx_path).exists()
    assert sorted(p.name for p in out.iterdir())[0].startswith("Bramford-Fire-Station-Renovation-Addition_OAC-01_2026-09-01")


def test_meeting_three_result_flags(demo):
    store, firm, project, meetings, out = demo
    from oacminutes.pipeline import compute
    withdraw_last_meeting(store, firm, project)          # back to the state after meeting 2
    m3 = store.list_meetings(project.id)[-1]
    result = compute(store, firm, project, m3)
    assert [i.item_number for i in result.overdue] == ["1.05"]
    assert [i.item_number for i in result.closed_this_meeting] == ["1.01", "1.06", "1.07", "2.01", "2.03"]
    assert [i.item_number for i in result.new_items] == ["3.01", "3.02", "3.03", "3.04"]
    assert result.not_discussed == [] and result.warnings == []
    # closed at meeting 2 -> not on meeting 3's tracker
    assert "1.03" not in [i.item_number for i in result.active_items]
    assert "1.01" in [i.item_number for i in result.active_items]


def test_withdraw_and_refinalize(demo):
    store, firm, project, meetings, out = demo
    last = withdraw_last_meeting(store, firm, project)
    assert last.meeting_no == 3 and last.status == MeetingStatus.DRAFT
    items = store.list_items(project.id)
    assert len(items) == 11
    assert {i.item_number: i.status for i in items}["1.01"] == ItemStatus.OPEN
    meeting, result = finalize(store, firm, project, last, out)
    assert meeting.status == MeetingStatus.FINAL
    assert len(store.list_items(project.id)) == 15


def test_generate_rejects_out_of_order_meetings(demo):
    store, firm, project, meetings, out = demo
    with pytest.raises(PipelineError, match="already finalized"):
        generate_draft(store, firm, project, transcript="x", extractor=MockExtractor(), meeting_no=3, meeting_date=date(2026, 9, 22), source_name="oac_meeting_03.txt")
    with pytest.raises(PipelineError, match="empty"):
        generate_draft(store, firm, project, transcript="   ", extractor=MockExtractor(), meeting_no=4, meeting_date=date(2026, 9, 22))


def test_regenerating_a_draft_replaces_the_previous_draft(tmp_path):
    store = Store(":memory:")
    from oacminutes.samples import make_demo_firm, make_demo_project
    firm = store.save_firm(make_demo_firm())
    project = store.save_project(make_demo_project(firm))
    kwargs = dict(transcript=sample_transcript("oac_meeting_01.txt"), extractor=MockExtractor(), meeting_no=1, meeting_date=date(2026, 9, 1), source_name="oac_meeting_01.txt")
    first = generate_draft(store, firm, project, **kwargs)
    second = generate_draft(store, firm, project, **kwargs)
    drafts = store.list_meetings(project.id, MeetingStatus.DRAFT)
    assert [m.id for m in drafts] == [second.meeting.id]
    assert first.warnings == ["Engine 2 relocation (target 09/21) was discussed but deliberately not made an action item pending the Chief's confirmation of mutual aid coverage."]
    assert store.list_items(project.id) == []  # nothing committed until finalize


def test_result_for_meeting_matches_history(demo):
    store, firm, project, meetings, out = demo
    from oacminutes.pipeline import result_for_meeting
    r2 = result_for_meeting(store, firm, project, meetings[1])
    assert [i.item_number for i in r2.not_discussed] == ["1.02"]
    assert [i.item_number for i in r2.closed_this_meeting] == ["1.03", "1.04"]
    assert [i.item_number for i in r2.new_items] == ["2.01", "2.02", "2.03", "2.04"]
    r1 = result_for_meeting(store, firm, project, meetings[0])
    assert len(r1.items) == 7 and r1.closed_this_meeting == []

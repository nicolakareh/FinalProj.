from datetime import date

import pytest

from oacminutes.carryforward import (
    carry_forward,
    format_item_number,
    looks_like_duplicate,
    normalize_item_number,
    parse_item_number,
    tracker_rows,
)
from oacminutes.dates import parse_date
from oacminutes.models import (
    ItemStatus,
    MeetingExtraction,
    NewItem,
    NumberingSpec,
    PriorItemUpdate,
)

PID = "proj1"
M1 = date(2026, 9, 1)
M2 = date(2026, 9, 8)
M3 = date(2026, 9, 15)


def extraction(new=(), updates=()):
    return MeetingExtraction(new_items=list(new), prior_item_updates=list(updates))


def meeting_one():
    """Two items raised at meeting 1, one due before meeting 2."""
    ext = extraction(new=[
        NewItem(description="Submit revised baseline schedule", responsible="GC – J. Alvarez", due_date="2026-09-05", section_key="schedule"),
        NewItem(description="Issue RFI response on footing elevation", responsible="Architect – M. Chen", due_date="2026-09-12", section_key="rfis"),
    ])
    return carry_forward([], ext, project_id=PID, meeting_no=1, meeting_date=M1)


# ---------------------------------------------------------------- numbering
def test_numbering_styles():
    assert format_item_number(NumberingSpec(), 3, 4) == "3.04"
    assert format_item_number(NumberingSpec(separator="-", item_pad=3, prefix="OAC "), 12, 7) == "OAC 12-007"
    assert format_item_number(NumberingSpec(style="sequential", item_pad=3), 3, 4) == "004"


def test_parse_and_normalize_item_numbers():
    assert parse_item_number("3.04") == (3, 4)
    assert parse_item_number("OAC 12-007") == (12, 7)
    assert parse_item_number("004") == (0, 4)
    assert normalize_item_number("3.4") == normalize_item_number(" 3-04 ") == "3:4"


def test_sequential_numbering_continues_across_meetings():
    seq = NumberingSpec(style="sequential", item_pad=3)
    r1 = carry_forward([], extraction(new=[NewItem(description="A"), NewItem(description="B")]), project_id=PID, meeting_no=1, meeting_date=M1, numbering=seq)
    assert [i.item_number for i in r1.items] == ["001", "002"]
    r2 = carry_forward(r1.items, extraction(new=[NewItem(description="C")]), project_id=PID, meeting_no=2, meeting_date=M2, numbering=seq)
    assert [i.item_number for i in r2.items] == ["001", "002", "003"]


# ---------------------------------------------------------------- new items
def test_new_items_get_numbers_dates_and_history():
    r = meeting_one()
    assert [i.item_number for i in r.new_items] == ["1.01", "1.02"]
    first = r.new_items[0]
    assert first.date_raised == M1
    assert first.raised_meeting_no == 1
    assert first.due_date == date(2026, 9, 5)
    assert first.status == ItemStatus.OPEN
    assert first.history[0].note == "Raised."
    assert not r.warnings


def test_blank_new_items_are_skipped():
    r = carry_forward([], extraction(new=[NewItem(description="   ")]), project_id=PID, meeting_no=1, meeting_date=M1)
    assert r.items == []


def test_duplicate_new_item_is_flagged_not_blocked():
    r1 = meeting_one()
    r2 = carry_forward(r1.items, extraction(new=[NewItem(description="GC to submit the revised baseline schedule")]), project_id=PID, meeting_no=2, meeting_date=M2)
    assert len(r2.new_items) == 1
    assert any("looks like existing item 1.01" in w for w in r2.warnings)


def test_looks_like_duplicate():
    assert looks_like_duplicate("Submit revised baseline schedule", "GC to submit the revised baseline schedule")
    assert not looks_like_duplicate("Submit revised baseline schedule", "Order long-lead switchgear")


# ---------------------------------------------------------------- carry forward
def test_untouched_items_are_carried_forward_with_a_note():
    r1 = meeting_one()
    r2 = carry_forward(r1.items, extraction(), project_id=PID, meeting_no=2, meeting_date=M2)
    assert [i.item_number for i in r2.not_discussed] == ["1.01", "1.02"]
    assert r2.by_number()["1.01"].history[-1].note == "Not discussed – carried forward."
    assert r2.by_number()["1.01"].last_discussed_meeting_no == 1
    assert len(r2.active_items) == 2


def test_explicit_not_discussed_status_behaves_like_untouched():
    r1 = meeting_one()
    r2 = carry_forward(r1.items, extraction(updates=[PriorItemUpdate(item_number="1.01", status="not_discussed")]), project_id=PID, meeting_no=2, meeting_date=M2)
    assert [i.item_number for i in r2.not_discussed] == ["1.01", "1.02"]


def test_input_items_are_not_mutated():
    r1 = meeting_one()
    before = [i.model_copy(deep=True) for i in r1.items]
    carry_forward(r1.items, extraction(updates=[PriorItemUpdate(item_number="1.01", status="closed")]), project_id=PID, meeting_no=2, meeting_date=M2)
    assert r1.items == before


def test_closing_an_item_shows_it_once_then_drops_it():
    r1 = meeting_one()
    r2 = carry_forward(r1.items, extraction(updates=[PriorItemUpdate(item_number="1.01", status="closed", note="Schedule received 9/4; accepted.")]), project_id=PID, meeting_no=2, meeting_date=M2)
    closed = r2.by_number()["1.01"]
    assert closed.status == ItemStatus.CLOSED
    assert closed.closed_meeting_no == 2 and closed.closed_date == M2
    assert closed.history[-1].note == "Schedule received 9/4; accepted."
    assert [i.item_number for i in r2.closed_this_meeting] == ["1.01"]
    assert [i.item_number for i in r2.active_items] == ["1.01", "1.02"]  # shown once more

    r3 = carry_forward(r2.items, extraction(), project_id=PID, meeting_no=3, meeting_date=M3)
    assert [i.item_number for i in r3.active_items] == ["1.02"]          # then gone
    assert "1.01" in r3.by_number()                                        # but never deleted
    assert [i.item_number for i in r3.not_discussed] == ["1.02"]


def test_update_with_new_due_date_and_owner():
    r1 = meeting_one()
    upd = PriorItemUpdate(item_number="1.02", status="open", note="Architect needs survey first.", new_due_date="2026-09-19", new_responsible="Architect – R. Patel")
    r2 = carry_forward(r1.items, extraction(updates=[upd]), project_id=PID, meeting_no=2, meeting_date=M2)
    item = r2.by_number()["1.02"]
    assert item.due_date == date(2026, 9, 19)
    assert item.responsible == "Architect – R. Patel"
    assert item.last_discussed_meeting_no == 2
    assert "Due date revised to 09/19/2026." in item.history[-1].note
    assert "Reassigned to Architect – R. Patel." in item.history[-1].note
    assert item.history[-1].note.startswith("Architect needs survey first.")


def test_on_hold_status():
    r1 = meeting_one()
    r2 = carry_forward(r1.items, extraction(updates=[PriorItemUpdate(item_number="1.01", status="on_hold", note="Pending owner decision.")]), project_id=PID, meeting_no=2, meeting_date=M2)
    item = r2.by_number()["1.01"]
    assert item.status == ItemStatus.ON_HOLD
    assert not item.is_overdue(M3)  # on-hold items are not counted overdue


def test_overdue_is_computed_from_dates():
    r1 = meeting_one()
    r2 = carry_forward(r1.items, extraction(updates=[PriorItemUpdate(item_number="1.01", status="open", note="Still working on it.")]), project_id=PID, meeting_no=2, meeting_date=M2)
    assert [i.item_number for i in r2.overdue] == ["1.01"]   # due 9/5, meeting 9/8
    assert r2.by_number()["1.02"].is_overdue(M2) is False     # due 9/12


def test_reopening_a_closed_item():
    r1 = meeting_one()
    r2 = carry_forward(r1.items, extraction(updates=[PriorItemUpdate(item_number="1.01", status="closed")]), project_id=PID, meeting_no=2, meeting_date=M2)
    r3 = carry_forward(r2.items, extraction(updates=[PriorItemUpdate(item_number="1.01", status="open", note="Schedule rejected by Owner; resubmit.")]), project_id=PID, meeting_no=3, meeting_date=M3)
    item = r3.by_number()["1.01"]
    assert item.status == ItemStatus.OPEN and item.closed_meeting_no is None
    assert [i.item_number for i in r3.reopened] == ["1.01"]
    assert item.history[-1].note.startswith("Reopened.")
    assert "1.01" in [i.item_number for i in r3.active_items]


def test_closing_an_already_closed_item_warns():
    r1 = meeting_one()
    r2 = carry_forward(r1.items, extraction(updates=[PriorItemUpdate(item_number="1.01", status="closed")]), project_id=PID, meeting_no=2, meeting_date=M2)
    r3 = carry_forward(r2.items, extraction(updates=[PriorItemUpdate(item_number="1.01", status="closed")]), project_id=PID, meeting_no=3, meeting_date=M3)
    assert any("already closed" in w for w in r3.warnings)
    assert r3.closed_this_meeting == []


def test_unknown_item_number_warns_and_continues():
    r1 = meeting_one()
    r2 = carry_forward(r1.items, extraction(updates=[PriorItemUpdate(item_number="9.99", status="closed")]), project_id=PID, meeting_no=2, meeting_date=M2)
    assert any("9.99" in w for w in r2.warnings)
    assert len(r2.active_items) == 2


def test_second_update_for_same_item_is_ignored_with_warning():
    r1 = meeting_one()
    updates = [PriorItemUpdate(item_number="1.01", status="closed"), PriorItemUpdate(item_number="1.1", status="open")]
    r2 = carry_forward(r1.items, extraction(updates=updates), project_id=PID, meeting_no=2, meeting_date=M2)
    assert r2.by_number()["1.01"].status == ItemStatus.CLOSED
    assert any("updated twice" in w for w in r2.warnings)


def test_bad_due_date_is_reported_not_fatal():
    r = carry_forward([], extraction(new=[NewItem(description="X", due_date="sometime next week")]), project_id=PID, meeting_no=1, meeting_date=M1)
    assert r.items[0].due_date is None
    assert any("Could not read due date" in w for w in r.warnings)


def test_items_are_sorted_by_number():
    r1 = meeting_one()
    r2 = carry_forward(r1.items, extraction(new=[NewItem(description="Z")]), project_id=PID, meeting_no=2, meeting_date=M2)
    assert [i.item_number for i in r2.items] == ["1.01", "1.02", "2.01"]


def test_tracker_rows_flags():
    r1 = meeting_one()
    rows = tracker_rows(r1.items, as_of=date(2026, 9, 10), current_meeting_no=2)
    first = rows[0]
    assert first["item_number"] == "1.01"
    assert first["overdue"] is True and first["days_overdue"] == 5
    assert first["meetings_open"] == 1
    assert rows[1]["overdue"] is False


# ---------------------------------------------------------------- dates
@pytest.mark.parametrize("raw,expected", [
    ("2026-10-06", date(2026, 10, 6)),
    ("2026-10-06T09:00:00", date(2026, 10, 6)),
    ("10/6/2026", date(2026, 10, 6)),
    ("10/6/26", date(2026, 10, 6)),
    ("10-06-2026", date(2026, 10, 6)),
    ("10/6", date(2026, 10, 6)),
    ("October 6, 2026", date(2026, 10, 6)),
    ("Oct 6", date(2026, 10, 6)),
    ("6 October 2026", date(2026, 10, 6)),
    ("Sept 30, 2026", date(2026, 9, 30)),
    ("TBD", None),
    ("", None),
    (None, None),
    ("2026-02-30", None),
    ("next week", None),
])
def test_parse_date(raw, expected):
    assert parse_date(raw, default_year=2026) == expected


def test_parse_date_without_year_and_no_default():
    assert parse_date("10/6") is None

from datetime import date

from oacminutes.models import Firm, ItemStatus, Meeting, MeetingExtraction, MeetingStatus, OpenItem, Project
from oacminutes.storage import Store


def make_store():
    return Store(":memory:")


def test_firm_project_roundtrip():
    store = make_store()
    firm = store.save_firm(Firm(name="Acme OPM"))
    project = store.save_project(Project(firm_id=firm.id, name="Library Renovation", number="24-101"))
    assert store.get_firm(firm.id).name == "Acme OPM"
    assert store.list_firms()[0].id == firm.id
    assert store.get_project(project.id).number == "24-101"
    assert [p.id for p in store.list_projects(firm.id)] == [project.id]
    project.number = "24-102"
    store.save_project(project)
    assert store.get_project(project.id).number == "24-102"


def test_meetings_and_numbering():
    store = make_store()
    firm = store.save_firm(Firm(name="Acme OPM"))
    project = store.save_project(Project(firm_id=firm.id, name="P"))
    assert store.next_meeting_no(project.id) == 1
    m1 = store.save_meeting(Meeting(project_id=project.id, meeting_no=1, meeting_date=date(2026, 9, 1), status=MeetingStatus.FINAL, extraction=MeetingExtraction()))
    m2 = store.save_meeting(Meeting(project_id=project.id, meeting_no=2, meeting_date=date(2026, 9, 8), transcript="hello"))
    assert store.next_meeting_no(project.id) == 3
    assert store.last_final_meeting(project.id).id == m1.id
    assert [m.meeting_no for m in store.list_meetings(project.id)] == [1, 2]
    assert store.get_meeting(m2.id).transcript == "hello"
    assert store.get_meeting(m1.id).extraction is not None
    m2.status = MeetingStatus.FINAL
    store.save_meeting(m2)
    assert store.last_final_meeting(project.id).id == m2.id
    store.delete_meeting(m2.id)
    assert store.next_meeting_no(project.id) == 2


def test_items_replace_and_sort():
    store = make_store()
    firm = store.save_firm(Firm(name="Acme OPM"))
    project = store.save_project(Project(firm_id=firm.id, name="P"))

    def item(number, status=ItemStatus.OPEN):
        return OpenItem(project_id=project.id, item_number=number, description=f"Item {number}", date_raised=date(2026, 9, 1), raised_meeting_no=1, last_discussed_meeting_no=1, status=status)

    store.replace_items(project.id, [item("2.01"), item("1.02", ItemStatus.CLOSED), item("1.01")])
    numbers = [i.item_number for i in store.list_items(project.id)]
    assert numbers == ["1.01", "1.02", "2.01"]
    store.replace_items(project.id, [item("1.01")])
    assert len(store.list_items(project.id)) == 1
    one = store.list_items(project.id)[0]
    one.responsible = "GC"
    store.save_item(one)
    assert store.list_items(project.id)[0].responsible == "GC"


def test_cascade_delete():
    store = make_store()
    firm = store.save_firm(Firm(name="Acme OPM"))
    project = store.save_project(Project(firm_id=firm.id, name="P"))
    store.save_meeting(Meeting(project_id=project.id, meeting_no=1, meeting_date=date(2026, 9, 1)))
    store.replace_items(project.id, [OpenItem(project_id=project.id, item_number="1.01", description="x", date_raised=date(2026, 9, 1), raised_meeting_no=1, last_discussed_meeting_no=1)])
    store.delete_firm(firm.id)
    assert store.list_projects() == []
    assert store.list_meetings(project.id) == []
    assert store.list_items(project.id) == []


def test_file_backed_store(tmp_path):
    path = tmp_path / "nested" / "app.db"
    store = Store(path)
    store.save_firm(Firm(name="Persisted"))
    store.close()
    again = Store(path)
    assert again.list_firms()[0].name == "Persisted"

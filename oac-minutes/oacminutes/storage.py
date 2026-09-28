"""SQLite persistence. One file, four tables, JSON documents inside.

The schema is intentionally boring so the app can later move to Postgres
behind the same Store interface.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .models import Firm, Meeting, MeetingStatus, OpenItem, Project

SCHEMA = """
CREATE TABLE IF NOT EXISTS firms (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    firm_id TEXT NOT NULL REFERENCES firms(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meetings (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    meeting_no INTEGER NOT NULL,
    meeting_date TEXT NOT NULL,
    status TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(project_id, meeting_no)
);
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    item_number TEXT NOT NULL,
    status TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_project ON items(project_id);
CREATE INDEX IF NOT EXISTS idx_meetings_project ON meetings(project_id, meeting_no);
"""


def _dump(model) -> str:
    return json.dumps(model.model_dump(mode="json"))


class Store:
    def __init__(self, db_path: str | Path = ":memory:"):
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # ------------------------------------------------------------ firms
    def save_firm(self, firm: Firm) -> Firm:
        self.conn.execute(
            "INSERT INTO firms (id, name, data, created_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name = excluded.name, data = excluded.data",
            (firm.id, firm.name, _dump(firm), firm.created_at.isoformat()),
        )
        self.conn.commit()
        return firm

    def get_firm(self, firm_id: str) -> Firm | None:
        row = self.conn.execute("SELECT data FROM firms WHERE id = ?", (firm_id,)).fetchone()
        return Firm.model_validate_json(row["data"]) if row else None

    def list_firms(self) -> list[Firm]:
        rows = self.conn.execute("SELECT data FROM firms ORDER BY name").fetchall()
        return [Firm.model_validate_json(r["data"]) for r in rows]

    def delete_firm(self, firm_id: str) -> None:
        self.conn.execute("DELETE FROM firms WHERE id = ?", (firm_id,))
        self.conn.commit()

    # ------------------------------------------------------------ projects
    def save_project(self, project: Project) -> Project:
        self.conn.execute(
            "INSERT INTO projects (id, firm_id, name, data, created_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET firm_id = excluded.firm_id, name = excluded.name, data = excluded.data",
            (project.id, project.firm_id, project.name, _dump(project), project.created_at.isoformat()),
        )
        self.conn.commit()
        return project

    def get_project(self, project_id: str) -> Project | None:
        row = self.conn.execute("SELECT data FROM projects WHERE id = ?", (project_id,)).fetchone()
        return Project.model_validate_json(row["data"]) if row else None

    def list_projects(self, firm_id: str | None = None) -> list[Project]:
        if firm_id is None:
            rows = self.conn.execute("SELECT data FROM projects ORDER BY name").fetchall()
        else:
            rows = self.conn.execute("SELECT data FROM projects WHERE firm_id = ? ORDER BY name", (firm_id,)).fetchall()
        return [Project.model_validate_json(r["data"]) for r in rows]

    def delete_project(self, project_id: str) -> None:
        self.conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        self.conn.commit()

    # ------------------------------------------------------------ meetings
    def save_meeting(self, meeting: Meeting) -> Meeting:
        self.conn.execute(
            "INSERT INTO meetings (id, project_id, meeting_no, meeting_date, status, data, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET meeting_no = excluded.meeting_no, meeting_date = excluded.meeting_date, "
            "status = excluded.status, data = excluded.data",
            (meeting.id, meeting.project_id, meeting.meeting_no, meeting.meeting_date.isoformat(),
             meeting.status.value, _dump(meeting), meeting.created_at.isoformat()),
        )
        self.conn.commit()
        return meeting

    def get_meeting(self, meeting_id: str) -> Meeting | None:
        row = self.conn.execute("SELECT data FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
        return Meeting.model_validate_json(row["data"]) if row else None

    def list_meetings(self, project_id: str, status: MeetingStatus | None = None) -> list[Meeting]:
        if status is None:
            rows = self.conn.execute("SELECT data FROM meetings WHERE project_id = ? ORDER BY meeting_no", (project_id,)).fetchall()
        else:
            rows = self.conn.execute("SELECT data FROM meetings WHERE project_id = ? AND status = ? ORDER BY meeting_no", (project_id, status.value)).fetchall()
        return [Meeting.model_validate_json(r["data"]) for r in rows]

    def last_final_meeting(self, project_id: str) -> Meeting | None:
        meetings = self.list_meetings(project_id, MeetingStatus.FINAL)
        return meetings[-1] if meetings else None

    def next_meeting_no(self, project_id: str) -> int:
        row = self.conn.execute("SELECT MAX(meeting_no) AS n FROM meetings WHERE project_id = ?", (project_id,)).fetchone()
        return (row["n"] or 0) + 1

    def delete_meeting(self, meeting_id: str) -> None:
        self.conn.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))
        self.conn.commit()

    # ------------------------------------------------------------ items
    def replace_items(self, project_id: str, items: Iterable[OpenItem]) -> None:
        """Atomically replace the project's item list (used when a meeting is finalized)."""
        with self.conn:
            self.conn.execute("DELETE FROM items WHERE project_id = ?", (project_id,))
            self.conn.executemany(
                "INSERT INTO items (id, project_id, item_number, status, data) VALUES (?, ?, ?, ?, ?)",
                [(i.id, project_id, i.item_number, i.status.value, _dump(i)) for i in items],
            )

    def list_items(self, project_id: str) -> list[OpenItem]:
        rows = self.conn.execute("SELECT data FROM items WHERE project_id = ?", (project_id,)).fetchall()
        items = [OpenItem.model_validate_json(r["data"]) for r in rows]
        from .carryforward import parse_item_number
        return sorted(items, key=lambda i: parse_item_number(i.item_number))

    def save_item(self, item: OpenItem) -> OpenItem:
        self.conn.execute(
            "INSERT INTO items (id, project_id, item_number, status, data) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET item_number = excluded.item_number, status = excluded.status, data = excluded.data",
            (item.id, item.project_id, item.item_number, item.status.value, _dump(item)),
        )
        self.conn.commit()
        return item

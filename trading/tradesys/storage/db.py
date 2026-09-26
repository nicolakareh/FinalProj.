"""SQLite persistence for sources, signals, trades, risk state, backtests, news and alerts.

Everything the risk manager needs to survive a restart (halts, kill state, arm state)
lives here, so a crash and relaunch cannot silently reset a weekly halt.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable

from ..common import ensure_dir, to_iso, utcnow

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    disabled_reason TEXT,
    disabled_at TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
    source_id TEXT PRIMARY KEY,
    backtest_id TEXT,
    code_hash TEXT,
    approved_at TEXT NOT NULL,
    note TEXT
);
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry REAL,
    stop REAL,
    target REAL,
    signal_time TEXT NOT NULL,
    raw_text TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    status_reason TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    signal_id INTEGER,
    symbol TEXT NOT NULL,
    mode TEXT NOT NULL,
    qty REAL NOT NULL,
    entry_price REAL,
    stop_price REAL,
    target_price REAL,
    entry_time TEXT,
    exit_price REAL,
    exit_time TEXT,
    exit_reason TEXT,
    pnl REAL,
    fees REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    entry_order_id TEXT,
    stop_order_id TEXT,
    target_order_id TEXT,
    exit_order_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS trades_source_idx ON trades(source_id, status);
CREATE INDEX IF NOT EXISTS trades_symbol_idx ON trades(symbol, status);
CREATE TABLE IF NOT EXISTS risk_state (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS backtests (
    id TEXT PRIMARY KEY,
    strategy TEXT NOT NULL,
    symbols TEXT NOT NULL,
    timeframe TEXT,
    start TEXT,
    end TEXT,
    params_json TEXT,
    results_json TEXT NOT NULL,
    code_hash TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS news_items (
    id TEXT PRIMARY KEY,
    article_id TEXT,
    symbol TEXT,
    headline TEXT,
    source TEXT,
    url TEXT,
    published_at TEXT,
    sentiment REAL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS news_symbol_time ON news_items(symbol, published_at);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,
    message TEXT NOT NULL,
    channels TEXT
);
CREATE TABLE IF NOT EXISTS order_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    trade_id INTEGER,
    broker_order_id TEXT,
    client_order_id TEXT,
    symbol TEXT,
    side TEXT,
    qty REAL,
    order_type TEXT,
    status TEXT,
    payload_json TEXT
);
CREATE TABLE IF NOT EXISTS equity_snapshots (
    ts TEXT PRIMARY KEY,
    equity REAL NOT NULL,
    cash REAL NOT NULL,
    mode TEXT NOT NULL
);
"""


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return None if row is None else {k: row[k] for k in row.keys()}


class Database:
    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        if self.path != ":memory:":
            ensure_dir(Path(self.path).parent)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        if self.path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)

    # ------------------------------------------------------------------ core
    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, tuple(params))

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            return [_row_to_dict(r) for r in cur.fetchall()]  # type: ignore[misc]

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            return _row_to_dict(cur.fetchone())

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # --------------------------------------------------------------- sources
    def upsert_source(self, source_id: str, kind: str, name: str) -> dict[str, Any]:
        now = to_iso(utcnow())
        self.execute(
            "INSERT INTO sources(id, kind, name, status, created_at) VALUES (?,?,?,'active',?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name",
            (source_id, kind, name, now),
        )
        return self.get_source(source_id)  # type: ignore[return-value]

    def get_source(self, source_id: str) -> dict[str, Any] | None:
        return self.query_one("SELECT * FROM sources WHERE id=?", (source_id,))

    def list_sources(self) -> list[dict[str, Any]]:
        return self.query("SELECT * FROM sources ORDER BY kind, name")

    def set_source_status(self, source_id: str, status: str, reason: str | None = None) -> None:
        now = to_iso(utcnow())
        if status == "disabled":
            self.execute("UPDATE sources SET status=?, disabled_reason=?, disabled_at=? WHERE id=?",
                         (status, reason, now, source_id))
        else:
            self.execute("UPDATE sources SET status=?, disabled_reason=NULL, disabled_at=NULL WHERE id=?",
                         (status, source_id))

    # ------------------------------------------------------------- approvals
    def set_approval(self, source_id: str, backtest_id: str | None, code_hash: str | None, note: str = "") -> None:
        self.execute(
            "INSERT INTO approvals(source_id, backtest_id, code_hash, approved_at, note) VALUES (?,?,?,?,?) "
            "ON CONFLICT(source_id) DO UPDATE SET backtest_id=excluded.backtest_id, code_hash=excluded.code_hash, "
            "approved_at=excluded.approved_at, note=excluded.note",
            (source_id, backtest_id, code_hash, to_iso(utcnow()), note),
        )

    def get_approval(self, source_id: str) -> dict[str, Any] | None:
        return self.query_one("SELECT * FROM approvals WHERE source_id=?", (source_id,))

    def delete_approval(self, source_id: str) -> None:
        self.execute("DELETE FROM approvals WHERE source_id=?", (source_id,))

    def list_approvals(self) -> list[dict[str, Any]]:
        return self.query("SELECT * FROM approvals ORDER BY source_id")

    # --------------------------------------------------------------- signals
    def insert_signal(self, source_id: str, symbol: str, direction: str, entry: float | None, stop: float | None,
                      target: float | None, signal_time, raw_text: str | None, status: str = "new",
                      status_reason: str | None = None) -> int:
        cur = self.execute(
            "INSERT INTO signals(source_id, symbol, direction, entry, stop, target, signal_time, raw_text, status, "
            "status_reason, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (source_id, symbol, direction, entry, stop, target, to_iso(signal_time), raw_text, status,
             status_reason, to_iso(utcnow())),
        )
        return int(cur.lastrowid)

    def set_signal_status(self, signal_id: int, status: str, reason: str | None = None) -> None:
        self.execute("UPDATE signals SET status=?, status_reason=? WHERE id=?", (status, reason, signal_id))

    def list_signals(self, source_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if source_id:
            return self.query("SELECT * FROM signals WHERE source_id=? ORDER BY id DESC LIMIT ?", (source_id, limit))
        return self.query("SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,))

    # ---------------------------------------------------------------- trades
    def insert_trade(self, **fields: Any) -> int:
        now = to_iso(utcnow())
        fields.setdefault("status", "pending")
        fields.setdefault("fees", 0.0)
        fields["created_at"] = now
        fields["updated_at"] = now
        for k in ("entry_time", "exit_time"):
            if k in fields and fields[k] is not None and not isinstance(fields[k], str):
                fields[k] = to_iso(fields[k])
        cols = ", ".join(fields.keys())
        marks = ", ".join("?" for _ in fields)
        cur = self.execute(f"INSERT INTO trades({cols}) VALUES ({marks})", tuple(fields.values()))
        return int(cur.lastrowid)

    def update_trade(self, trade_id: int, **fields: Any) -> None:
        if not fields:
            return
        for k in ("entry_time", "exit_time"):
            if k in fields and fields[k] is not None and not isinstance(fields[k], str):
                fields[k] = to_iso(fields[k])
        fields["updated_at"] = to_iso(utcnow())
        sets = ", ".join(f"{k}=?" for k in fields)
        self.execute(f"UPDATE trades SET {sets} WHERE id=?", (*fields.values(), trade_id))

    def get_trade(self, trade_id: int) -> dict[str, Any] | None:
        return self.query_one("SELECT * FROM trades WHERE id=?", (trade_id,))

    def find_trade_by_order(self, order_id: str) -> dict[str, Any] | None:
        return self.query_one(
            "SELECT * FROM trades WHERE entry_order_id=? OR stop_order_id=? OR target_order_id=? OR exit_order_id=? "
            "ORDER BY id DESC LIMIT 1",
            (order_id, order_id, order_id, order_id),
        )

    def list_trades(self, source_id: str | None = None, status: str | None = None, mode: str | None = None,
                    since: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM trades WHERE 1=1"
        params: list[Any] = []
        if source_id:
            sql += " AND source_id=?"
            params.append(source_id)
        if status:
            sql += " AND status=?"
            params.append(status)
        if mode:
            sql += " AND mode=?"
            params.append(mode)
        if since:
            sql += " AND COALESCE(exit_time, entry_time, created_at) >= ?"
            params.append(since)
        sql += " ORDER BY id ASC"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        return self.query(sql, params)

    def open_trades(self, mode: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM trades WHERE status IN ('open','pending')"
        params: list[Any] = []
        if mode:
            sql += " AND mode=?"
            params.append(mode)
        return self.query(sql + " ORDER BY id", params)

    def closed_trades_for_source(self, source_id: str, limit: int | None = None,
                                 modes: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
        """Most recent closed trades first."""
        sql = "SELECT * FROM trades WHERE source_id=? AND status='closed'"
        params: list[Any] = [source_id]
        if modes:
            sql += " AND mode IN (%s)" % ",".join("?" for _ in modes)
            params.extend(modes)
        sql += " ORDER BY exit_time DESC, id DESC"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        return self.query(sql, params)

    def realized_pnl_since(self, since_iso: str, modes: tuple[str, ...]) -> tuple[float, float]:
        """Return (net pnl, fees) of trades closed at or after since_iso, for the given modes."""
        marks = ",".join("?" for _ in modes)
        row = self.query_one(
            f"SELECT COALESCE(SUM(pnl),0) AS pnl, COALESCE(SUM(fees),0) AS fees FROM trades "
            f"WHERE status='closed' AND exit_time >= ? AND mode IN ({marks})",
            (since_iso, *modes),
        )
        return float(row["pnl"]), float(row["fees"])  # type: ignore[index]

    def count_orders_since(self, since_iso: str) -> int:
        row = self.query_one("SELECT COUNT(*) AS n FROM order_log WHERE ts >= ? AND side='buy'", (since_iso,))
        return int(row["n"])  # type: ignore[index]

    # ------------------------------------------------------------ risk state
    def get_state(self, key: str, default: str | None = None) -> str | None:
        row = self.query_one("SELECT value FROM risk_state WHERE key=?", (key,))
        return default if row is None else row["value"]

    def set_state(self, key: str, value: str | None) -> None:
        self.execute(
            "INSERT INTO risk_state(key, value, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, to_iso(utcnow())),
        )

    def all_state(self) -> dict[str, str | None]:
        return {r["key"]: r["value"] for r in self.query("SELECT key, value FROM risk_state")}

    # ------------------------------------------------------------- backtests
    def save_backtest(self, backtest_id: str, strategy: str, symbols: list[str], timeframe: str, start: str,
                      end: str, params: dict, results: dict, code_hash: str) -> None:
        self.execute(
            "INSERT OR REPLACE INTO backtests(id, strategy, symbols, timeframe, start, end, params_json, results_json, "
            "code_hash, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (backtest_id, strategy, ",".join(symbols), timeframe, start, end, json.dumps(params, default=str),
             json.dumps(results, default=str), code_hash, to_iso(utcnow())),
        )

    def get_backtest(self, backtest_id: str) -> dict[str, Any] | None:
        row = self.query_one("SELECT * FROM backtests WHERE id=?", (backtest_id,))
        if row:
            row["params"] = json.loads(row["params_json"] or "{}")
            row["results"] = json.loads(row["results_json"])
        return row

    def list_backtests(self, strategy: str | None = None) -> list[dict[str, Any]]:
        if strategy:
            rows = self.query("SELECT * FROM backtests WHERE strategy=? ORDER BY created_at DESC", (strategy,))
        else:
            rows = self.query("SELECT * FROM backtests ORDER BY created_at DESC")
        for row in rows:
            row["results"] = json.loads(row["results_json"])
        return rows

    # ------------------------------------------------------------------ news
    def insert_news(self, item_id: str, article_id: str, symbol: str, headline: str, source: str, url: str,
                    published_at, sentiment: float) -> bool:
        cur = self.execute(
            "INSERT OR IGNORE INTO news_items(id, article_id, symbol, headline, source, url, published_at, sentiment, "
            "created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (item_id, article_id, symbol, headline, source, url, to_iso(published_at), sentiment, to_iso(utcnow())),
        )
        return cur.rowcount > 0

    def news_since(self, symbol: str, since_iso: str) -> list[dict[str, Any]]:
        return self.query("SELECT * FROM news_items WHERE symbol=? AND published_at >= ? ORDER BY published_at",
                          (symbol, since_iso))

    def news_counts_by_hour(self, symbol: str, since_iso: str) -> dict[str, int]:
        rows = self.query(
            "SELECT substr(published_at, 1, 13) AS hour, COUNT(*) AS n FROM news_items "
            "WHERE symbol=? AND published_at >= ? GROUP BY hour",
            (symbol, since_iso),
        )
        return {r["hour"]: int(r["n"]) for r in rows}

    # ---------------------------------------------------------------- alerts
    def log_alert(self, kind: str, message: str, channels: list[str]) -> None:
        self.execute("INSERT INTO alerts(ts, kind, message, channels) VALUES (?,?,?,?)",
                     (to_iso(utcnow()), kind, message, ",".join(channels)))

    def recent_alerts(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.query("SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,))

    def log_order(self, trade_id: int | None, broker_order_id: str | None, client_order_id: str | None, symbol: str,
                  side: str, qty: float, order_type: str, status: str, payload: dict | None = None) -> None:
        self.execute(
            "INSERT INTO order_log(ts, trade_id, broker_order_id, client_order_id, symbol, side, qty, order_type, "
            "status, payload_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (to_iso(utcnow()), trade_id, broker_order_id, client_order_id, symbol, side, qty, order_type, status,
             json.dumps(payload or {}, default=str)),
        )

    def snapshot_equity(self, equity: float, cash: float, mode: str) -> None:
        self.execute("INSERT OR REPLACE INTO equity_snapshots(ts, equity, cash, mode) VALUES (?,?,?,?)",
                     (to_iso(utcnow()), equity, cash, mode))

    def equity_history(self, mode: str, since_iso: str | None = None) -> list[dict[str, Any]]:
        if since_iso:
            return self.query("SELECT * FROM equity_snapshots WHERE mode=? AND ts>=? ORDER BY ts", (mode, since_iso))
        return self.query("SELECT * FROM equity_snapshots WHERE mode=? ORDER BY ts", (mode,))

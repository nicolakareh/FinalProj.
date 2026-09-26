from datetime import timedelta

from tradesys.common import to_iso, utcnow


def test_sources_and_approvals(db):
    db.upsert_source("strategy:x", "strategy", "x")
    assert db.get_source("strategy:x")["status"] == "active"
    db.set_source_status("strategy:x", "disabled", "negative")
    assert db.get_source("strategy:x")["disabled_reason"] == "negative"
    db.set_approval("strategy:x", "bt1", "hash", "ok")
    assert db.get_approval("strategy:x")["backtest_id"] == "bt1"
    db.delete_approval("strategy:x")
    assert db.get_approval("strategy:x") is None


def test_trades_roundtrip_and_pnl(db):
    now = utcnow()
    t1 = db.insert_trade(source_id="s", symbol="SPY", mode="paper", qty=1, entry_price=100, stop_price=95,
                         status="open", entry_time=now)
    db.update_trade(t1, status="closed", exit_price=110, exit_time=now, pnl=10.0, fees=0.5, exit_reason="target")
    t2 = db.insert_trade(source_id="s", symbol="SPY", mode="paper", qty=1, entry_price=100, stop_price=95,
                         status="closed", entry_time=now, exit_time=now, pnl=-5.0, fees=0.5)
    pnl, fees = db.realized_pnl_since(to_iso(now - timedelta(hours=1)), ("paper",))
    assert pnl == 5.0 and fees == 1.0
    recent = db.closed_trades_for_source("s", limit=1)
    assert recent[0]["id"] == t2
    assert db.find_trade_by_order("nope") is None
    db.update_trade(t1, stop_order_id="abc")
    assert db.find_trade_by_order("abc")["id"] == t1


def test_state_and_news(db):
    db.set_state("killed", "1")
    assert db.get_state("killed") == "1"
    db.set_state("killed", None)
    assert db.get_state("killed") is None
    now = utcnow()
    assert db.insert_news("a:AAPL", "a", "AAPL", "h", "src", "u", now, 0.2)
    assert not db.insert_news("a:AAPL", "a", "AAPL", "h", "src", "u", now, 0.2)
    counts = db.news_counts_by_hour("AAPL", to_iso(now - timedelta(days=1)))
    assert sum(counts.values()) == 1

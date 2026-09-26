from pathlib import Path

import pytest

from tradesys.alerts import Notifier
from tradesys.config import StrategyConfig
from tradesys.execution.approvals import ApprovalError, ApprovalRegistry
from tradesys.execution.fake_broker import FakeBroker
from tradesys.execution.models import OrderIntent
from tradesys.risk.kill_switch import KillSwitch
from tradesys.risk.manager import RiskManager
from tradesys.strategies import strategy_code_hash


def _buy(rm, broker, symbol, qty, price, stop, target=None):
    it = OrderIntent(symbol, "buy", qty, "market", price, "strategy:x", "t", f"c-{symbol}", stop, target)
    d = rm.evaluate(it, broker.get_account(), broker.get_positions(), broker.get_open_orders(), broker.get_asset(symbol),
                    broker.get_clock())
    assert d.allowed, d
    return broker.submit(d.approval)


def test_kill_switch_cancels_flattens_and_persists(settings, db):
    notifier = Notifier(settings, db, sync=True)
    rm = RiskManager(settings, db, notifier)
    broker = FakeBroker(cash=10_000, prices={"AAPL": 100.0, "MSFT": 50.0})
    _buy(rm, broker, "AAPL", 10, 100.0, 95.0, 110.0)   # filled + 2 legs open
    _buy(rm, broker, "MSFT", 20, 50.0, 48.0)           # filled + stop leg open
    assert len(broker.get_open_orders()) == 3 and len(broker.positions) == 2
    ks = KillSwitch(settings, db, broker, rm, notifier)
    res = ks.trigger("test", flatten=True)
    assert res["orders_cancelled"] == 3 and res["positions_closed"] == 2 and not res["errors"]
    assert broker.get_open_orders() == [] and broker.positions == {}
    assert rm.is_killed() and notifier.sent[-1][0] == "KILL"
    # persisted: a fresh RiskManager on the same db still sees the kill
    assert RiskManager(settings, db).is_killed()
    # file trigger
    assert not ks.file_triggered()
    Path(settings.kill_file).write_text("stop")
    assert ks.file_triggered()
    # idempotent
    assert ks.trigger("again")["orders_cancelled"] == 0


def test_kill_without_flatten_keeps_positions(settings, db):
    rm = RiskManager(settings, db)
    broker = FakeBroker(cash=10_000, prices={"AAPL": 100.0})
    _buy(rm, broker, "AAPL", 10, 100.0, 95.0, 110.0)
    res = KillSwitch(settings, db, broker, rm).trigger("t", flatten=False)
    assert res["orders_cancelled"] == 2 and len(broker.positions) == 1


def test_strategy_approval_requires_valid_backtest(db):
    reg = ApprovalRegistry(db)
    cfg = StrategyConfig("sma_crossover", ("SPY",), "1Day", {"fast": 10, "slow": 30})
    with pytest.raises(ApprovalError, match="not found"):
        reg.approve_strategy(cfg, "nope")
    h = strategy_code_hash(cfg.name, cfg.params)
    db.save_backtest("bt-short", "sma_crossover", ["SPY"], "1Day", "a", "b", cfg.params, {"sufficient_history": False}, h)
    with pytest.raises(ApprovalError, match="less than 2 years"):
        reg.approve_strategy(cfg, "bt-short")
    db.save_backtest("bt-stale", "sma_crossover", ["SPY"], "1Day", "a", "b", cfg.params, {"sufficient_history": True}, "old")
    with pytest.raises(ApprovalError, match="changed"):
        reg.approve_strategy(cfg, "bt-stale")
    db.save_backtest("bt-other", "rsi_reversion", ["SPY"], "1Day", "a", "b", {}, {"sufficient_history": True}, h)
    with pytest.raises(ApprovalError, match="is for rsi_reversion"):
        reg.approve_strategy(cfg, "bt-other")
    db.save_backtest("bt-ok", "sma_crossover", ["SPY"], "1Day", "a", "b", cfg.params, {"sufficient_history": True}, h)
    row = reg.approve_strategy(cfg, "bt-ok")
    assert row["backtest_id"] == "bt-ok"
    assert reg.is_approved(cfg.source_id, h)[0]
    # changing params invalidates the approval
    ok, why = reg.is_approved(cfg.source_id, strategy_code_hash(cfg.name, {"fast": 11, "slow": 30}))
    assert not ok and "changed" in why
    reg.revoke(cfg.source_id)
    assert not reg.is_approved(cfg.source_id)[0]


def test_source_approval_requires_acknowledgement(db):
    reg = ApprovalRegistry(db)
    with pytest.raises(ApprovalError, match="strategies are approved"):
        reg.approve_source("strategy:sma_crossover", acknowledged=True)
    with pytest.raises(ApprovalError, match="i-reviewed"):
        reg.approve_source("discord:1")
    with pytest.raises(ApprovalError, match="unknown source"):
        reg.approve_source("discord:1", acknowledged=True)
    db.upsert_source("discord:1", "discord", "bob")
    reg.approve_source("discord:1", acknowledged=True)
    assert reg.is_approved("discord:1")[0]
    assert len(reg.list()) == 1


def test_kill_flatten_records_exit_pnl(settings, db):
    from tradesys.signals import SourceTracker
    rm = RiskManager(settings, db)
    broker = FakeBroker(cash=10_000, prices={"AAPL": 100.0})
    order = _buy(rm, broker, "AAPL", 10, 100.0, 95.0, 110.0)
    tracker = SourceTracker(db)
    tid = tracker.open_trade("strategy:x", "AAPL", "paper", 10, 100.0, 95.0, 110.0, entry_order_id=order.id)
    broker.set_price("AAPL", 103.0)
    KillSwitch(settings, db, broker, rm).trigger("t", flatten=True)
    t = db.get_trade(tid)
    assert t["status"] == "closed" and t["exit_reason"] == "kill" and t["pnl"] == 30.0

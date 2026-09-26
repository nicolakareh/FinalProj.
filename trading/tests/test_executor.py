from datetime import timedelta

import pytest

from tradesys.alerts import Notifier
from tradesys.common import utcnow
from tradesys.config import StrategyConfig
from tradesys.execution.approvals import ApprovalRegistry
from tradesys.execution.executor import Executor
from tradesys.execution.fake_broker import FakeBroker
from tradesys.risk.manager import RiskManager
from tradesys.signals import Direction, Signal, SourceTracker
from tradesys.strategies import strategy_code_hash
from tradesys.strategies.base import Intent
from tests.conftest import make_settings


CFG = StrategyConfig("sma_crossover", ("AAPL", "BTC/USD"), "1Day", {"fast": 5, "slow": 20})
HASH = strategy_code_hash(CFG.name, CFG.params)


def build(tmp_path, db, prices=None, live=False, **broker_kw):
    settings = make_settings(tmp_path, live_mode=live)
    notifier = Notifier(settings, db, sync=True)
    broker = FakeBroker(cash=10_000, prices=prices or {"AAPL": 100.0, "BTC/USD": 50_000.0}, mode=settings.mode, **broker_kw)
    rm = RiskManager(settings, db, notifier)
    approvals = ApprovalRegistry(db)
    tracker = SourceTracker(db, notifier)
    ex = Executor(settings, db, broker, rm, approvals, tracker, notifier, price_lookup=lambda s: broker.prices.get(s))
    return settings, notifier, broker, rm, approvals, tracker, ex


def approve(db, approvals):
    db.save_backtest("bt1", CFG.name, list(CFG.symbols), "1Day", "a", "b", CFG.params, {"sufficient_history": True}, HASH)
    approvals.approve_strategy(CFG, "bt1")


def drain(broker, ex):
    while broker.events:
        ev, order, extra = broker.events.pop(0)
        ex.on_trade_update(ev, order, extra)


def discord_signal(symbol="AAPL", direction=Direction.LONG, entry=100.0, stop=95.0, target=110.0, source="discord:1", **meta):
    return Signal(source, "discord", "bob", symbol, direction, utcnow(), entry, stop, target, "raw", meta=meta)


def test_unapproved_source_is_shadow_tracked(tmp_path, db):
    settings, notifier, broker, rm, approvals, tracker, ex = build(tmp_path, db)
    assert ex.handle_signal(discord_signal()) == "tracked"
    assert broker.orders == {}  # nothing reached the broker
    shadow = db.open_trades(mode="shadow")
    assert len(shadow) == 1 and shadow[0]["qty"] == 40 and shadow[0]["entry_price"] == 100.0
    # duplicate long for the same symbol does not open a second shadow trade
    assert ex.handle_signal(discord_signal()) == "tracked"
    assert len(db.open_trades(mode="shadow")) == 1
    # stop hit closes it with a loss and fees, and it counts toward the caller's record
    assert ex.update_shadow_trades({"AAPL": 94.0}) == 1
    st = tracker.stats("discord:1")
    assert st.trades == 1 and st.losses == 1 and st.net_pnl < -199
    # target and time exits
    ex.handle_signal(discord_signal(symbol="MSFT", entry=50, stop=48, target=55))
    assert ex.update_shadow_trades({"MSFT": 56.0}) == 1
    assert db.closed_trades_for_source("discord:1", limit=1)[0]["exit_reason"] == "target"
    ex.handle_signal(discord_signal(symbol="TSLA", entry=200, stop=190, target=None))
    assert ex.update_shadow_trades({"TSLA": 201.0}, now=utcnow() + timedelta(days=11)) == 1
    assert db.closed_trades_for_source("discord:1", limit=1)[0]["exit_reason"] == "time"
    # a CLOSE signal closes an open shadow trade at the current price
    ex.handle_signal(discord_signal(symbol="NVDA", entry=900, stop=880, target=None))
    assert ex.handle_signal(discord_signal(symbol="NVDA", direction=Direction.CLOSE, entry=None, stop=None, target=None),
                            price=910.0) == "tracked"
    assert db.closed_trades_for_source("discord:1", limit=1)[0]["pnl"] > 0


def test_rejections(tmp_path, db):
    settings, notifier, broker, rm, approvals, tracker, ex = build(tmp_path, db)
    assert ex.handle_signal(discord_signal(direction=Direction.SHORT)) == "rejected"
    assert ex.handle_signal(discord_signal(instrument="option", parse_ok=False, parse_reason="options")) == "rejected"
    assert ex.handle_signal(discord_signal(parse_ok=False, parse_reason="stop above entry")) == "rejected"
    tracker.register("discord:1", "discord", "bob")
    tracker.disable("discord:1", "test")
    assert ex.handle_signal(discord_signal()) == "rejected"
    statuses = [s["status"] for s in db.list_signals("discord:1")]
    assert statuses and all(s == "rejected" for s in statuses)


def test_approved_strategy_places_bracket_and_handles_stop(tmp_path, db):
    settings, notifier, broker, rm, approvals, tracker, ex = build(tmp_path, db)
    approve(db, approvals)
    out = ex.handle_strategy_intent(CFG, "AAPL", Intent("buy", 95.0, 110.0, "cross"), 100.0, HASH)
    assert out == "accepted"
    entry = [o for o in broker.orders.values() if o.side == "buy"][0]
    assert entry.status == "filled" and entry.order_class == "bracket" and len(entry.legs) == 2
    assert entry.qty == 40  # 2% of 10k / $5
    trade = db.open_trades(mode="paper")[0]
    assert trade["status"] == "pending" and trade["stop_order_id"] and trade["target_order_id"]
    drain(broker, ex)
    trade = db.get_trade(trade["id"])
    assert trade["status"] == "open" and trade["entry_price"] == 100.0
    assert notifier.sent[-1][0] == "FILL"
    # a second buy in the same symbol is refused (no pyramiding)
    assert ex.handle_strategy_intent(CFG, "AAPL", Intent("buy", 95.0, 110.0), 100.0, HASH) == "rejected"
    # price falls through the stop: the stop leg fills, the target leg is cancelled, trade closes at a loss
    broker.set_price("AAPL", 94.0)
    drain(broker, ex)
    trade = db.get_trade(trade["id"])
    assert trade["status"] == "closed" and trade["exit_reason"] == "stop" and trade["pnl"] < -239
    assert any(k == "STOP_HIT" for k, _ in notifier.sent)
    assert broker.get_open_orders() == [] and broker.positions == {}
    # -240 realised today > $200 daily limit -> daily halt fired from the fill handler
    assert rm.is_daily_halted() and any(k == "HALT_DAILY" for k, _ in notifier.sent)
    assert ex.handle_strategy_intent(CFG, "MSFT", Intent("buy", 45.0, 60.0), 50.0, HASH) == "rejected"


def test_target_hit_and_signal_exit(tmp_path, db):
    settings, notifier, broker, rm, approvals, tracker, ex = build(tmp_path, db)
    approve(db, approvals)
    ex.handle_strategy_intent(CFG, "AAPL", Intent("buy", 95.0, 110.0), 100.0, HASH)
    drain(broker, ex)
    broker.set_price("AAPL", 111.0)
    drain(broker, ex)
    t = db.list_trades(status="closed")[0]
    assert t["exit_reason"] == "target" and t["exit_price"] == 110.0 and t["pnl"] > 390
    assert tracker.stats(CFG.source_id).wins == 1
    # new trade, then the strategy says sell: legs cancelled, market exit, closed as 'signal'
    ex.handle_strategy_intent(CFG, "AAPL", Intent("buy", 105.0, 130.0), 111.0, HASH)
    drain(broker, ex)
    broker.set_price("AAPL", 115.0)
    assert ex.handle_strategy_intent(CFG, "AAPL", Intent("sell", reason="cross down"), 115.0, HASH) == "accepted"
    drain(broker, ex)
    t = db.list_trades(status="closed")[-1]
    assert t["exit_reason"] == "signal" and t["exit_price"] == 115.0 and t["pnl"] > 0
    assert broker.get_open_orders() == []
    # sell with nothing open is rejected
    assert ex.handle_strategy_intent(CFG, "AAPL", Intent("sell"), 115.0, HASH) == "rejected"


def test_crypto_gets_protective_stop_and_software_stop(tmp_path, db):
    settings, notifier, broker, rm, approvals, tracker, ex = build(tmp_path, db)
    approve(db, approvals)
    assert ex.handle_strategy_intent(CFG, "BTC/USD", Intent("buy", 48_000.0, 56_000.0), 50_000.0, HASH) == "accepted"
    entry = [o for o in broker.orders.values() if o.side == "buy"][0]
    assert entry.legs == [] and abs(entry.qty - 0.1) < 1e-6
    drain(broker, ex)
    trade = db.open_trades(mode="paper")[0]
    stop_orders = [o for o in broker.get_open_orders() if o.order_type == "stop_limit"]
    assert trade["status"] == "open" and len(stop_orders) == 1 and trade["stop_order_id"] == stop_orders[0].id
    # the resting stop-limit fills normally
    broker.set_price("BTC/USD", 47_900.0)
    drain(broker, ex)
    assert db.get_trade(trade["id"])["exit_reason"] == "stop"
    # second trade: the stop order disappears (e.g. rejected), software monitor takes over
    rm.clear_kill(); db.set_state("daily_halt_date", None)
    ex.handle_strategy_intent(CFG, "BTC/USD", Intent("buy", 46_000.0, 52_000.0), 47_900.0, HASH)
    drain(broker, ex)
    trade = db.open_trades(mode="paper")[0]
    broker.orders[trade["stop_order_id"]].status = "rejected"
    broker.set_price("BTC/USD", 45_900.0, _check=False)
    assert ex.check_software_stops({"BTC/USD": 45_900.0}) == [trade["id"]]
    drain(broker, ex)
    assert db.get_trade(trade["id"])["status"] == "closed"


def test_reconcile_picks_up_missed_fills(tmp_path, db):
    settings, notifier, broker, rm, approvals, tracker, ex = build(tmp_path, db)
    approve(db, approvals)
    ex.handle_strategy_intent(CFG, "AAPL", Intent("buy", 95.0, 110.0), 100.0, HASH)
    broker.events.clear()  # websocket "missed" the fill
    assert db.open_trades(mode="paper")[0]["status"] == "pending"
    ex.reconcile()
    assert db.open_trades(mode="paper")[0]["status"] == "open"
    broker.set_price("AAPL", 90.0)
    broker.events.clear()
    ex.reconcile()
    assert db.list_trades(status="closed")[0]["exit_reason"] == "stop"


def test_risk_rejection_and_live_gate(tmp_path, db):
    settings, notifier, broker, rm, approvals, tracker, ex = build(tmp_path, db, market_open=False)
    approve(db, approvals)
    assert ex.handle_strategy_intent(CFG, "AAPL", Intent("buy", 95.0, 110.0), 100.0, HASH) == "rejected"
    assert broker.orders == {}
    assert "market_open" in db.list_signals(CFG.source_id)[0]["status_reason"]
    # live mode without GO LIVE: nothing is sent
    settings2, notifier2, broker2, rm2, approvals2, tracker2, ex2 = build(tmp_path, db, live=True)
    assert ex2.handle_strategy_intent(CFG, "AAPL", Intent("buy", 95.0, 110.0), 100.0, HASH) == "rejected"
    assert broker2.orders == {}
    rm2.arm_live("GO LIVE")
    assert ex2.handle_strategy_intent(CFG, "AAPL", Intent("buy", 95.0, 110.0), 100.0, HASH) == "accepted"
    assert len(broker2.orders) == 3


def test_exit_all(tmp_path, db):
    settings, notifier, broker, rm, approvals, tracker, ex = build(tmp_path, db)
    approve(db, approvals)
    ex.handle_strategy_intent(CFG, "AAPL", Intent("buy", 95.0, 110.0), 100.0, HASH)
    drain(broker, ex)
    assert ex.exit_all("halt") == 1
    drain(broker, ex)
    assert db.list_trades(status="closed")[0]["exit_reason"] == "halt"

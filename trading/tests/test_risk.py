from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from tradesys.alerts import Notifier
from tradesys.common import utcnow
from tradesys.execution.models import AccountSnapshot, AssetInfo, ClockInfo, OrderIntent, OrderSnapshot, PositionSnapshot
from tradesys.risk.manager import RiskApproval, RiskManager, RiskViolation, verify_approval
from tests.conftest import make_settings


def intent(symbol="AAPL", side="buy", qty=10, ref=100.0, stop=95.0, target=110.0, **kw):
    return OrderIntent(symbol=symbol, side=side, qty=qty, order_type="market", reference_price=ref, source_id="strategy:x",
                       reason="t", client_order_id="c1", stop_price=stop, target_price=target, **kw)


def account(cash=10_000, equity=10_000, last_equity=10_000, **kw):
    return AccountSnapshot(cash=cash, equity=equity, last_equity=last_equity, buying_power=cash * 2,
                           non_marginable_buying_power=cash, **kw)


def position(symbol="AAPL", qty=10, entry=100.0, price=100.0, intraday=0.0):
    return PositionSnapshot(symbol, qty, entry, price, qty * price, qty * entry, (price - entry) * qty, intraday, qty)


STOCK = AssetInfo("AAPL", "us_equity", True, False)
OPEN = ClockInfo(True, None, None)


@pytest.fixture
def rm(settings, db):
    return RiskManager(settings, db, Notifier(settings, db, sync=True))


def test_allows_a_clean_buy_and_signs_it(rm):
    d = rm.evaluate(intent(), account(), [], [], STOCK, OPEN)
    assert d.allowed, d
    assert isinstance(d.approval, RiskApproval)
    verify_approval(d.approval)
    assert "risk_per_trade" in d.checks and "no_margin" in d.checks and "stop_required" in d.checks


def test_tampered_or_forged_approval_fails(rm):
    d = rm.evaluate(intent(), account(), [], [], STOCK, OPEN)
    forged = replace(d.approval, intent=intent(qty=1000))
    with pytest.raises(RiskViolation):
        verify_approval(forged)
    fake = RiskApproval(intent(), ("x",), "deadbeef", d.approval.created_at, "paper")
    with pytest.raises(RiskViolation):
        verify_approval(fake)
    with pytest.raises(RiskViolation):
        verify_approval(d.approval, now=utcnow() + timedelta(minutes=10))
    with pytest.raises(RiskViolation):
        verify_approval("not an approval")  # type: ignore[arg-type]


def test_stop_required_and_below_entry(rm):
    assert not rm.evaluate(intent(stop=None), account(), [], [], STOCK, OPEN).allowed
    d = rm.evaluate(intent(stop=101), account(), [], [], STOCK, OPEN)
    assert not d.allowed and any("stop_required" in r for r in d.reasons)


def test_two_percent_risk_cap(rm):
    # 10k cap -> $200 max risk. 41 shares * $5 = $205 -> rejected; 40 -> ok
    assert not rm.evaluate(intent(qty=41), account(), [], [], STOCK, OPEN).allowed
    assert rm.evaluate(intent(qty=40), account(), [], [], STOCK, OPEN).allowed


def test_capital_cap_counts_positions_and_open_buys(rm):
    held = [position("MSFT", qty=90, entry=100)]  # $9,000 deployed
    d = rm.evaluate(intent(qty=11), account(cash=50_000), held, [], STOCK, OPEN)  # +$1,100 -> $10,100 > cap
    assert not d.allowed and any("capital_cap" in r for r in d.reasons)
    assert rm.evaluate(intent(qty=10), account(cash=50_000), held, [], STOCK, OPEN).allowed
    pending = [OrderSnapshot("o1", "c", "TSLA", "buy", 5, 0, None, "limit", "new", limit_price=200)]  # $1,000 pending
    d = rm.evaluate(intent(qty=1), account(cash=50_000), held, pending, STOCK, OPEN)
    assert not d.allowed and any("capital_cap" in r for r in d.reasons)


def test_no_margin_uses_cash_not_buying_power(rm):
    d = rm.evaluate(intent(qty=10), account(cash=500), [], [], STOCK, OPEN)  # $1,000 order, $500 cash, $1,000 BP
    assert not d.allowed and any("no_margin" in r for r in d.reasons)


def test_no_shorting(rm):
    d = rm.evaluate(intent(side="sell", stop=None, target=None), account(), [], [], STOCK)
    assert not d.allowed and any("no_short" in r for r in d.reasons)
    d = rm.evaluate(intent(side="sell", qty=11, stop=None, target=None), account(), [position(qty=10)], [], STOCK)
    assert not d.allowed
    assert rm.evaluate(intent(side="sell", qty=10, stop=None, target=None), account(), [position(qty=10)], [], STOCK).allowed


def test_no_options_or_untradable_assets(rm):
    d = rm.evaluate(intent(symbol="AAPL260117C00150000"), account(), [], [], None, OPEN)
    assert not d.allowed and any("asset_class" in r for r in d.reasons)
    opt = AssetInfo("AAPL", "us_option", True, False)
    assert not rm.evaluate(intent(), account(), [], [], opt, OPEN).allowed
    assert not rm.evaluate(intent(), account(), [], [], AssetInfo("AAPL", "us_equity", False, False), OPEN).allowed
    # fractional qty on a non-fractionable asset
    assert not rm.evaluate(intent(qty=1.5), account(), [], [], STOCK, OPEN).allowed


def test_halts_block_buys_but_allow_exits(rm):
    rm.halt_daily("test")
    assert not rm.evaluate(intent(), account(), [], [], STOCK, OPEN).allowed
    assert rm.evaluate(intent(side="sell", stop=None, target=None), account(), [position()], [], STOCK).allowed
    assert rm.is_daily_halted()
    # lifts automatically the next trading day
    tomorrow = utcnow() + timedelta(days=1)
    assert not rm.is_daily_halted(tomorrow)
    rm.halt_weekly("test")
    assert not rm.evaluate(intent(), account(), [], [], STOCK, OPEN).allowed
    assert rm.is_weekly_halted() and rm.is_weekly_halted()  # does not expire on its own
    rm.resume_weekly()
    assert rm.evaluate(intent(), account(), [], [], STOCK, OPEN).allowed
    rm.kill("test")
    assert not rm.evaluate(intent(), account(), [], [], STOCK, OPEN).allowed
    rm.clear_kill()
    assert rm.evaluate(intent(), account(), [], [], STOCK, OPEN).allowed


def test_live_gate_requires_go_live(tmp_path, db):
    s = make_settings(tmp_path, live_mode=True)
    rm = RiskManager(s, db)
    d = rm.evaluate(intent(), account(), [], [], STOCK, OPEN)
    assert not d.allowed and any("live_gate" in r for r in d.reasons)
    with pytest.raises(RiskViolation):
        rm.arm_live("go live")
    with pytest.raises(RiskViolation):
        rm.arm_live("yes")
    rm.arm_live("GO LIVE")
    assert rm.is_armed()
    d = rm.evaluate(intent(), account(), [], [], STOCK, OPEN)
    assert d.allowed and d.approval.mode == "live"
    rm.disarm()
    assert not rm.evaluate(intent(), account(), [], [], STOCK, OPEN).allowed
    # arming is meaningless (and refused) in paper mode
    with pytest.raises(RiskViolation):
        RiskManager(make_settings(tmp_path), db).arm_live("GO LIVE")


def test_runaway_guards_pdt_and_market_hours(rm, db):
    closed = ClockInfo(False, None, None)
    d = rm.evaluate(intent(), account(), [], [], STOCK, closed)
    assert not d.allowed and any("market_open" in r for r in d.reasons)
    # crypto trades round the clock
    crypto = AssetInfo("BTC/USD", "crypto", True, True)
    assert rm.evaluate(intent(symbol="BTC/USD", qty=0.01, ref=50_000, stop=48_000, target=55_000), account(), [], [],
                       crypto, closed).allowed
    d = rm.evaluate(intent(), account(equity=9_000, daytrade_count=3), [], [], STOCK, OPEN)
    assert not d.allowed and any("pdt_guard" in r for r in d.reasons)
    held = [position(f"S{i}", qty=1, entry=1.0) for i in range(10)]
    d = rm.evaluate(intent(), account(), held, [], STOCK, OPEN)
    assert not d.allowed and any("max_positions" in r for r in d.reasons)
    for i in range(40):
        db.log_order(None, f"o{i}", f"c{i}", "AAPL", "buy", 1, "market", "filled")
    d = rm.evaluate(intent(), account(), [], [], STOCK, OPEN)
    assert not d.allowed and any("max_orders_per_day" in r for r in d.reasons)
    assert not rm.evaluate(intent(), account(trading_blocked=True), [], [], STOCK, OPEN).allowed


def test_loss_limits_trigger_halts(settings, db):
    notifier = Notifier(settings, db, sync=True)
    rm = RiskManager(settings, db, notifier)
    now = utcnow()
    # realised -150 today plus -60 unrealised intraday -> -210 <= -200 daily limit
    db.insert_trade(source_id="s", symbol="AAPL", mode="paper", qty=1, entry_price=100, status="closed",
                    entry_time=now, exit_time=now, exit_price=0, pnl=-150.0)
    fired = rm.check_loss_limits(account(), [position(price=94, intraday=-60)], now)
    assert fired == ["daily"] and rm.is_daily_halted()
    assert notifier.sent[-1][0] == "HALT_DAILY"
    # weekly: another -300 realised earlier this week -> total -510 <= -500
    monday = now - timedelta(days=now.astimezone(timezone(timedelta(hours=-4))).weekday())
    if monday.date() == now.date():
        monday = now  # Monday: same day counts
    db.insert_trade(source_id="s", symbol="AAPL", mode="paper", qty=1, entry_price=100, status="closed",
                    entry_time=monday, exit_time=monday, exit_price=0, pnl=-300.0)
    fired = rm.check_loss_limits(account(), [position(price=94, intraday=-60)], now)
    assert "weekly" in fired and rm.is_weekly_halted()
    assert notifier.sent[-1][0] == "HALT_WEEKLY"
    # live-mode trades are not mixed into paper-mode P&L
    snap = rm.pnl_snapshot(account(), [], now)
    db.insert_trade(source_id="s", symbol="AAPL", mode="live", qty=1, entry_price=100, status="closed",
                    entry_time=now, exit_time=now, exit_price=0, pnl=-5000.0)
    assert rm.pnl_snapshot(account(), [], now).realized_today == snap.realized_today
    st = rm.status()
    assert st["daily_halted"] and st["weekly_halted"] and st["mode"] == "paper"

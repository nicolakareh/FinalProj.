from datetime import timedelta

from tradesys.alerts import Notifier
from tradesys.common import utcnow
from tradesys.signals import Direction, Signal, SourceTracker


def test_auto_disable_after_negative_window(settings, db):
    notifier = Notifier(settings, db, sync=True)
    tr = SourceTracker(db, notifier)
    tr.register("discord:1", "discord", "caller")
    now = utcnow()
    # 19 losing trades: not enough history to judge
    for i in range(19):
        tid = tr.open_trade("discord:1", "AAPL", "shadow", 1, 100, 95, 110, now - timedelta(hours=40 - i))
        tr.close_trade(tid, 99, now - timedelta(hours=39 - i), "stop")
    assert tr.is_active("discord:1")
    # 20th trade tips the 20-trade window negative -> disabled
    tid = tr.open_trade("discord:1", "AAPL", "shadow", 1, 100, 95, 110, now)
    tr.close_trade(tid, 99.5, now, "stop")
    assert not tr.is_active("discord:1")
    assert notifier.sent[-1][0] == "SOURCE_DISABLED"
    st = tr.stats("discord:1")
    assert st.trades == 20 and st.wins == 0 and st.last_window_pnl < 0 and st.status == "disabled"
    # manual re-enable works
    tr.enable("discord:1")
    assert tr.is_active("discord:1")


def test_window_uses_only_last_20(settings, db):
    tr = SourceTracker(db)
    tr.register("strategy:s", "strategy", "s")
    now = utcnow()
    # 10 big early losses, then 10 small wins: the 20-trade window is net negative -> disabled at trade 20
    for i in range(10):
        tid = tr.open_trade("strategy:s", "SPY", "paper", 1, 100, 90, 120, now - timedelta(days=60 - i))
        tr.close_trade(tid, 80, now - timedelta(days=59 - i), "stop")
    for i in range(10):
        tid = tr.open_trade("strategy:s", "SPY", "paper", 1, 100, 90, 120, now - timedelta(days=40 - i))
        tr.close_trade(tid, 101, now - timedelta(days=39 - i), "target")
    assert not tr.is_active("strategy:s")
    assert tr.stats("strategy:s").last_window_pnl == -190.0
    # 10 more wins (still disabled, so these would be shadow-tracked in practice)
    for i in range(10):
        tid = tr.open_trade("strategy:s", "SPY", "paper", 1, 100, 90, 120, now - timedelta(days=20 - i))
        tr.close_trade(tid, 101, now - timedelta(days=19 - i), "target")
    # the old losses have now rolled out of the 20-trade window, so re-enabling sticks
    assert tr.stats("strategy:s").last_window_pnl == 20.0
    tr.enable("strategy:s")
    assert tr.evaluate("strategy:s") is False
    assert tr.is_active("strategy:s")
    st = tr.stats("strategy:s")
    assert st.trades == 30 and st.net_pnl == -180.0 and st.last_window_pnl == 20.0
    assert st.max_drawdown == 200.0
    assert st.win_rate == 20 / 30


def test_pnl_includes_fees_and_signal_logging(settings, db):
    tr = SourceTracker(db)
    sig = Signal("discord:9", "discord", "bob", "BTC/USD", Direction.LONG, utcnow(), entry=50000, stop=48000,
                 target=54000, raw_text="long btc")
    sid = tr.record_signal(sig)
    tid = tr.open_trade("discord:9", "BTC/USD", "shadow", 0.01, 50000, 48000, 54000, signal_id=sid)
    trade = tr.close_trade(tid, 54000, exit_reason="target", fees=2.5)
    assert abs(trade["pnl"] - (4000 * 0.01 - 2.5)) < 1e-9
    assert trade["exit_reason"] == "target"
    assert db.list_signals("discord:9")[0]["symbol"] == "BTC/USD"

import asyncio
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tradesys.alerts import Notifier
from tradesys.common import utcnow
from tradesys.config import StrategyConfig
from tradesys.engine import TradingEngine
from tradesys.execution.fake_broker import FakeBroker
from tradesys.news.feed import NewsItem
from tradesys.reporting.daily_report import build_report, save_report
from tradesys.risk.manager import RiskManager
from tradesys.signals import SourceTracker
from tradesys.storage import Database
from tradesys.strategies import strategy_code_hash
from tradesys.strategies.base import Intent, Strategy
from tests.conftest import make_settings


class StubMarketData:
    """Deterministic bars/prices; the last bar is complete (timestamp two days back)."""

    def __init__(self, prices):
        self.prices = dict(prices)

    def get_recent_bars(self, symbol, timeframe, bars):
        n = max(bars, 30)
        end = pd.Timestamp(utcnow()).floor("D") - pd.Timedelta(days=2)
        idx = pd.date_range(end=end, periods=n, freq="D", tz="UTC")
        p = self.prices[symbol]
        close = np.linspace(p * 0.9, p, n)
        return pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
                             "volume": 1e6, "trade_count": 1.0, "vwap": close}, index=idx)

    def get_bars(self, symbol, timeframe="1Day", start=None, end=None, limit=None):
        return self.get_recent_bars(symbol, timeframe, 30)

    def get_latest_price(self, symbol):
        return self.prices[symbol]

    def get_latest_prices(self, symbols):
        return {s: self.prices[s] for s in symbols if s in self.prices}


class AlwaysBuy(Strategy):
    name = "sma_crossover"  # borrow the registered name so approval hashing works
    default_params = {"fast": 5, "slow": 20}

    @property
    def warmup(self):
        return 2

    def prepare(self, df):
        return df

    def on_bar(self, df, i, position):
        if position is None:
            close = float(df["close"].iloc[i])
            return Intent("buy", close * 0.95, close * 1.10, "always")
        return None


def make_engine(tmp_path, **settings_kw):
    cfg = StrategyConfig("sma_crossover", ("AAPL",), "1Day", {"fast": 5, "slow": 20})
    settings = make_settings(tmp_path, strategies=(cfg,), **settings_kw)
    db = Database(tmp_path / "e.db")
    broker = FakeBroker(cash=10_000, prices={"AAPL": 100.0, "BTC/USD": 50_000.0, "SPY": 500.0})
    md = StubMarketData({"AAPL": 100.0, "BTC/USD": 50_000.0, "SPY": 500.0})
    engine = TradingEngine(settings, db=db, broker=broker, market_data=md, notifier=Notifier(settings, db, sync=True))
    code_hash = strategy_code_hash(cfg.name, cfg.params)
    engine.strategies = [(cfg, AlwaysBuy(**cfg.params), code_hash)]
    return engine, cfg, code_hash


def test_engine_strategy_pass_places_order_once(tmp_path):
    engine, cfg, code_hash = make_engine(tmp_path)
    engine.startup_checks()
    # not approved yet: shadow only
    assert engine.evaluate_strategies() == 1
    assert engine.broker.orders == {} and len(engine.db.open_trades(mode="shadow")) == 1
    # approve and evaluate again: the same bar is not re-evaluated until a new bar arrives
    engine.db.save_backtest("bt", cfg.name, ["AAPL"], "1Day", "a", "b", cfg.params, {"sufficient_history": True}, code_hash)
    engine.approvals.approve_strategy(cfg, "bt")
    assert engine.evaluate_strategies() == 0
    engine._last_bar.clear()
    assert engine.evaluate_strategies() == 1
    orders = list(engine.broker.orders.values())
    assert any(o.side == "buy" and o.status == "filled" for o in orders)
    while engine.broker.events:
        ev, order, extra = engine.broker.events.pop(0)
        engine.executor.on_trade_update(ev, order, extra)
    assert engine.db.open_trades(mode="paper")[0]["status"] == "open"
    assert "open AAPL" in engine.status_text()
    assert "strategy:sma_crossover" in engine.sources_text()


def test_engine_risk_tick_kill_file_and_halt(tmp_path):
    engine, cfg, code_hash = make_engine(tmp_path)
    engine.risk_tick()
    assert not engine._stop.is_set()
    Path(engine.settings.kill_file).write_text("x")
    engine.risk_tick()
    assert engine.risk.is_killed() and engine._stop.is_set()
    assert engine.notifier.sent[-1][0] == "KILL"


def test_engine_maintenance_news_and_report(tmp_path):
    engine, cfg, code_hash = make_engine(tmp_path)
    engine.maintenance_tick()  # nothing open: no-op
    now = utcnow()
    items = [NewsItem(f"n{i}", "Apple beats estimates, shares surge to record", "", "t", f"u{i}",
                      now - timedelta(minutes=i), ("AAPL",)) for i in range(6)]
    engine.news.fetcher = type("F", (), {"fetch": lambda self, since=None: items})()
    assert engine.poll_news() == 1
    assert any(k == "NEWS_ALERT" for k, _ in engine.notifier.sent)
    # the news signal was shadow-tracked (news:momentum is not approved)
    assert any(t["source_id"] == "news:momentum" for t in engine.db.open_trades(mode="shadow"))
    engine.maintenance_tick()
    report, path = engine.write_daily_report(email=False)
    assert path.exists() and "Signal sources vs buy-and-hold" in path.read_text()
    assert asyncio.run(engine.discord_command("status", [])).startswith("mode=paper")
    assert "day" in asyncio.run(engine.discord_command("pnl", []))
    assert "commands" in asyncio.run(engine.discord_command("help", []))


def test_daily_report_content(tmp_path, db):
    settings = make_settings(tmp_path)
    tracker = SourceTracker(db)
    rm = RiskManager(settings, db)
    now = utcnow()
    tracker.register("strategy:s", "strategy", "s")
    t1 = tracker.open_trade("strategy:s", "AAPL", "paper", 10, 100, 95, 110, now - timedelta(hours=3))
    tracker.close_trade(t1, 108, now - timedelta(hours=1), "target", fees=0.1)
    t2 = tracker.open_trade("strategy:s", "MSFT", "paper", 5, 50, 48, 60, now - timedelta(hours=2))
    tracker.close_trade(t2, 48, now - timedelta(minutes=30), "stop", fees=0.05)
    tracker.open_trade("strategy:s", "SPY", "paper", 1, 500, 490, 520, now)
    pnl = vars(rm.pnl_snapshot(type("A", (), {"equity": 10_000, "last_equity": 10_000})(), []))
    report = build_report(settings, db, tracker, rm.status(), pnl, account={"equity": 10_079.85, "cash": 9_500},
                          benchmark_fn=lambda sym, a, b: 0.01 if sym == "SPY" else -0.02)
    md = report.to_markdown()
    assert "| AAPL | strategy:s | 10 |" in md and "| MSFT |" in md
    assert "Today: 2 trades, win rate 50%" in md
    assert "+100.00" in md and "-200.00" in md  # B&H SPY / BTC on the source's window with a 10k cap
    assert "| SPY | strategy:s | 1 |" in md  # open trade
    assert report.stats["max_drawdown_usd"] == pytest.approx(10.05)
    path = save_report(settings, report)
    assert path.exists() and path.suffix == ".md"


def test_engine_writes_one_report_per_day_after_close(tmp_path):
    from datetime import datetime
    from tradesys.common import NY
    engine, cfg, code_hash = make_engine(tmp_path)
    morning = datetime(2026, 3, 3, 10, 0, tzinfo=NY)
    engine.risk_tick(morning)
    assert engine._last_report_date is None
    engine.risk_tick(datetime(2026, 3, 3, 16, 6, tzinfo=NY))
    assert engine._last_report_date == morning.date()
    reports = list((tmp_path / "reports").glob("*.md"))
    assert len(reports) == 1
    engine.risk_tick(datetime(2026, 3, 3, 17, 2, tzinfo=NY))
    assert len(list((tmp_path / "reports").glob("*.md"))) == 1
    engine.risk_tick(datetime(2026, 3, 4, 16, 30, tzinfo=NY))
    assert len(list((tmp_path / "reports").glob("*.md"))) == 2

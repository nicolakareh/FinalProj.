import numpy as np
import pandas as pd
import pytest

from tradesys.backtest.engine import BacktestConfig, Backtester, FeeModel
from tradesys.backtest.metrics import buy_and_hold, compute_metrics, max_drawdown
from tradesys.backtest.runner import format_result, run_backtest, save_backtest
from tradesys.config import StrategyConfig
from tradesys.risk.sizing import position_size
from tradesys.strategies import create_strategy, list_strategies, strategy_code_hash
from tradesys.strategies.base import Intent, PositionState, Strategy
from tradesys.storage import Database
from tests.conftest import make_settings


def bars(n=800, seed=1, start="2022-01-03", freq="B", drift=0.0004, vol=0.01, base=100.0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    rets = rng.normal(drift, vol, n)
    close = base * np.cumprod(1 + rets)
    open_ = np.concatenate([[base], close[:-1]]) * (1 + rng.normal(0, 0.001, n))
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.005, n))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.005, n))
    vol_ = rng.uniform(1e6, 2e6, n)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": vol_,
                         "trade_count": 1.0, "vwap": close}, index=idx)


class OneShot(Strategy):
    """Buys at bar `at` with a fixed stop/target; used to pin down fill mechanics."""
    name = "oneshot"
    default_params = {"at": 5, "stop": 90.0, "target": 120.0}

    @property
    def warmup(self):
        return 1

    def prepare(self, df):
        return df

    def on_bar(self, df, i, position):
        if i == self.p("at") and position is None:
            return Intent("buy", self.p("stop"), self.p("target"), "test")
        return None


def flat_bars(prices, start="2023-01-02"):
    idx = pd.date_range(start, periods=len(prices), freq="B", tz="UTC")
    p = np.array(prices, dtype=float)
    return pd.DataFrame({"open": p, "high": p, "low": p, "close": p, "volume": 1e6, "trade_count": 1.0, "vwap": p},
                        index=idx)


def test_position_size_respects_risk_cap_and_cash():
    # 2% of 10k = $200 risk; $5 per share risk -> 40 shares
    assert position_size(10_000, 2.0, 100, 95, cash_available=10_000, deployed_notional=0, fractional=False) == 40
    # cash limits notional: only $1,000 available -> 10 shares
    assert position_size(10_000, 2.0, 100, 95, cash_available=1_000, deployed_notional=0, fractional=False) == 10
    # capital cap limits notional even if the account has more cash
    assert position_size(10_000, 2.0, 100, 95, cash_available=50_000, deployed_notional=9_500, fractional=False) == 5
    # no stop / stop above entry -> zero
    assert position_size(10_000, 2.0, 100, 100, 10_000, 0, False) == 0
    assert position_size(10_000, 2.0, 100, 105, 10_000, 0, False) == 0
    # fractional crypto
    q = position_size(10_000, 2.0, 50_000, 48_000, 10_000, 0, fractional=True)
    assert abs(q - 0.1) < 1e-6


def test_fill_next_open_with_slippage_then_stop():
    # signal at bar 5 (close 100); bar 6 opens 100 -> fill 100.05 with 5bps; bar 8 gaps to 85 below the 90 stop
    prices = [100] * 6 + [100, 95, 85, 85, 85]
    df = flat_bars(prices)
    df.loc[df.index[8], ["open", "high", "low", "close"]] = [85, 86, 84, 85]
    cfg = BacktestConfig(initial_capital=10_000, risk_pct=2.0, slippage_bps_stock=5, fees=FeeModel())
    res = Backtester(cfg).run(OneShot(at=5, stop=90.0, target=120.0), {"XYZ": df}, "1Day")
    assert len(res.trades) == 1
    t = res.trades[0]
    assert abs(t.entry_price - 100.05) < 1e-9
    assert t.exit_reason == "stop"
    # gap below the stop fills at the open (85) minus slippage, not at the stop price
    assert abs(t.exit_price - 85 * (1 - 0.0005)) < 1e-9
    assert t.qty == 19  # floor($200 risk / ($100.05 - 90) = 19.9)
    assert t.pnl < 0 and t.fees > 0
    assert res.metrics["n_trades"] == 1 and res.metrics["fees_paid"] > 0
    assert res.equity.iloc[-1] == pytest.approx(10_000 + t.pnl, abs=1e-6)


def test_target_and_signal_exits_and_end_liquidation():
    prices = [100] * 6 + [100, 110, 125, 125]
    df = flat_bars(prices)
    df.loc[df.index[8], ["open", "high", "low", "close"]] = [118, 126, 117, 125]
    res = Backtester(BacktestConfig(initial_capital=10_000, slippage_bps_stock=0)).run(
        OneShot(at=5, stop=90.0, target=120.0), {"XYZ": df}, "1Day")
    t = res.trades[0]
    assert t.exit_reason == "target" and t.exit_price == 120.0 and t.pnl > 0
    # still-open positions are liquidated at the last close
    res2 = Backtester(BacktestConfig(initial_capital=10_000, slippage_bps_stock=0)).run(
        OneShot(at=5, stop=50.0, target=500.0), {"XYZ": df}, "1Day")
    assert res2.trades[0].exit_reason == "end_of_test"


def test_fee_model():
    f = FeeModel()
    assert f.fee("AAPL", 100, 100, "buy") == 0.0
    sell = f.fee("AAPL", 100, 100, "sell")
    assert 0 < sell < 1.0
    assert f.fee("BTC/USD", 0.1, 50_000, "buy") == pytest.approx(12.5)


def test_metrics_and_drawdown():
    eq = pd.Series([100, 110, 99, 120, 90, 130], index=pd.date_range("2024-01-01", periods=6, freq="D", tz="UTC"))
    dd_pct, dd_abs = max_drawdown(eq)
    assert dd_abs == 30 and abs(dd_pct - 0.25) < 1e-9
    m = compute_metrics(eq.astype(float), [], 252, 100.0)
    assert m["total_return_pct"] == 30.0 and m["max_drawdown_pct"] == 25.0 and m["n_trades"] == 0


def test_buy_and_hold_benchmark():
    df = flat_bars([100, 105, 110, 120])
    eq, m = buy_and_hold(df, 10_000, FeeModel().fee, 0, "SPY", 252, fractional=False)
    assert m["total_return_pct"] == pytest.approx(20.0, abs=0.1)
    assert m["n_trades"] == 1


def test_real_strategies_run_and_registry():
    names = [n for n, _, _ in list_strategies()]
    assert {"sma_crossover", "rsi_reversion", "breakout_volume"} <= set(names)
    data = {"AAA": bars(800, seed=3), "BBB": bars(800, seed=4)}
    for name in names:
        strat = create_strategy(name)
        res = Backtester(BacktestConfig(initial_capital=10_000)).run(strat, data, "1Day")
        assert len(res.equity) == 800
        assert res.metrics["max_drawdown_pct"] >= 0
        for t in res.trades:
            assert t.stop_price < t.entry_price          # every entry had a stop below it
            assert t.qty * (t.entry_price - t.stop_price) <= 200.0 + 1e-6   # 2% of 10k
    with pytest.raises(ValueError):
        create_strategy("sma_crossover", {"bogus": 1})
    h1 = strategy_code_hash("sma_crossover", {"fast": 10})
    assert h1 != strategy_code_hash("sma_crossover", {"fast": 11})
    assert h1 == strategy_code_hash("sma_crossover", {"fast": 10})


def test_intent_requires_stop():
    with pytest.raises(ValueError):
        Intent("buy")
    with pytest.raises(ValueError):
        Intent("short", 1.0)
    assert PositionState(1, 100, 95, 110).qty == 1


def test_run_backtest_with_benchmarks_and_save(tmp_path):
    settings = make_settings(tmp_path)
    db = Database(tmp_path / "t.db")
    cfg = StrategyConfig("sma_crossover", ("AAA",), "1Day", {"fast": 10, "slow": 30})
    data = {"AAA": bars(800, seed=5)}
    bench = {"SPY": bars(800, seed=6), "BTC/USD": bars(800, seed=7)}
    res = run_backtest(settings, md=None, cfg=cfg, data=data, benchmark_data=bench)
    assert res.sufficient_history and res.history_days >= 730
    assert set(res.benchmarks) == {"B&H SPY", "B&H BTC/USD", "B&H AAA"}
    text = format_result(res, "x")
    assert "Total return" in text and "B&H SPY" in text
    bt_id = save_backtest(settings, db, res, cfg)
    row = db.get_backtest(bt_id)
    assert row["strategy"] == "sma_crossover" and row["results"]["sufficient_history"] is True
    assert (tmp_path / "backtests" / f"{bt_id}.json").exists()
    # short history is flagged
    short = run_backtest(settings, md=None, cfg=cfg, data={"AAA": bars(300, seed=5)}, benchmark_data=bench)
    assert not short.sufficient_history and any("INSUFFICIENT" in w or "required" in w for w in short.warnings)

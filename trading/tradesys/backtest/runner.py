"""Fetch 2+ years of history, run a strategy through the backtester, compare it with
buying and holding SPY and BTC/USD (and the traded symbols), then persist the result
so it can be cited when approving the strategy for live trading.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from ..common import ensure_dir, is_crypto, to_iso, utcnow
from ..config import Settings, StrategyConfig
from ..data.market_data import MarketData, periods_per_year
from ..storage import Database
from ..strategies import create_strategy, strategy_code_hash
from .engine import BacktestConfig, Backtester, BacktestResult, FeeModel
from .metrics import buy_and_hold

log = logging.getLogger(__name__)

MIN_HISTORY_DAYS = 730          # "2+ years"
BENCHMARKS = ("SPY", "BTC/USD")


def make_backtest_id(strategy: str, when: datetime | None = None) -> str:
    when = when or utcnow()
    return f"{strategy}-{when.strftime('%Y%m%d-%H%M%S')}"


def run_backtest(settings: Settings, md: MarketData, cfg: StrategyConfig, years: float = 2.0,
                 end: datetime | None = None, bt_config: BacktestConfig | None = None,
                 data: dict[str, pd.DataFrame] | None = None,
                 benchmark_data: dict[str, pd.DataFrame] | None = None) -> BacktestResult:
    """`data`/`benchmark_data` let tests inject frames instead of hitting Alpaca."""
    end = end or utcnow()
    bt_config = bt_config or BacktestConfig(initial_capital=settings.total_capital_cap,
                                            risk_pct=settings.max_risk_per_trade_pct,
                                            max_open_positions=settings.max_open_positions, fees=FeeModel())
    strategy = create_strategy(cfg.name, cfg.params)
    if data is None:
        data = {sym: md.get_history(sym, cfg.timeframe, years=max(years, 2.0), end=end) for sym in cfg.symbols}
    warnings: list[str] = []
    for sym, df in data.items():
        if df.empty:
            warnings.append(f"{sym}: no data returned")
    data = {s: d for s, d in data.items() if not d.empty}
    if not data:
        raise ValueError("no historical data for any symbol; check ALPACA keys / symbols")
    ppy = periods_per_year(cfg.timeframe, cfg.symbols[0])
    result = Backtester(bt_config).run(strategy, data, cfg.timeframe, periods_per_year=ppy)
    result.warnings.extend(warnings)
    result.sufficient_history = result.history_days >= MIN_HISTORY_DAYS
    if not result.sufficient_history:
        result.warnings.append(f"only {result.history_days} days of history; {MIN_HISTORY_DAYS}+ required for approval")

    # benchmarks over the same window
    start = result.start
    bench_syms = list(BENCHMARKS) + [s for s in data if s not in BENCHMARKS]
    for sym in bench_syms:
        try:
            if benchmark_data is not None and sym in benchmark_data:
                bdf = benchmark_data[sym]
            elif sym in data:
                bdf = data[sym]
            else:
                bdf = md.get_history(sym, "1Day", years=max(years, 2.0), end=end)
            bdf = bdf[(bdf.index >= start) & (bdf.index <= result.end)]
            if bdf.empty:
                continue
            tf = cfg.timeframe if sym in data else "1Day"
            _, m = buy_and_hold(bdf, bt_config.initial_capital, bt_config.fees.fee, bt_config.slippage(sym) * 10_000,
                                sym, periods_per_year(tf, sym), fractional=is_crypto(sym))
            result.benchmarks[f"B&H {sym}"] = m
        except Exception as e:  # a missing benchmark must not sink the backtest
            log.warning("benchmark %s failed: %s", sym, e)
            result.warnings.append(f"benchmark {sym} unavailable: {e}")
    return result


def save_backtest(settings: Settings, db: Database, result: BacktestResult, cfg: StrategyConfig) -> str:
    bt_id = make_backtest_id(cfg.name)
    payload = result.to_dict()
    payload["id"] = bt_id
    payload["code_hash"] = strategy_code_hash(cfg.name, cfg.params)
    out_dir = ensure_dir(settings.backtests_dir)
    (out_dir / f"{bt_id}.json").write_text(json.dumps(payload, indent=2, default=str))
    (out_dir / f"{bt_id}.txt").write_text(format_result(result, bt_id))
    db.save_backtest(bt_id, cfg.name, list(cfg.symbols), cfg.timeframe, to_iso(result.start) or "",
                     to_iso(result.end) or "", cfg.params, {k: v for k, v in payload.items() if k not in ("trades", "equity")},
                     payload["code_hash"])
    return bt_id


ROWS = [
    ("Total return", "total_return_pct", "%"), ("CAGR", "cagr_pct", "%"), ("Max drawdown", "max_drawdown_pct", "%"),
    ("Max drawdown $", "max_drawdown_usd", "$"), ("Sharpe", "sharpe", ""), ("Sortino", "sortino", ""),
    ("Volatility (ann.)", "annual_volatility_pct", "%"), ("Net profit", "net_profit", "$"),
    ("Final equity", "final_equity", "$"), ("Trades", "n_trades", ""), ("Win rate", "win_rate_pct", "%"),
    ("Profit factor", "profit_factor", ""), ("Avg trade", "avg_trade", "$"), ("Best trade", "best_trade", "$"),
    ("Worst trade", "worst_trade", "$"), ("Fees paid", "fees_paid", "$"), ("Exposure", "exposure_pct", "%"),
]


def _fmt(v: Any, unit: str) -> str:
    if v is None:
        return "-"
    if isinstance(v, float) and v == float("inf"):
        return "inf"
    if unit == "$":
        return f"${v:,.2f}"
    if unit == "%":
        return f"{v:.2f}%"
    return f"{v}"


def format_result(result: BacktestResult, bt_id: str | None = None) -> str:
    cols = {"Strategy": result.metrics, **result.benchmarks}
    names = list(cols)
    width = max(18, *(len(n) + 2 for n in names))
    lines = []
    title = f"Backtest {bt_id or ''} - {result.strategy} {result.params} on {', '.join(result.symbols)} [{result.timeframe}]"
    lines.append(title)
    lines.append(f"Window: {result.start:%Y-%m-%d} to {result.end:%Y-%m-%d} ({result.history_days} days)"
                 f"{'' if result.sufficient_history else '  ** INSUFFICIENT HISTORY (<2y) **'}")
    cfg = result.config
    lines.append(f"Capital ${cfg.initial_capital:,.0f}, risk/trade {cfg.risk_pct}%, slippage {cfg.slippage_bps_stock}/"
                 f"{cfg.slippage_bps_crypto} bps (stock/crypto), crypto fee {cfg.fees.crypto_fee_pct}%")
    lines.append("")
    lines.append(f"{'Metric':<20}" + "".join(f"{n:>{width}}" for n in names))
    lines.append("-" * (20 + width * len(names)))
    for label, key, unit in ROWS:
        lines.append(f"{label:<20}" + "".join(f"{_fmt(cols[n].get(key), unit):>{width}}" for n in names))
    if result.per_symbol:
        lines.append("")
        lines.append("Per symbol: " + "; ".join(f"{s}: {m['n_trades']} trades, ${m['net_pnl']:,.2f}, win {m['win_rate_pct']}%"
                                                for s, m in result.per_symbol.items()))
    if result.warnings:
        lines.append("")
        lines.extend(f"WARNING: {w}" for w in result.warnings)
    return "\n".join(lines)

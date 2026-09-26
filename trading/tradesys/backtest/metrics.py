"""Performance metrics for equity curves and trade lists, plus buy-and-hold benchmarks."""
from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np
import pandas as pd


def max_drawdown(equity: pd.Series) -> tuple[float, float]:
    """(drawdown as a fraction of the running peak, drawdown in dollars); both positive numbers."""
    if equity.empty:
        return 0.0, 0.0
    peak = equity.cummax()
    dd = (equity - peak)
    dd_pct = dd / peak.replace(0, np.nan)
    return float(-dd_pct.min(skipna=True) or 0.0), float(-dd.min() or 0.0)


def compute_metrics(equity: pd.Series, trades: Iterable[Any], periods_per_year: float,
                    initial_capital: float) -> dict[str, Any]:
    trades = list(trades)
    equity = equity.dropna()
    if equity.empty:
        return {"total_return_pct": 0.0, "n_trades": 0}
    final = float(equity.iloc[-1])
    total_return = final / initial_capital - 1.0
    start, end = equity.index[0], equity.index[-1]
    years = max((end - start).total_seconds() / (365.25 * 86400), 1e-9)
    cagr = (final / initial_capital) ** (1 / years) - 1.0 if final > 0 and years > 1 / 365 else total_return
    rets = equity.pct_change().dropna()
    vol = float(rets.std(ddof=0) * math.sqrt(periods_per_year)) if len(rets) > 1 else 0.0
    sharpe = float(rets.mean() / rets.std(ddof=0) * math.sqrt(periods_per_year)) if len(rets) > 1 and rets.std(ddof=0) > 0 else 0.0
    downside = rets[rets < 0]
    sortino = float(rets.mean() / downside.std(ddof=0) * math.sqrt(periods_per_year)) if len(downside) > 1 and downside.std(ddof=0) > 0 else 0.0
    dd_pct, dd_abs = max_drawdown(equity)
    pnls = [float(t.pnl) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_profit, gross_loss = sum(wins), -sum(losses)
    fees = sum(float(getattr(t, "fees", 0.0)) for t in trades)
    bars_held = [int(getattr(t, "bars_held", 0)) for t in trades]
    return {
        "start": str(start), "end": str(end), "years": round(years, 3),
        "initial_capital": initial_capital, "final_equity": round(final, 2),
        "net_profit": round(final - initial_capital, 2),
        "total_return_pct": round(total_return * 100, 2), "cagr_pct": round(cagr * 100, 2),
        "annual_volatility_pct": round(vol * 100, 2), "sharpe": round(sharpe, 2), "sortino": round(sortino, 2),
        "max_drawdown_pct": round(dd_pct * 100, 2), "max_drawdown_usd": round(dd_abs, 2),
        "calmar": round(cagr / dd_pct, 2) if dd_pct > 0 else None,
        "n_trades": len(pnls), "wins": len(wins), "losses": len(losses),
        "win_rate_pct": round(100 * len(wins) / len(pnls), 1) if pnls else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else (None if not wins else float("inf")),
        "avg_trade": round(sum(pnls) / len(pnls), 2) if pnls else 0.0,
        "avg_win": round(sum(wins) / len(wins), 2) if wins else 0.0,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0.0,
        "best_trade": round(max(pnls), 2) if pnls else 0.0, "worst_trade": round(min(pnls), 2) if pnls else 0.0,
        "fees_paid": round(fees, 2), "avg_bars_held": round(sum(bars_held) / len(bars_held), 1) if bars_held else 0.0,
    }


def buy_and_hold(df: pd.DataFrame, initial_capital: float, fee_fn, slippage_bps: float, symbol: str,
                 periods_per_year: float, fractional: bool = True) -> tuple[pd.Series, dict[str, Any]]:
    """Buy at the first bar's open (slippage + fees applied), hold to the last close."""
    if df.empty:
        return pd.Series(dtype=float), {"total_return_pct": 0.0, "n_trades": 0}
    entry = float(df["open"].iloc[0]) * (1 + slippage_bps / 10_000)
    qty = initial_capital / entry
    if not fractional:
        qty = float(int(qty))
    fees_in = float(fee_fn(symbol, qty, entry, "buy"))
    cash = initial_capital - qty * entry - fees_in
    equity = cash + qty * df["close"].astype(float)
    equity.name = f"B&H {symbol}"
    exit_price = float(df["close"].iloc[-1])
    fees_out = float(fee_fn(symbol, qty, exit_price, "sell"))
    equity.iloc[-1] -= fees_out

    class _T:  # minimal trade record for compute_metrics
        pnl = qty * (exit_price - entry) - fees_in - fees_out
        fees = fees_in + fees_out
        bars_held = len(df)

    m = compute_metrics(equity, [_T()], periods_per_year, initial_capital)
    m["symbol"] = symbol
    return equity, m

"""Daily report: trades, P&L, win rate, max drawdown, fees, and each signal source's
track record against buying and holding SPY / BTC over the same window.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from ..backtest.metrics import max_drawdown
from ..common import NY, ensure_dir, from_iso, to_iso, utcnow
from ..config import Settings
from ..signals.tracker import SourceTracker
from ..storage import Database

log = logging.getLogger(__name__)

# benchmark_fn(symbol, start, end) -> total return fraction over the window (or None)
BenchmarkFn = Callable[[str, datetime, datetime], float | None]


@dataclass
class DailyReport:
    report_date: date
    mode: str
    generated_at: datetime
    account: dict[str, Any]
    risk: dict[str, Any]
    pnl: dict[str, float]
    trades_today: list[dict[str, Any]]
    open_trades: list[dict[str, Any]]
    stats: dict[str, Any]
    sources: list[dict[str, Any]]
    benchmarks: dict[str, Any]
    warnings: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        L: list[str] = []
        L.append(f"# tradesys daily report - {self.report_date} ({self.mode.upper()})")
        L.append(f"_generated {self.generated_at:%Y-%m-%d %H:%M %Z}_")
        L.append("")
        a, r, p = self.account, self.risk, self.pnl
        L.append("## Account & risk")
        L.append(f"- Equity ${a.get('equity', 0):,.2f} | cash ${a.get('cash', 0):,.2f} | capital cap ${r['capital_cap']:,.2f}")
        L.append(f"- Day P&L **{p['daily']:+,.2f}** (realized {p['realized_today']:+,.2f}, unrealized {p['unrealized_intraday']:+,.2f})"
                 f" | limit ${r['daily_loss_limit']:,.2f}")
        L.append(f"- Week P&L **{p['weekly']:+,.2f}** (realized {p['realized_week']:+,.2f}, unrealized {p['unrealized_total']:+,.2f})"
                 f" | limit ${r['weekly_loss_limit']:,.2f}")
        flags = [k for k in ("killed", "daily_halted", "weekly_halted") if r.get(k)]
        L.append(f"- State: {'; '.join(flags) if flags else 'trading normally'} | live armed: {r.get('armed')}")
        L.append("")
        L.append("## Today's closed trades")
        if self.trades_today:
            L.append("| Symbol | Source | Qty | Entry | Exit | Reason | P&L | Fees |")
            L.append("|---|---|---:|---:|---:|---|---:|---:|")
            for t in self.trades_today:
                L.append(f"| {t['symbol']} | {t['source_id']} | {t['qty']:g} | {t['entry_price'] or 0:,.4f} | "
                         f"{t['exit_price'] or 0:,.4f} | {t['exit_reason']} | {t['pnl'] or 0:+,.2f} | {t['fees'] or 0:,.2f} |")
        else:
            L.append("_none_")
        L.append("")
        L.append("## Open trades")
        if self.open_trades:
            L.append("| Symbol | Source | Qty | Entry | Stop | Target | Unrealized |")
            L.append("|---|---|---:|---:|---:|---:|---:|")
            for t in self.open_trades:
                L.append(f"| {t['symbol']} | {t['source_id']} | {t['qty']:g} | {t['entry_price'] or 0:,.4f} | "
                         f"{t['stop_price'] or 0:,.4f} | {t['target_price'] or 0:,.4f} | {t.get('unrealized', 0):+,.2f} |")
        else:
            L.append("_none_")
        L.append("")
        s = self.stats
        L.append("## Statistics")
        L.append(f"- Today: {s['today_trades']} trades, win rate {s['today_win_rate']:.0f}%, fees ${s['today_fees']:,.2f}")
        L.append(f"- Last 30 days: {s['month_trades']} trades, win rate {s['month_win_rate']:.0f}%, net {s['month_pnl']:+,.2f}, "
                 f"fees ${s['month_fees']:,.2f}")
        L.append(f"- All time ({self.mode}): {s['all_trades']} trades, win rate {s['all_win_rate']:.0f}%, net {s['all_pnl']:+,.2f}, "
                 f"fees ${s['all_fees']:,.2f}")
        L.append(f"- Max drawdown of closed-trade P&L: ${s['max_drawdown_usd']:,.2f} ({s['max_drawdown_pct']:.2f}% of capital cap)")
        if s.get("equity_drawdown_pct") is not None:
            L.append(f"- Max drawdown of account equity (snapshots): {s['equity_drawdown_pct']:.2f}%")
        L.append("")
        L.append("## Signal sources vs buy-and-hold")
        L.append("| Source | Kind | Status | Approved | Trades | Win% | Net P&L | Last-20 P&L | Max DD | B&H SPY | B&H BTC |")
        L.append("|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|")
        for src in self.sources:
            L.append(f"| {src['name']} (`{src['source_id']}`) | {src['kind']} | {src['status']} | {'yes' if src['approved'] else 'no'} | "
                     f"{src['trades']} | {src['win_rate'] * 100:.0f} | {src['net_pnl']:+,.2f} | {src['last_window_pnl']:+,.2f} | "
                     f"{src['max_drawdown']:,.2f} | {_fmt_bench(src.get('bh_spy'))} | {_fmt_bench(src.get('bh_btc'))} |")
        if not self.sources:
            L.append("| _no sources yet_ | | | | | | | | | | |")
        L.append("")
        b = self.benchmarks
        if b:
            L.append(f"_B&H columns: what ${self.risk['capital_cap']:,.0f} in SPY / BTC would have made over each source's "
                     f"active window. Today: SPY {_fmt_pct(b.get('spy_today'))}, BTC {_fmt_pct(b.get('btc_today'))}._")
        if self.warnings:
            L.append("")
            L.append("## Warnings")
            L.extend(f"- {w}" for w in self.warnings)
        return "\n".join(L)


def _fmt_bench(v: float | None) -> str:
    return "n/a" if v is None else f"{v:+,.2f}"


def _fmt_pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v * 100:+.2f}%"


def _win_rate(trades: list[dict]) -> float:
    if not trades:
        return 0.0
    return 100.0 * sum(1 for t in trades if (t["pnl"] or 0) > 0) / len(trades)


def build_report(settings: Settings, db: Database, tracker: SourceTracker, risk_status: dict, pnl: dict,
                 account: dict | None = None, positions: list | None = None, report_date: date | None = None,
                 benchmark_fn: BenchmarkFn | None = None, now: datetime | None = None) -> DailyReport:
    now = now or utcnow()
    report_date = report_date or now.astimezone(NY).date()
    day_start = datetime(report_date.year, report_date.month, report_date.day, tzinfo=NY)
    day_end = day_start + timedelta(days=1)
    mode = settings.mode
    warnings: list[str] = []

    closed = [t for t in db.list_trades(status="closed", mode=mode)]
    closed.sort(key=lambda t: (t["exit_time"] or "", t["id"]))
    today = [t for t in closed if t["exit_time"] and to_iso(day_start) <= t["exit_time"] < to_iso(day_end)]
    month = [t for t in closed if t["exit_time"] and t["exit_time"] >= (to_iso(now - timedelta(days=30)) or "")]

    pos_by_symbol = {p.symbol: p for p in (positions or [])}
    open_trades = []
    for t in db.open_trades(mode=mode):
        p = pos_by_symbol.get(t["symbol"])
        unreal = ((p.current_price - float(t["entry_price"] or p.avg_entry_price)) * float(t["qty"])) if p and t["entry_price"] else 0.0
        open_trades.append({**t, "unrealized": unreal})

    pnls = [float(t["pnl"] or 0) for t in closed]
    dd_usd = 0.0
    if pnls:
        import pandas as pd
        curve = pd.Series(pnls).cumsum() + settings.total_capital_cap
        _, dd_usd = max_drawdown(curve)
    eq_dd = None
    hist = db.equity_history(mode)
    if len(hist) > 1:
        import pandas as pd
        eq_pct, _ = max_drawdown(pd.Series([h["equity"] for h in hist]))
        eq_dd = eq_pct * 100

    stats = {
        "today_trades": len(today), "today_win_rate": _win_rate(today), "today_fees": sum(float(t["fees"] or 0) for t in today),
        "month_trades": len(month), "month_win_rate": _win_rate(month), "month_pnl": sum(float(t["pnl"] or 0) for t in month),
        "month_fees": sum(float(t["fees"] or 0) for t in month),
        "all_trades": len(closed), "all_win_rate": _win_rate(closed), "all_pnl": sum(pnls),
        "all_fees": sum(float(t["fees"] or 0) for t in closed),
        "max_drawdown_usd": dd_usd, "max_drawdown_pct": 100 * dd_usd / settings.total_capital_cap if settings.total_capital_cap else 0.0,
        "equity_drawdown_pct": eq_dd,
    }

    sources: list[dict[str, Any]] = []
    for st in tracker.all_stats():
        row = st.as_dict()
        row["bh_spy"] = row["bh_btc"] = None
        if benchmark_fn and st.trades:
            trades = tracker.db.list_trades(source_id=st.source_id, status="closed")
            starts = [from_iso(t["entry_time"]) for t in trades if t["entry_time"]]
            ends = [from_iso(t["exit_time"]) for t in trades if t["exit_time"]]
            if starts and ends:
                w_start, w_end = min(starts), max(ends)
                for key, sym in (("bh_spy", "SPY"), ("bh_btc", "BTC/USD")):
                    try:
                        ret = benchmark_fn(sym, w_start, w_end)
                        row[key] = None if ret is None else ret * settings.total_capital_cap
                    except Exception as e:
                        warnings.append(f"benchmark {sym} for {st.source_id} failed: {e}")
        sources.append(row)

    benchmarks: dict[str, Any] = {}
    if benchmark_fn:
        for key, sym in (("spy_today", "SPY"), ("btc_today", "BTC/USD")):
            try:
                benchmarks[key] = benchmark_fn(sym, day_start, min(now, day_end))
            except Exception as e:
                warnings.append(f"benchmark {sym} today failed: {e}")
    if settings.limits_defaulted:
        warnings.append("dollar limits are placeholders (paper defaults); set TOTAL_CAPITAL_CAP / DAILY_LOSS_LIMIT / WEEKLY_LOSS_LIMIT")

    return DailyReport(report_date=report_date, mode=mode, generated_at=now.astimezone(NY), account=account or {},
                       risk=risk_status, pnl=pnl, trades_today=today, open_trades=open_trades, stats=stats,
                       sources=sources, benchmarks=benchmarks, warnings=warnings)


def save_report(settings: Settings, report: DailyReport) -> Path:
    out = ensure_dir(settings.reports_dir) / f"{report.report_date.isoformat()}-{report.mode}.md"
    out.write_text(report.to_markdown())
    return out


def market_benchmark_fn(market_data) -> BenchmarkFn:
    """Total return of `symbol` between two datetimes using daily bars (crypto) / daily bars (stocks)."""
    def fn(symbol: str, start: datetime, end: datetime) -> float | None:
        if end <= start:
            end = start + timedelta(days=1)
        df = market_data.get_bars(symbol, "1Day", start=start - timedelta(days=5), end=end + timedelta(days=1))
        df = df[(df.index >= start - timedelta(days=5)) & (df.index <= end + timedelta(days=1))]
        if len(df) < 1:
            return None
        before = df[df.index <= start]
        first = float(before["close"].iloc[-1]) if len(before) else float(df["open"].iloc[0])
        upto = df[df.index <= end]
        last = float(upto["close"].iloc[-1]) if len(upto) else float(df["close"].iloc[-1])
        return last / first - 1.0 if first else None
    return fn

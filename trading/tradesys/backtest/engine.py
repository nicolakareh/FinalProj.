"""Event-driven, portfolio-level backtester.

Mechanics mirror live execution as closely as possible:
  * a signal on bar i is filled at bar i+1's open (no same-bar fills),
  * slippage is applied against you on every market fill,
  * fees follow the same FeeModel the live tracker uses,
  * sizing uses risk.sizing.position_size with the same capital cap / 2% rule,
  * stops are checked against each bar's low (gaps fill at the open), targets against the high,
    and when both are touched in one bar the stop is assumed to fill first.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from ..common import is_crypto
from ..risk.sizing import position_size
from ..strategies.base import Intent, PositionState, Strategy
from .metrics import compute_metrics


@dataclass
class FeeModel:
    """Alpaca has no commissions on stocks; sells carry small regulatory fees. Crypto pays a % fee."""
    stock_commission_per_share: float = 0.0
    stock_sell_sec_fee_pct: float = 0.00278   # SEC Section 31 fee: $27.80 per $1M sold (percent of notional)
    stock_sell_finra_taf_per_share: float = 0.000166
    stock_sell_finra_taf_cap: float = 8.30
    crypto_fee_pct: float = 0.25               # Alpaca tier-1 taker fee

    def fee(self, symbol: str, qty: float, price: float, side: str) -> float:
        notional = abs(qty * price)
        if is_crypto(symbol):
            return notional * self.crypto_fee_pct / 100.0
        fee = abs(qty) * self.stock_commission_per_share
        if side == "sell":
            fee += notional * self.stock_sell_sec_fee_pct / 100.0
            fee += min(abs(qty) * self.stock_sell_finra_taf_per_share, self.stock_sell_finra_taf_cap)
        return fee


@dataclass
class BacktestConfig:
    initial_capital: float = 10_000.0
    risk_pct: float = 2.0
    slippage_bps_stock: float = 5.0
    slippage_bps_crypto: float = 10.0
    max_open_positions: int = 10
    fees: FeeModel = field(default_factory=FeeModel)

    def slippage(self, symbol: str) -> float:
        return (self.slippage_bps_crypto if is_crypto(symbol) else self.slippage_bps_stock) / 10_000.0


@dataclass
class BacktestTrade:
    symbol: str
    entry_time: datetime
    exit_time: datetime
    qty: float
    entry_price: float
    exit_price: float
    stop_price: float
    target_price: float | None
    pnl: float
    fees: float
    exit_reason: str
    bars_held: int
    reason: str = ""


@dataclass
class BacktestResult:
    strategy: str
    params: dict[str, Any]
    symbols: list[str]
    timeframe: str
    config: BacktestConfig
    equity: pd.Series
    trades: list[BacktestTrade]
    metrics: dict[str, Any]
    benchmarks: dict[str, dict[str, Any]] = field(default_factory=dict)
    per_symbol: dict[str, dict[str, Any]] = field(default_factory=dict)
    sufficient_history: bool = True
    history_days: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def start(self) -> datetime:
        return self.equity.index[0].to_pydatetime()

    @property
    def end(self) -> datetime:
        return self.equity.index[-1].to_pydatetime()

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy, "params": self.params, "symbols": self.symbols, "timeframe": self.timeframe,
            "config": {**asdict(self.config), "fees": asdict(self.config.fees)},
            "start": str(self.start), "end": str(self.end), "history_days": self.history_days,
            "sufficient_history": self.sufficient_history, "metrics": self.metrics, "benchmarks": self.benchmarks,
            "per_symbol": self.per_symbol, "warnings": self.warnings,
            "trades": [{**asdict(t), "entry_time": str(t.entry_time), "exit_time": str(t.exit_time)} for t in self.trades],
            "equity": {str(k): round(float(v), 2) for k, v in self.equity.iloc[:: max(1, len(self.equity) // 2000)].items()},
        }


class Backtester:
    def __init__(self, config: BacktestConfig | None = None):
        self.config = config or BacktestConfig()

    def run(self, strategy: Strategy, data: dict[str, pd.DataFrame], timeframe: str,
            periods_per_year: float = 252.0) -> BacktestResult:
        cfg = self.config
        prepared = {sym: strategy.prepare(df) for sym, df in data.items() if len(df)}
        if not prepared:
            raise ValueError("no data to backtest")
        pos_index = {sym: {ts: i for i, ts in enumerate(df.index)} for sym, df in prepared.items()}
        timeline = sorted(set().union(*[set(df.index) for df in prepared.values()]))

        cash = cfg.initial_capital
        positions: dict[str, PositionState] = {}
        pending: dict[str, Intent] = {}
        last_close: dict[str, float] = {}
        trades: list[BacktestTrade] = []
        equity_points: list[tuple[Any, float]] = []
        bars_in_market = 0

        def deployed() -> float:
            return sum(p.qty * p.entry_price for p in positions.values())

        def close_position(sym: str, price: float, ts, reason: str, i: int) -> None:
            nonlocal cash
            pos = positions.pop(sym)
            fee = cfg.fees.fee(sym, pos.qty, price, "sell")
            cash += pos.qty * price - fee
            entry_fee = getattr(pos, "entry_fee", 0.0)
            pnl = (price - pos.entry_price) * pos.qty - fee - entry_fee
            trades.append(BacktestTrade(sym, getattr(pos, "entry_time"), ts, pos.qty, pos.entry_price, price,
                                        pos.stop_price or 0.0, pos.target_price, pnl, fee + entry_fee, reason,
                                        i - pos.entry_index, getattr(pos, "reason", "")))

        for ts in timeline:
            for sym, df in prepared.items():
                i = pos_index[sym].get(ts)
                if i is None:
                    continue
                bar = df.iloc[i]
                o, h, l, c = float(bar["open"]), float(bar["high"]), float(bar["low"]), float(bar["close"])
                if any(math.isnan(x) for x in (o, h, l, c)):
                    continue
                last_close[sym] = c
                slip = cfg.slippage(sym)

                # 1) fill last bar's intent at this bar's open
                intent = pending.pop(sym, None)
                if intent is not None:
                    if intent.action == "buy" and sym not in positions and len(positions) < cfg.max_open_positions:
                        fill = o * (1 + slip)
                        stop = float(intent.stop_price)
                        if fill > stop:
                            qty = position_size(cfg.initial_capital, cfg.risk_pct, fill, stop, cash, deployed(),
                                                fractional=is_crypto(sym))
                            if qty > 0:
                                fee = cfg.fees.fee(sym, qty, fill, "buy")
                                if qty * fill + fee <= cash:
                                    cash -= qty * fill + fee
                                    pos = PositionState(qty, fill, stop, intent.target_price, i, 0)
                                    pos.entry_fee = fee          # type: ignore[attr-defined]
                                    pos.entry_time = ts          # type: ignore[attr-defined]
                                    pos.reason = intent.reason   # type: ignore[attr-defined]
                                    positions[sym] = pos
                    elif intent.action == "sell" and sym in positions:
                        close_position(sym, o * (1 - slip), ts, "signal", i)

                # 2) stops and targets on this bar
                pos = positions.get(sym)
                if pos is not None:
                    if pos.stop_price is not None and l <= pos.stop_price:
                        px = (o if o < pos.stop_price else pos.stop_price) * (1 - slip)
                        close_position(sym, px, ts, "stop", i)
                    elif pos.target_price is not None and h >= pos.target_price:
                        px = o if o > pos.target_price else pos.target_price
                        close_position(sym, px, ts, "target", i)
                    else:
                        pos.bars_held = i - pos.entry_index

                # 3) strategy decision at the close
                if i >= strategy.warmup:
                    new_intent = strategy.on_bar(df, i, positions.get(sym))
                    if new_intent is not None:
                        pending[sym] = new_intent

            equity = cash + sum(p.qty * last_close.get(s, p.entry_price) for s, p in positions.items())
            equity_points.append((ts, equity))
            if positions:
                bars_in_market += 1

        # liquidate anything still open at the last close so metrics are realised
        final_ts = timeline[-1]
        for sym in list(positions):
            df = prepared[sym]
            close_position(sym, float(df["close"].iloc[-1]) * (1 - cfg.slippage(sym)), final_ts, "end_of_test",
                           len(df) - 1)
        equity_points[-1] = (final_ts, cash)

        equity = pd.Series({ts: v for ts, v in equity_points}, name="strategy")
        equity.index = pd.DatetimeIndex(equity.index)
        metrics = compute_metrics(equity, trades, periods_per_year, cfg.initial_capital)
        metrics["exposure_pct"] = round(100 * bars_in_market / max(len(timeline), 1), 1)
        per_symbol: dict[str, dict[str, Any]] = {}
        for sym in prepared:
            st = [t for t in trades if t.symbol == sym]
            pn = [t.pnl for t in st]
            per_symbol[sym] = {"n_trades": len(st), "net_pnl": round(sum(pn), 2),
                               "win_rate_pct": round(100 * sum(1 for p in pn if p > 0) / len(pn), 1) if pn else 0.0,
                               "fees": round(sum(t.fees for t in st), 2)}
        first = min(df.index[0] for df in prepared.values())
        last = max(df.index[-1] for df in prepared.values())
        return BacktestResult(strategy=strategy.name, params=dict(strategy.params), symbols=list(prepared),
                              timeframe=timeframe, config=cfg, equity=equity, trades=trades, metrics=metrics,
                              per_symbol=per_symbol, history_days=(last - first).days)

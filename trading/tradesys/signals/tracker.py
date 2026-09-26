"""Per-source track record: every strategy, Discord caller and news trigger gets its
own ledger of trades with real P&L. A source whose net P&L over its last
EVAL_WINDOW closed trades is negative is disabled automatically and stays disabled
until you re-enable it by hand.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Iterable

from ..alerts import Notifier
from ..common import from_iso, utcnow
from ..storage import Database
from .models import Signal

log = logging.getLogger(__name__)

EVAL_WINDOW = 20
TRACKED_MODES: tuple[str, ...] = ("live", "paper", "shadow")


@dataclass
class SourceStats:
    source_id: str
    kind: str
    name: str
    status: str
    approved: bool
    trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    net_pnl: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    fees: float = 0.0
    avg_pnl: float = 0.0
    profit_factor: float | None = None
    max_drawdown: float = 0.0
    last_window_trades: int = 0
    last_window_pnl: float = 0.0
    open_trades: int = 0
    by_mode: dict[str, int] = field(default_factory=dict)
    disabled_reason: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _max_drawdown(pnls: Iterable[float]) -> float:
    """Largest peak-to-trough fall of the cumulative P&L curve (a positive number)."""
    peak = 0.0
    equity = 0.0
    worst = 0.0
    for p in pnls:
        equity += p
        peak = max(peak, equity)
        worst = max(worst, peak - equity)
    return worst


class SourceTracker:
    def __init__(self, db: Database, notifier: Notifier | None = None, eval_window: int = EVAL_WINDOW,
                 min_trades: int | None = None):
        self.db = db
        self.notifier = notifier
        self.eval_window = eval_window
        self.min_trades = eval_window if min_trades is None else min_trades

    # ------------------------------------------------------------- sources
    def register(self, source_id: str, kind: str, name: str) -> dict:
        return self.db.upsert_source(source_id, kind, name)

    def is_active(self, source_id: str) -> bool:
        row = self.db.get_source(source_id)
        return bool(row) and row["status"] == "active"

    def enable(self, source_id: str) -> None:
        self.db.set_source_status(source_id, "active")
        log.info("source %s re-enabled", source_id)

    def disable(self, source_id: str, reason: str) -> None:
        self.db.set_source_status(source_id, "disabled", reason)
        log.warning("source %s disabled: %s", source_id, reason)
        if self.notifier:
            self.notifier.notify("SOURCE_DISABLED", f"{source_id}: {reason}")

    # ------------------------------------------------------------- signals
    def record_signal(self, signal: Signal, status: str = "new", reason: str | None = None) -> int:
        self.register(signal.source_id, signal.source_kind, signal.source_name)
        return self.db.insert_signal(signal.source_id, signal.symbol, signal.direction.value, signal.entry,
                                     signal.stop, signal.target, signal.timestamp, signal.raw_text, status, reason)

    # -------------------------------------------------------------- trades
    def open_trade(self, source_id: str, symbol: str, mode: str, qty: float, entry_price: float | None,
                   stop_price: float | None, target_price: float | None, entry_time: datetime | None = None,
                   signal_id: int | None = None, status: str = "open", **order_ids) -> int:
        if mode not in TRACKED_MODES:
            raise ValueError(f"unknown trade mode {mode}")
        return self.db.insert_trade(source_id=source_id, signal_id=signal_id, symbol=symbol, mode=mode, qty=qty,
                                    entry_price=entry_price, stop_price=stop_price, target_price=target_price,
                                    entry_time=entry_time or utcnow(), status=status, **order_ids)

    def close_trade(self, trade_id: int, exit_price: float, exit_time: datetime | None = None,
                    exit_reason: str = "signal", fees: float = 0.0, qty: float | None = None) -> dict:
        trade = self.db.get_trade(trade_id)
        if trade is None:
            raise KeyError(f"trade {trade_id} not found")
        if trade["status"] == "closed":
            return trade
        q = float(qty if qty is not None else trade["qty"])
        entry = float(trade["entry_price"] or exit_price)
        total_fees = float(trade["fees"] or 0.0) + float(fees)
        pnl = (float(exit_price) - entry) * q - total_fees
        self.db.update_trade(trade_id, status="closed", exit_price=float(exit_price), exit_time=exit_time or utcnow(),
                             exit_reason=exit_reason, pnl=round(pnl, 6), fees=round(total_fees, 6), qty=q)
        updated = self.db.get_trade(trade_id)
        self.evaluate(trade["source_id"])
        return updated  # type: ignore[return-value]

    def cancel_trade(self, trade_id: int, reason: str = "canceled") -> None:
        self.db.update_trade(trade_id, status="canceled", exit_reason=reason, exit_time=utcnow())

    # ---------------------------------------------------------- evaluation
    def evaluate(self, source_id: str) -> bool:
        """Disable the source if its last `eval_window` closed trades net out negative.

        Returns True when this call disabled the source.
        """
        recent = self.db.closed_trades_for_source(source_id, limit=self.eval_window, modes=TRACKED_MODES)
        if len(recent) < self.min_trades:
            return False
        window_pnl = sum(float(t["pnl"] or 0.0) for t in recent)
        if window_pnl < 0 and self.is_active(source_id):
            self.disable(source_id, f"net P&L over last {len(recent)} trades is {window_pnl:+.2f}")
            return True
        return False

    # --------------------------------------------------------------- stats
    def stats(self, source_id: str) -> SourceStats:
        src = self.db.get_source(source_id) or {"id": source_id, "kind": "?", "name": source_id, "status": "unknown",
                                                "disabled_reason": None}
        approved = self.db.get_approval(source_id) is not None
        closed = [t for t in self.db.list_trades(source_id=source_id, status="closed") if t["mode"] in TRACKED_MODES]
        closed.sort(key=lambda t: (t["exit_time"] or "", t["id"]))
        pnls = [float(t["pnl"] or 0.0) for t in closed]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        gross_profit = sum(wins)
        gross_loss = -sum(losses)
        recent = pnls[-self.eval_window:]
        by_mode: dict[str, int] = {}
        for t in closed:
            by_mode[t["mode"]] = by_mode.get(t["mode"], 0) + 1
        open_n = len([t for t in self.db.list_trades(source_id=source_id) if t["status"] in ("open", "pending")])
        return SourceStats(
            source_id=source_id, kind=src["kind"], name=src["name"], status=src["status"], approved=approved,
            trades=len(pnls), wins=len(wins), losses=len(losses),
            win_rate=(len(wins) / len(pnls)) if pnls else 0.0, net_pnl=sum(pnls), gross_profit=gross_profit,
            gross_loss=gross_loss, fees=sum(float(t["fees"] or 0.0) for t in closed),
            avg_pnl=(sum(pnls) / len(pnls)) if pnls else 0.0,
            profit_factor=(gross_profit / gross_loss) if gross_loss > 0 else (None if not wins else float("inf")),
            max_drawdown=_max_drawdown(pnls), last_window_trades=len(recent), last_window_pnl=sum(recent),
            open_trades=open_n, by_mode=by_mode, disabled_reason=src.get("disabled_reason"),
        )

    def all_stats(self) -> list[SourceStats]:
        return [self.stats(s["id"]) for s in self.db.list_sources()]

    def equity_curve(self, source_id: str) -> list[tuple[datetime, float]]:
        closed = [t for t in self.db.list_trades(source_id=source_id, status="closed") if t["mode"] in TRACKED_MODES]
        closed.sort(key=lambda t: (t["exit_time"] or "", t["id"]))
        out, total = [], 0.0
        for t in closed:
            total += float(t["pnl"] or 0.0)
            out.append((from_iso(t["exit_time"]) or utcnow(), total))
        return out

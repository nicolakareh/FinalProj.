"""Turns approved signals into risk-checked orders and keeps the trade ledger in sync
with broker fills.

Flow for a LONG signal:
  signal -> source active? -> source approved? (else shadow-track) -> price, stop, size
  -> RiskManager.evaluate (signed approval) -> broker.submit -> trade 'pending'
  -> fill event -> trade 'open' (+ protective stop order for crypto) -> stop/target/exit fill
  -> trade 'closed' with P&L -> tracker re-evaluates the source -> loss limits re-checked.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Callable

from ..alerts import Notifier
from ..backtest.engine import FeeModel
from ..common import from_iso, is_crypto, to_iso, utcnow
from ..config import Settings, StrategyConfig
from ..risk.manager import RiskManager
from ..risk.sizing import position_size
from ..signals.models import Direction, Signal
from ..signals.tracker import SourceTracker
from ..storage import Database
from ..strategies.base import Intent
from .approvals import ApprovalRegistry
from .models import OrderIntent, OrderSnapshot

log = logging.getLogger(__name__)

TERMINAL_EVENTS = {"canceled", "expired", "rejected", "done_for_day"}


class Executor:
    def __init__(self, settings: Settings, db: Database, broker, risk: RiskManager, approvals: ApprovalRegistry,
                 tracker: SourceTracker, notifier: Notifier | None = None,
                 price_lookup: Callable[[str], float | None] | None = None, fees: FeeModel | None = None,
                 shadow_max_days: int = 10):
        self.settings = settings
        self.db = db
        self.broker = broker
        self.risk = risk
        self.approvals = approvals
        self.tracker = tracker
        self.notifier = notifier
        self.price_lookup = price_lookup or (lambda s: None)
        self.fees = fees or FeeModel()
        self.mode = settings.mode
        self.shadow_max_days = shadow_max_days

    # ------------------------------------------------------------ helpers
    def _notify(self, kind: str, msg: str) -> None:
        if self.notifier:
            self.notifier.notify(kind, msg)

    def _price(self, symbol: str, hint: float | None) -> float | None:
        if hint and hint > 0:
            return float(hint)
        try:
            p = self.price_lookup(symbol)
            return float(p) if p else None
        except Exception as e:
            log.warning("price lookup for %s failed: %s", symbol, e)
            return None

    def open_trade_for(self, source_id: str, symbol: str, mode: str) -> dict | None:
        for t in self.db.open_trades(mode=mode):
            if t["source_id"] == source_id and t["symbol"] == symbol:
                return t
        return None

    def _deployed(self, positions, open_orders) -> float:
        deployed = sum(float(p.cost_basis) for p in positions if p.qty > 0)
        deployed += sum(o.remaining_qty * float(o.limit_price or o.stop_price or 0.0)
                        for o in open_orders if o.side == "buy" and o.is_open)
        return deployed

    # ------------------------------------------------------------ signals
    def handle_strategy_intent(self, cfg: StrategyConfig, symbol: str, intent: Intent, price: float,
                               code_hash: str, now: datetime | None = None) -> str:
        signal = Signal(source_id=cfg.source_id, source_kind="strategy", source_name=cfg.name, symbol=symbol,
                        direction=Direction.LONG if intent.action == "buy" else Direction.CLOSE,
                        timestamp=now or utcnow(), entry=price, stop=intent.stop_price, target=intent.target_price,
                        raw_text=intent.reason, meta={"code_hash": code_hash})
        return self.handle_signal(signal, price)

    def handle_signal(self, signal: Signal, price: float | None = None) -> str:
        """Returns 'accepted' (real order placed), 'tracked' (shadow only) or 'rejected'."""
        sig_id = self.tracker.record_signal(signal)

        def reject(reason: str) -> str:
            self.db.set_signal_status(sig_id, "rejected", reason)
            log.info("signal %s from %s rejected: %s", signal.symbol, signal.source_id, reason)
            return "rejected"

        if not self.tracker.is_active(signal.source_id):
            return reject("source is disabled")
        if signal.direction == Direction.SHORT:
            return reject("shorting is not allowed")
        if signal.meta.get("instrument") == "option":
            return reject("options are not traded")
        if signal.meta.get("parse_ok") is False:
            return reject(signal.meta.get("parse_reason") or "unparseable levels")

        code_hash = signal.meta.get("code_hash") if signal.source_kind == "strategy" else None
        approved, why = self.approvals.is_approved(signal.source_id, code_hash)

        if signal.direction == Direction.CLOSE:
            if approved:
                trade = self.open_trade_for(signal.source_id, signal.symbol, self.mode)
                if trade is None or trade["status"] != "open":
                    return reject("no open trade to close")
                ok = self.exit_trade(trade, "signal")
                self.db.set_signal_status(sig_id, "ordered" if ok else "rejected", None if ok else "exit rejected")
                return "accepted" if ok else "rejected"
            self._close_shadow(signal.source_id, signal.symbol, self._price(signal.symbol, price), "signal")
            self.db.set_signal_status(sig_id, "tracked", why)
            return "tracked"

        if not approved:
            self._open_shadow(signal, sig_id, price)
            self.db.set_signal_status(sig_id, "tracked", why)
            return "tracked"
        return self._enter(signal, sig_id, price, reject)

    # ------------------------------------------------------------ entries
    def _enter(self, signal: Signal, sig_id: int, price: float | None, reject) -> str:
        symbol = signal.symbol
        ref = self._price(symbol, price if price else signal.entry)
        if ref is None:
            return reject("no price available")
        stop = float(signal.stop) if signal.stop else ref * (1 - self.settings.default_stop_pct / 100.0)
        if stop >= ref:
            return reject(f"stop {stop} is not below entry {ref}")
        target = float(signal.target) if signal.target and signal.target > ref else None
        if self.open_trade_for(signal.source_id, symbol, self.mode) is not None:
            return reject("this source already has an open trade in the symbol")

        try:
            account = self.broker.get_account()
            positions = self.broker.get_positions()
            open_orders = self.broker.get_open_orders()
            asset = self.broker.get_asset(symbol)
            clock = self.broker.get_clock()
        except Exception as e:
            log.exception("broker read failed")
            return reject(f"broker read failed: {e}")

        qty = position_size(self.settings.total_capital_cap, self.settings.max_risk_per_trade_pct, ref, stop,
                            account.spendable_cash, self._deployed(positions, open_orders), fractional=asset.fractionable)
        if qty <= 0:
            return reject("position size rounds to zero (cap, cash or stop distance)")
        intent = OrderIntent(symbol=symbol, side="buy", qty=qty, order_type="market", reference_price=ref,
                             source_id=signal.source_id, reason=signal.raw_text[:200], client_order_id=f"ts-{uuid.uuid4().hex[:20]}",
                             stop_price=round(stop, 6), target_price=(round(target, 6) if target else None))
        decision = self.risk.evaluate(intent, account, positions, open_orders, asset, clock)
        if not decision.allowed:
            return reject(str(decision))

        trade_id = self.tracker.open_trade(signal.source_id, symbol, self.mode, qty, None, intent.stop_price,
                                           intent.target_price, status="pending", signal_id=sig_id)
        try:
            order = self.broker.submit(decision.approval)
        except Exception as e:
            log.exception("order submit failed")
            self.tracker.cancel_trade(trade_id, f"submit failed: {e}")
            self._notify("ERROR", f"Order submit failed for {symbol}: {e}")
            return reject(f"submit failed: {e}")
        self.db.log_order(trade_id, order.id, intent.client_order_id, symbol, "buy", qty, intent.order_type, order.status,
                          {"stop": intent.stop_price, "target": intent.target_price, "source": signal.source_id})
        self.db.update_trade(trade_id, entry_order_id=order.id, **order.leg_ids())
        self.db.set_signal_status(sig_id, "ordered")
        log.info("ORDER %s buy %s x%s stop %s target %s -> %s", self.mode, symbol, qty, intent.stop_price,
                 intent.target_price, order.status)
        return "accepted"

    # ------------------------------------------------------------ exits
    def exit_trade(self, trade: dict, reason: str) -> bool:
        symbol = trade["symbol"]
        for key in ("stop_order_id", "target_order_id"):
            if trade.get(key):
                try:
                    self.broker.cancel_order(trade[key])
                except Exception as e:
                    log.warning("cancel %s %s failed (may already be done): %s", key, trade[key], e)
        try:
            account = self.broker.get_account()
            positions = self.broker.get_positions()
            open_orders = self.broker.get_open_orders()
            asset = self.broker.get_asset(symbol)
        except Exception as e:
            log.exception("broker read failed during exit")
            return False
        pos = next((p for p in positions if p.symbol == symbol), None)
        if pos is None or pos.qty <= 0:
            log.warning("exit requested for %s but no position is held; closing trade as flat", symbol)
            price = self._price(symbol, None) or float(trade.get("entry_price") or 0)
            self.tracker.close_trade(trade["id"], price, exit_reason=f"{reason}:no_position")
            return True
        qty = min(float(trade["qty"]), pos.sellable_qty)
        if not asset.fractionable:
            qty = float(int(qty))
        if qty <= 0:
            return False
        intent = OrderIntent(symbol=symbol, side="sell", qty=qty, order_type="market", reference_price=pos.current_price,
                             source_id=trade["source_id"], reason=reason, client_order_id=f"tx-{uuid.uuid4().hex[:20]}",
                             trade_id=trade["id"])
        decision = self.risk.evaluate(intent, account, positions, open_orders, asset)
        if not decision.allowed:
            log.error("exit for %s rejected: %s", symbol, decision)
            self._notify("ERROR", f"Exit order for {symbol} rejected by risk checks: {decision}")
            return False
        try:
            order = self.broker.submit(decision.approval)
        except Exception as e:
            log.exception("exit submit failed")
            self._notify("ERROR", f"Exit order submit failed for {symbol}: {e}")
            return False
        self.db.log_order(trade["id"], order.id, intent.client_order_id, symbol, "sell", qty, "market", order.status,
                          {"reason": reason})
        self.db.update_trade(trade["id"], exit_order_id=order.id, exit_reason=reason)
        return True

    def exit_all(self, reason: str) -> int:
        n = 0
        for t in self.db.open_trades(mode=self.mode):
            if t["status"] == "open" and self.exit_trade(t, reason):
                n += 1
        return n

    def _place_crypto_stop(self, trade: dict) -> None:
        symbol = trade["symbol"]
        try:
            account = self.broker.get_account()
            positions = self.broker.get_positions()
            open_orders = self.broker.get_open_orders()
            asset = self.broker.get_asset(symbol)
            pos = next((p for p in positions if p.symbol == symbol), None)
            qty = min(float(trade["qty"]), pos.sellable_qty) if pos else float(trade["qty"])
            intent = OrderIntent(symbol=symbol, side="sell", qty=qty, order_type="stop_limit",
                                 reference_price=float(trade["entry_price"]), source_id=trade["source_id"],
                                 reason="protective stop", client_order_id=f"sl-{uuid.uuid4().hex[:20]}",
                                 stop_price=float(trade["stop_price"]), trade_id=trade["id"])
            decision = self.risk.evaluate(intent, account, positions, open_orders, asset)
            if not decision.allowed:
                raise RuntimeError(str(decision))
            order = self.broker.submit_protective_stop(decision.approval)
            self.db.update_trade(trade["id"], stop_order_id=order.id)
            self.db.log_order(trade["id"], order.id, intent.client_order_id, symbol, "sell", qty, "stop_limit",
                              order.status, {"stop": trade["stop_price"]})
        except Exception as e:
            log.exception("could not place protective stop for %s", symbol)
            self._notify("ERROR", f"Protective stop for {symbol} could not be placed ({e}); the software stop monitor "
                                  f"will exit at market if price falls below {trade['stop_price']}.")

    # ------------------------------------------------------------ fills
    def on_trade_update(self, event: str, order: OrderSnapshot, extra: dict | None = None) -> None:
        """Idempotent handler for broker trade updates (websocket or reconcile)."""
        extra = extra or {}
        trade = self.db.find_trade_by_order(order.id)
        if trade is None:
            return
        tid = trade["id"]
        price = order.filled_avg_price or extra.get("price") or 0.0
        qty = float(order.filled_qty or extra.get("qty") or trade["qty"])
        if event == "fill" or (event == "partial_fill" and order.status == "filled"):
            if order.id == trade["entry_order_id"] and trade["status"] == "pending":
                fee = self.fees.fee(order.symbol, qty, price, "buy")
                self.db.update_trade(tid, status="open", entry_price=price, qty=qty, entry_time=utcnow(), fees=fee)
                if order.legs:
                    self.db.update_trade(tid, **order.leg_ids())
                self._notify("FILL", f"BUY {order.symbol} x{qty:g} @ {price:,.4f} [{self.mode}] source {trade['source_id']}\n"
                                     f"stop {trade['stop_price']} target {trade['target_price']}")
                if is_crypto(order.symbol):
                    self._place_crypto_stop(self.db.get_trade(tid))  # type: ignore[arg-type]
            elif order.id == trade.get("stop_order_id") and trade["status"] == "open":
                self._close_from_fill(trade, price, qty, "stop", "STOP_HIT")
            elif order.id == trade.get("target_order_id") and trade["status"] == "open":
                self._close_from_fill(trade, price, qty, "target", "TARGET_HIT")
            elif order.id == trade.get("exit_order_id") and trade["status"] == "open":
                self._close_from_fill(trade, price, qty, trade.get("exit_reason") or "signal", "FILL")
        elif event == "partial_fill":
            log.info("partial fill %s %s: %s/%s", order.symbol, order.id, order.filled_qty, order.qty)
        elif event in TERMINAL_EVENTS:
            if order.id == trade["entry_order_id"] and trade["status"] == "pending":
                self.tracker.cancel_trade(tid, f"entry {event}")
                if trade.get("signal_id"):
                    self.db.set_signal_status(trade["signal_id"], "rejected", f"entry order {event}")
            elif order.id == trade.get("stop_order_id") and trade["status"] == "open" and not trade.get("exit_order_id"):
                self._notify("ERROR", f"Stop order for {order.symbol} was {event}; software stop monitor is now the only "
                                      f"protection (stop {trade['stop_price']}).")
                self.db.update_trade(tid, stop_order_id=None)

    def _close_from_fill(self, trade: dict, price: float, qty: float, reason: str, kind: str) -> None:
        fee = self.fees.fee(trade["symbol"], qty, price, "sell")
        closed = self.tracker.close_trade(trade["id"], price, exit_reason=reason, fees=fee, qty=qty)
        pnl = closed["pnl"]
        self._notify(kind, f"{reason.upper()} {trade['symbol']} sold x{qty:g} @ {price:,.4f} [{self.mode}] "
                           f"P&L {pnl:+,.2f} (fees {closed['fees']:.2f}) source {trade['source_id']}")
        try:
            self.risk.check_loss_limits(self.broker.get_account(), self.broker.get_positions())
        except Exception:
            log.exception("loss-limit check after fill failed")

    def reconcile(self) -> None:
        """Poll the broker for trades whose orders may have changed while events were missed."""
        for trade in self.db.open_trades(mode=self.mode):
            for key in ("entry_order_id", "stop_order_id", "target_order_id", "exit_order_id"):
                oid = trade.get(key)
                if not oid:
                    continue
                try:
                    order = self.broker.get_order(oid)
                except Exception as e:
                    log.warning("reconcile: order %s lookup failed: %s", oid, e)
                    continue
                if order.status == "filled":
                    self.on_trade_update("fill", order, {"price": order.filled_avg_price, "qty": order.filled_qty})
                elif order.status in TERMINAL_EVENTS:
                    self.on_trade_update(order.status, order, {})
                trade = self.db.get_trade(trade["id"]) or trade

    def check_software_stops(self, prices: dict[str, float]) -> list[int]:
        """Exit at market when price is through the stop and no live stop order is protecting the trade."""
        exited: list[int] = []
        for trade in self.db.open_trades(mode=self.mode):
            if trade["status"] != "open" or trade.get("exit_order_id"):
                continue
            price = prices.get(trade["symbol"])
            stop = trade.get("stop_price")
            if price is None or stop is None or price > float(stop):
                continue
            stop_live = False
            if trade.get("stop_order_id"):
                try:
                    stop_live = self.broker.get_order(trade["stop_order_id"]).is_open
                except Exception:
                    stop_live = False
            # give a live stop order a little room; act if it is gone or price has fallen through it
            if stop_live and price > float(stop) * 0.995:
                continue
            log.warning("software stop for %s: price %s <= stop %s (stop order live=%s)", trade["symbol"], price, stop, stop_live)
            if self.exit_trade(trade, "stop"):
                exited.append(trade["id"])
        return exited

    # ------------------------------------------------------------ shadow
    def _open_shadow(self, signal: Signal, sig_id: int, price: float | None) -> int | None:
        if self.open_trade_for(signal.source_id, signal.symbol, "shadow") is not None:
            return None
        ref = self._price(signal.symbol, price if price else signal.entry)
        if ref is None:
            return None
        stop = float(signal.stop) if signal.stop else ref * (1 - self.settings.default_stop_pct / 100.0)
        if stop >= ref:
            return None
        target = float(signal.target) if signal.target and signal.target > ref else None
        qty = position_size(self.settings.total_capital_cap, self.settings.max_risk_per_trade_pct, ref, stop,
                            self.settings.total_capital_cap, 0.0, fractional=is_crypto(signal.symbol))
        if qty <= 0:
            return None
        fee = self.fees.fee(signal.symbol, qty, ref, "buy")
        tid = self.tracker.open_trade(signal.source_id, signal.symbol, "shadow", qty, ref, stop, target,
                                      entry_time=signal.timestamp, signal_id=sig_id, status="open")
        self.db.update_trade(tid, fees=fee)
        return tid

    def _close_shadow(self, source_id: str, symbol: str, price: float | None, reason: str) -> None:
        trade = self.open_trade_for(source_id, symbol, "shadow")
        if trade is None or price is None:
            return
        fee = self.fees.fee(symbol, float(trade["qty"]), price, "sell")
        self.tracker.close_trade(trade["id"], price, exit_reason=reason, fees=fee)

    def update_shadow_trades(self, prices: dict[str, float], now: datetime | None = None) -> int:
        now = now or utcnow()
        closed = 0
        for trade in self.db.open_trades(mode="shadow"):
            price = prices.get(trade["symbol"])
            if price is None:
                continue
            reason = None
            if trade["stop_price"] is not None and price <= float(trade["stop_price"]):
                reason, px = "stop", float(trade["stop_price"])
            elif trade["target_price"] is not None and price >= float(trade["target_price"]):
                reason, px = "target", float(trade["target_price"])
            else:
                opened = from_iso(trade["entry_time"]) or now
                if now - opened > timedelta(days=self.shadow_max_days):
                    reason, px = "time", price
            if reason:
                fee = self.fees.fee(trade["symbol"], float(trade["qty"]), px, "sell")
                self.tracker.close_trade(trade["id"], px, exit_time=now, exit_reason=reason, fees=fee)
                closed += 1
        return closed

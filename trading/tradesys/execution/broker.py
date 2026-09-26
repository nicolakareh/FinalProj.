"""Alpaca broker wrapper. `submit` refuses anything that is not a valid RiskApproval,
which is what makes the risk rules unbypassable from the rest of the code base.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Callable, Protocol

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import (GetOrdersRequest, LimitOrderRequest, MarketOrderRequest, StopLimitOrderRequest,
                                     StopLossRequest, TakeProfitRequest)

from ..common import KNOWN_CRYPTO, is_crypto
from ..config import Settings
from ..risk.manager import RiskApproval, verify_approval
from .models import AccountSnapshot, AssetInfo, ClockInfo, OrderSnapshot, PositionSnapshot

log = logging.getLogger(__name__)


def round_price(symbol: str, price: float) -> float:
    """Alpaca accepts 2 decimals at/above $1 and 4 below for stocks; crypto tolerates more."""
    if is_crypto(symbol):
        return round(price, 2) if price >= 1 else round(price, 6)
    return round(price, 2) if price >= 1 else round(price, 4)


def normalize_broker_symbol(symbol: str, asset_class: str | None = None) -> str:
    """Positions come back as BTCUSD while orders use BTC/USD; we always use the slash form."""
    if "/" in symbol:
        return symbol
    if asset_class == "crypto" or symbol[:-3] in KNOWN_CRYPTO:
        for quote in ("USDT", "USDC", "USD", "BTC"):
            if symbol.endswith(quote) and len(symbol) > len(quote):
                return f"{symbol[:-len(quote)]}/{quote}"
    return symbol


class Broker(Protocol):
    mode: str

    def get_account(self) -> AccountSnapshot: ...
    def get_positions(self) -> list[PositionSnapshot]: ...
    def get_open_orders(self) -> list[OrderSnapshot]: ...
    def get_order(self, order_id: str) -> OrderSnapshot: ...
    def submit(self, approval: RiskApproval) -> OrderSnapshot: ...
    def submit_protective_stop(self, approval: RiskApproval) -> OrderSnapshot: ...
    def cancel_order(self, order_id: str) -> None: ...
    def cancel_all_orders(self) -> int: ...
    def close_all_positions(self) -> list: ...
    def get_asset(self, symbol: str) -> AssetInfo: ...
    def get_clock(self) -> ClockInfo: ...


def _f(x, default=0.0) -> float:
    try:
        return float(x) if x is not None else default
    except (TypeError, ValueError):
        return default


def _enum_val(x) -> str:
    return str(getattr(x, "value", x) or "")


def snapshot_order(o) -> OrderSnapshot:
    asset_class = _enum_val(getattr(o, "asset_class", "us_equity")) or "us_equity"
    legs = [snapshot_order(l) for l in (getattr(o, "legs", None) or [])]
    return OrderSnapshot(
        id=str(o.id), client_order_id=str(getattr(o, "client_order_id", "") or ""),
        symbol=normalize_broker_symbol(str(o.symbol), asset_class), side=_enum_val(o.side), qty=_f(o.qty),
        filled_qty=_f(o.filled_qty), filled_avg_price=(_f(o.filled_avg_price) if o.filled_avg_price is not None else None),
        order_type=_enum_val(getattr(o, "order_type", None) or getattr(o, "type", "")), status=_enum_val(o.status),
        order_class=_enum_val(getattr(o, "order_class", "simple")) or "simple",
        stop_price=(_f(o.stop_price) if getattr(o, "stop_price", None) is not None else None),
        limit_price=(_f(o.limit_price) if getattr(o, "limit_price", None) is not None else None), legs=legs,
        created_at=getattr(o, "created_at", None), filled_at=getattr(o, "filled_at", None), asset_class=asset_class,
    )


class AlpacaBroker:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.mode = settings.mode
        self.client = TradingClient(settings.alpaca_api_key, settings.alpaca_secret_key, paper=not settings.live_mode)

    # ------------------------------------------------------------ reads
    def get_account(self) -> AccountSnapshot:
        a = self.client.get_account()
        nmbp = getattr(a, "non_marginable_buying_power", None)
        return AccountSnapshot(
            cash=_f(a.cash), equity=_f(a.equity), last_equity=_f(a.last_equity), buying_power=_f(a.buying_power),
            non_marginable_buying_power=(_f(nmbp) if nmbp is not None else None), multiplier=_f(a.multiplier, 1.0),
            shorting_enabled=bool(a.shorting_enabled), pattern_day_trader=bool(a.pattern_day_trader),
            daytrade_count=int(a.daytrade_count or 0), trading_blocked=bool(a.trading_blocked),
            account_blocked=bool(a.account_blocked), currency=str(a.currency or "USD"),
        )

    def get_positions(self) -> list[PositionSnapshot]:
        out = []
        for p in self.client.get_all_positions():
            ac = _enum_val(p.asset_class) or "us_equity"
            out.append(PositionSnapshot(
                symbol=normalize_broker_symbol(str(p.symbol), ac), qty=_f(p.qty), avg_entry_price=_f(p.avg_entry_price),
                current_price=_f(p.current_price), market_value=_f(p.market_value), cost_basis=_f(p.cost_basis),
                unrealized_pl=_f(p.unrealized_pl), unrealized_intraday_pl=_f(p.unrealized_intraday_pl),
                qty_available=(_f(p.qty_available) if getattr(p, "qty_available", None) is not None else None),
                side=_enum_val(p.side) or "long", asset_class=ac,
            ))
        return out

    def get_open_orders(self) -> list[OrderSnapshot]:
        orders = self.client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, nested=True, limit=500))
        return [snapshot_order(o) for o in orders]

    def get_orders_since(self, after: datetime) -> list[OrderSnapshot]:
        orders = self.client.get_orders(GetOrdersRequest(status=QueryOrderStatus.ALL, after=after, nested=True, limit=500))
        return [snapshot_order(o) for o in orders]

    def get_order(self, order_id: str) -> OrderSnapshot:
        return snapshot_order(self.client.get_order_by_id(order_id))

    def get_asset(self, symbol: str) -> AssetInfo:
        a = self.client.get_asset(symbol)
        return AssetInfo(symbol=symbol, asset_class=_enum_val(a.asset_class), tradable=bool(a.tradable),
                         fractionable=bool(getattr(a, "fractionable", False)), shortable=bool(getattr(a, "shortable", False)),
                         status=_enum_val(a.status))

    def get_clock(self) -> ClockInfo:
        c = self.client.get_clock()
        return ClockInfo(is_open=bool(c.is_open), next_open=c.next_open, next_close=c.next_close)

    # ------------------------------------------------------------ writes
    def submit(self, approval: RiskApproval) -> OrderSnapshot:
        verify_approval(approval)
        if approval.mode != self.mode:
            raise RuntimeError(f"approval issued for {approval.mode} mode but broker is {self.mode}")
        it = approval.intent
        side = OrderSide.BUY if it.side == "buy" else OrderSide.SELL
        common = dict(symbol=it.symbol, qty=it.qty, side=side, time_in_force=TimeInForce.GTC,
                      client_order_id=it.client_order_id)
        extra: dict = {}
        if it.side == "buy" and not it.is_crypto:
            # Stocks: the stop-loss (and target) legs travel with the entry as a bracket / OTO order.
            extra["stop_loss"] = StopLossRequest(stop_price=round_price(it.symbol, float(it.stop_price)))
            if it.target_price:
                extra["order_class"] = OrderClass.BRACKET
                extra["take_profit"] = TakeProfitRequest(limit_price=round_price(it.symbol, float(it.target_price)))
            else:
                extra["order_class"] = OrderClass.OTO
        if it.order_type == "limit":
            req = LimitOrderRequest(limit_price=round_price(it.symbol, float(it.limit_price)), **common, **extra)
        else:
            req = MarketOrderRequest(**common, **extra)
        log.info("submitting %s %s x%s (%s) [%s]", it.side, it.symbol, it.qty, it.order_type, self.mode)
        return snapshot_order(self.client.submit_order(req))

    def submit_protective_stop(self, approval: RiskApproval) -> OrderSnapshot:
        """Crypto cannot use bracket legs, so its stop is a separate GTC stop-limit sell."""
        verify_approval(approval)
        it = approval.intent
        if it.side != "sell" or it.stop_price is None:
            raise RuntimeError("protective stop needs a sell intent with a stop price")
        stop = round_price(it.symbol, float(it.stop_price))
        limit = round_price(it.symbol, stop * 0.99)  # limit slightly below so it fills through fast moves
        req = StopLimitOrderRequest(symbol=it.symbol, qty=it.qty, side=OrderSide.SELL, time_in_force=TimeInForce.GTC,
                                    stop_price=stop, limit_price=limit, client_order_id=it.client_order_id)
        return snapshot_order(self.client.submit_order(req))

    def cancel_order(self, order_id: str) -> None:
        self.client.cancel_order_by_id(order_id)

    def cancel_all_orders(self) -> int:
        res = self.client.cancel_orders()
        return len(res or [])

    def close_all_positions(self) -> list:
        return list(self.client.close_all_positions(cancel_orders=True) or [])


class TradeUpdateStream:
    """Alpaca trade-update websocket in a background thread; handler(event, OrderSnapshot, extra)."""

    def __init__(self, settings: Settings, handler: Callable[[str, OrderSnapshot, dict], None]):
        from alpaca.trading.stream import TradingStream
        self._stream = TradingStream(settings.alpaca_api_key, settings.alpaca_secret_key, paper=not settings.live_mode)
        self._handler = handler
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        async def on_update(data):
            try:
                extra = {"price": _f(getattr(data, "price", None)), "qty": _f(getattr(data, "qty", None)),
                         "position_qty": _f(getattr(data, "position_qty", None)), "timestamp": getattr(data, "timestamp", None)}
                self._handler(_enum_val(data.event), snapshot_order(data.order), extra)
            except Exception:
                log.exception("trade update handler failed")
        self._stream.subscribe_trade_updates(on_update)
        self._thread = threading.Thread(target=self._stream.run, name="trade-updates", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        try:
            self._stream.stop()
        except Exception:
            pass

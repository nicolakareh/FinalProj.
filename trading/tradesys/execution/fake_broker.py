"""In-memory broker with the same interface as AlpacaBroker, for tests and dry runs.
Market orders fill instantly at the current price; bracket legs and protective stops
fill when `set_price` crosses them, producing trade-update events in `events`.
"""
from __future__ import annotations

import itertools
from datetime import datetime

from ..common import is_crypto, utcnow
from ..risk.manager import RiskApproval, verify_approval
from .models import AccountSnapshot, AssetInfo, ClockInfo, OrderSnapshot, PositionSnapshot


class FakeBroker:
    def __init__(self, cash: float = 10_000.0, prices: dict[str, float] | None = None, mode: str = "paper",
                 market_open: bool = True, daytrade_count: int = 0):
        self.mode = mode
        self.cash = cash
        self.last_equity = cash
        self.prices: dict[str, float] = dict(prices or {})
        self.positions: dict[str, PositionSnapshot] = {}
        self.orders: dict[str, OrderSnapshot] = {}
        self.events: list[tuple[str, OrderSnapshot, dict]] = []
        self.market_open = market_open
        self.daytrade_count = daytrade_count
        self.blocked = False
        self._ids = itertools.count(1)
        self.assets: dict[str, AssetInfo] = {}

    # ------------------------------------------------------------ helpers
    def _new_id(self) -> str:
        return f"ord-{next(self._ids)}"

    def _emit(self, event: str, order: OrderSnapshot, price: float | None = None, qty: float | None = None) -> None:
        self.events.append((event, order, {"price": price, "qty": qty, "position_qty": self.positions.get(order.symbol).qty if order.symbol in self.positions else 0.0, "timestamp": utcnow()}))

    def _fill(self, order: OrderSnapshot, price: float) -> None:
        order.status = "filled"
        order.filled_qty = order.qty
        order.filled_avg_price = price
        order.filled_at = utcnow()
        sym = order.symbol
        if order.side == "buy":
            self.cash -= order.qty * price
            pos = self.positions.get(sym)
            if pos is None:
                self.positions[sym] = PositionSnapshot(sym, order.qty, price, price, order.qty * price, order.qty * price,
                                                       0.0, 0.0, order.qty, "long", "crypto" if is_crypto(sym) else "us_equity")
            else:
                total = pos.qty + order.qty
                pos.avg_entry_price = (pos.avg_entry_price * pos.qty + price * order.qty) / total
                pos.qty = total
                pos.qty_available = total
                pos.cost_basis = pos.avg_entry_price * total
        else:
            self.cash += order.qty * price
            pos = self.positions.get(sym)
            if pos is not None:
                pos.qty -= order.qty
                pos.qty_available = pos.qty
                if pos.qty <= 1e-9:
                    del self.positions[sym]
                else:
                    pos.cost_basis = pos.avg_entry_price * pos.qty
            # a filled leg cancels its sibling
            for other in self.orders.values():
                if other.symbol == sym and other.is_open and other.side == "sell" and other.id != order.id:
                    other.status = "canceled"
                    self._emit("canceled", other)
        self._emit("fill", order, price, order.qty)
        self.set_price(sym, price, _check=False)

    # ------------------------------------------------------------ prices
    def set_price(self, symbol: str, price: float, _check: bool = True) -> None:
        self.prices[symbol] = price
        pos = self.positions.get(symbol)
        if pos is not None:
            pos.current_price = price
            pos.market_value = pos.qty * price
            pos.unrealized_pl = (price - pos.avg_entry_price) * pos.qty
            pos.unrealized_intraday_pl = pos.unrealized_pl
        if not _check:
            return
        for order in list(self.orders.values()):
            if order.symbol != symbol or not order.is_open or order.side != "sell":
                continue
            if order.order_type in ("stop", "stop_limit") and order.stop_price is not None and price <= order.stop_price:
                self._fill(order, price)
            elif order.order_type == "limit" and order.limit_price is not None and price >= order.limit_price:
                self._fill(order, order.limit_price)

    # ------------------------------------------------------------ reads
    def get_account(self) -> AccountSnapshot:
        equity = self.cash + sum(p.market_value for p in self.positions.values())
        return AccountSnapshot(cash=self.cash, equity=equity, last_equity=self.last_equity, buying_power=self.cash,
                               non_marginable_buying_power=self.cash, multiplier=1.0, daytrade_count=self.daytrade_count,
                               trading_blocked=self.blocked, account_blocked=self.blocked)

    def get_positions(self) -> list[PositionSnapshot]:
        return list(self.positions.values())

    def get_open_orders(self) -> list[OrderSnapshot]:
        return [o for o in self.orders.values() if o.is_open]

    def get_orders_since(self, after: datetime) -> list[OrderSnapshot]:
        return list(self.orders.values())

    def get_order(self, order_id: str) -> OrderSnapshot:
        return self.orders[order_id]

    def get_asset(self, symbol: str) -> AssetInfo:
        return self.assets.get(symbol) or AssetInfo(symbol, "crypto" if is_crypto(symbol) else "us_equity", True,
                                                    is_crypto(symbol), False, "active")

    def get_clock(self) -> ClockInfo:
        return ClockInfo(self.market_open, None, None)

    # ------------------------------------------------------------ writes
    def submit(self, approval: RiskApproval) -> OrderSnapshot:
        verify_approval(approval)
        it = approval.intent
        price = self.prices.get(it.symbol, it.reference_price)
        order = OrderSnapshot(self._new_id(), it.client_order_id, it.symbol, it.side, it.qty, 0.0, None, it.order_type,
                              "new", asset_class="crypto" if it.is_crypto else "us_equity", limit_price=it.limit_price,
                              created_at=utcnow())
        self.orders[order.id] = order
        if it.side == "buy" and not it.is_crypto:
            stop = OrderSnapshot(self._new_id(), f"{it.client_order_id}-sl", it.symbol, "sell", it.qty, 0.0, None,
                                 "stop", "held", stop_price=it.stop_price, created_at=utcnow())
            self.orders[stop.id] = stop
            order.legs.append(stop)
            order.order_class = "oto"
            if it.target_price:
                tp = OrderSnapshot(self._new_id(), f"{it.client_order_id}-tp", it.symbol, "sell", it.qty, 0.0, None,
                                   "limit", "held", limit_price=it.target_price, created_at=utcnow())
                self.orders[tp.id] = tp
                order.legs.append(tp)
                order.order_class = "bracket"
        self._emit("new", order)
        if it.order_type == "market" or (it.side == "buy" and it.limit_price and price <= it.limit_price):
            self._fill(order, price)
            for leg in order.legs:
                leg.status = "new"
        return order

    def submit_protective_stop(self, approval: RiskApproval) -> OrderSnapshot:
        verify_approval(approval)
        it = approval.intent
        order = OrderSnapshot(self._new_id(), it.client_order_id, it.symbol, "sell", it.qty, 0.0, None, "stop_limit",
                              "new", stop_price=it.stop_price, limit_price=it.stop_price * 0.99, created_at=utcnow(),
                              asset_class="crypto")
        self.orders[order.id] = order
        self._emit("new", order)
        return order

    def cancel_order(self, order_id: str) -> None:
        o = self.orders[order_id]
        if o.is_open:
            o.status = "canceled"
            self._emit("canceled", o)

    def cancel_all_orders(self) -> int:
        n = 0
        for o in list(self.orders.values()):
            if o.is_open:
                self.cancel_order(o.id)
                n += 1
        return n

    def close_all_positions(self) -> list:
        self.cancel_all_orders()
        closed = []
        for sym, pos in list(self.positions.items()):
            order = OrderSnapshot(self._new_id(), f"close-{sym}", sym, "sell", pos.qty, 0.0, None, "market", "new")
            self.orders[order.id] = order
            self._fill(order, self.prices.get(sym, pos.current_price))
            closed.append(order)
        return closed

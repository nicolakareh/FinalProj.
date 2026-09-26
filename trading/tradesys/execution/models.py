"""Broker-agnostic order and account models so the risk layer never depends on SDK types."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime

from ..common import asset_class_for, is_crypto

OPTION_SYMBOL_RE = re.compile(r"^[A-Z]{1,6}\d{6}[CP]\d{8}$")


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    side: str                       # buy | sell
    qty: float
    order_type: str                 # market | limit
    reference_price: float          # latest price used for risk arithmetic
    source_id: str
    reason: str
    client_order_id: str
    stop_price: float | None = None
    target_price: float | None = None
    limit_price: float | None = None
    trade_id: int | None = None

    @property
    def asset_class(self) -> str:
        return asset_class_for(self.symbol)

    @property
    def is_crypto(self) -> bool:
        return is_crypto(self.symbol)

    @property
    def entry_price(self) -> float:
        return float(self.limit_price or self.reference_price)

    @property
    def notional(self) -> float:
        return float(self.qty) * self.entry_price

    @property
    def looks_like_option(self) -> bool:
        return bool(OPTION_SYMBOL_RE.match(self.symbol))

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class AccountSnapshot:
    cash: float
    equity: float
    last_equity: float
    buying_power: float
    non_marginable_buying_power: float | None = None
    multiplier: float = 1.0
    shorting_enabled: bool = False
    pattern_day_trader: bool = False
    daytrade_count: int = 0
    trading_blocked: bool = False
    account_blocked: bool = False
    currency: str = "USD"

    @property
    def spendable_cash(self) -> float:
        """Cash that can be spent without borrowing."""
        vals = [self.cash]
        if self.non_marginable_buying_power is not None:
            vals.append(self.non_marginable_buying_power)
        return max(0.0, min(vals))


@dataclass
class PositionSnapshot:
    symbol: str
    qty: float
    avg_entry_price: float
    current_price: float
    market_value: float
    cost_basis: float
    unrealized_pl: float
    unrealized_intraday_pl: float = 0.0
    qty_available: float | None = None
    side: str = "long"
    asset_class: str = "us_equity"

    @property
    def sellable_qty(self) -> float:
        return float(self.qty if self.qty_available is None else self.qty_available)


@dataclass
class OrderSnapshot:
    id: str
    client_order_id: str
    symbol: str
    side: str
    qty: float
    filled_qty: float
    filled_avg_price: float | None
    order_type: str
    status: str
    order_class: str = "simple"
    stop_price: float | None = None
    limit_price: float | None = None
    legs: list["OrderSnapshot"] = field(default_factory=list)
    created_at: datetime | None = None
    filled_at: datetime | None = None
    asset_class: str = "us_equity"

    @property
    def is_open(self) -> bool:
        return self.status in {"new", "accepted", "pending_new", "accepted_for_bidding", "held", "partially_filled",
                               "pending_replace", "calculated"}

    @property
    def remaining_qty(self) -> float:
        return max(0.0, float(self.qty) - float(self.filled_qty or 0.0))

    def leg_ids(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for leg in self.legs:
            if leg.order_type in ("stop", "stop_limit"):
                out["stop_order_id"] = leg.id
            elif leg.order_type == "limit":
                out["target_order_id"] = leg.id
        return out


@dataclass
class AssetInfo:
    symbol: str
    asset_class: str
    tradable: bool
    fractionable: bool
    shortable: bool = False
    status: str = "active"


@dataclass
class ClockInfo:
    is_open: bool
    next_open: datetime | None
    next_close: datetime | None

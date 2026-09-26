"""Strategy interface. Strategies are long-only by construction: they may say
"buy" (with a stop and target) or "sell" (close). They never size positions;
the risk layer does that.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass
class Intent:
    action: str                 # "buy" | "sell"
    stop_price: float | None = None
    target_price: float | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if self.action not in ("buy", "sell"):
            raise ValueError("Intent.action must be 'buy' or 'sell' (long-only system)")
        if self.action == "buy" and (self.stop_price is None or self.stop_price <= 0):
            raise ValueError("every buy intent must carry a stop price")


@dataclass
class PositionState:
    qty: float
    entry_price: float
    stop_price: float | None
    target_price: float | None
    entry_index: int = 0
    bars_held: int = 0


class Strategy(ABC):
    name: str = "base"
    description: str = ""
    default_params: dict[str, Any] = {}

    def __init__(self, **params: Any):
        self.params: dict[str, Any] = {**self.default_params, **params}
        unknown = set(params) - set(self.default_params)
        if unknown:
            raise ValueError(f"{self.name}: unknown params {sorted(unknown)}")

    @property
    @abstractmethod
    def warmup(self) -> int:
        """Bars needed before on_bar can produce a signal."""

    @abstractmethod
    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add indicator columns. Must only use past data (rolling/ewm), never future bars."""

    @abstractmethod
    def on_bar(self, df: pd.DataFrame, i: int, position: PositionState | None) -> Intent | None:
        """Evaluate bar i (df is the prepared frame). Return an Intent or None."""

    def p(self, key: str) -> Any:
        return self.params[key]

    @staticmethod
    def _stop_target(close: float, atr_val: float, atr_mult: float, target_r: float) -> tuple[float, float]:
        stop = close - atr_mult * atr_val
        if stop <= 0 or stop >= close:
            stop = close * 0.97
        target = close + target_r * (close - stop)
        return round(stop, 6), round(target, 6)

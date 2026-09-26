"""Structured trade signal shared by strategies, Discord callers and the news monitor."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Direction(str, Enum):
    LONG = "long"     # open or add to a long position
    SHORT = "short"   # recorded for the caller's track record, never executed
    CLOSE = "close"   # exit an existing long


@dataclass
class Signal:
    source_id: str          # e.g. strategy:sma_crossover, discord:1234, news:momentum
    source_kind: str        # strategy | discord | news
    source_name: str
    symbol: str
    direction: Direction
    timestamp: datetime
    entry: float | None = None
    stop: float | None = None
    target: float | None = None
    raw_text: str = ""
    meta: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "source_id": self.source_id, "source_kind": self.source_kind, "source_name": self.source_name,
            "symbol": self.symbol, "direction": self.direction.value, "timestamp": self.timestamp.isoformat(),
            "entry": self.entry, "stop": self.stop, "target": self.target, "raw_text": self.raw_text,
        }

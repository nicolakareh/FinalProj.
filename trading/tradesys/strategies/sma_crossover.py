from __future__ import annotations

import numpy as np
import pandas as pd

from ..data.indicators import atr, sma
from .base import Intent, PositionState, Strategy


class SMACrossover(Strategy):
    name = "sma_crossover"
    description = "Buy when the fast SMA crosses above the slow SMA, exit on the cross back down. ATR stop."
    default_params = {"fast": 20, "slow": 50, "atr_period": 14, "atr_mult": 2.0, "target_r": 3.0}

    @property
    def warmup(self) -> int:
        return int(max(self.p("slow"), self.p("atr_period"))) + 2

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["fast"] = sma(out["close"], int(self.p("fast")))
        out["slow"] = sma(out["close"], int(self.p("slow")))
        out["atr"] = atr(out, int(self.p("atr_period")))
        return out

    def on_bar(self, df: pd.DataFrame, i: int, position: PositionState | None) -> Intent | None:
        if i < 1:
            return None
        fast, slow = df["fast"].iloc[i], df["slow"].iloc[i]
        pfast, pslow = df["fast"].iloc[i - 1], df["slow"].iloc[i - 1]
        if np.isnan(fast) or np.isnan(slow) or np.isnan(pfast) or np.isnan(pslow):
            return None
        if position is None and fast > slow and pfast <= pslow:
            close, a = float(df["close"].iloc[i]), float(df["atr"].iloc[i])
            if np.isnan(a):
                return None
            stop, target = self._stop_target(close, a, float(self.p("atr_mult")), float(self.p("target_r")))
            return Intent("buy", stop, target, f"SMA{self.p('fast')} crossed above SMA{self.p('slow')}")
        if position is not None and fast < slow and pfast >= pslow:
            return Intent("sell", reason="SMA cross down")
        return None

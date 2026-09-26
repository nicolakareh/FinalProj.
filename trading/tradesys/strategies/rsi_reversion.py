from __future__ import annotations

import numpy as np
import pandas as pd

from ..data.indicators import atr, rsi, sma
from .base import Intent, PositionState, Strategy


class RSIReversion(Strategy):
    name = "rsi_reversion"
    description = ("In an uptrend (close above the trend SMA), buy when RSI climbs back out of oversold; "
                   "exit when RSI recovers past exit_rsi. ATR stop.")
    default_params = {"rsi_period": 14, "oversold": 30, "exit_rsi": 55, "trend_sma": 200, "atr_period": 14,
                      "atr_mult": 2.0, "target_r": 2.0}

    @property
    def warmup(self) -> int:
        return int(max(self.p("trend_sma"), self.p("rsi_period"), self.p("atr_period"))) + 2

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["rsi"] = rsi(out["close"], int(self.p("rsi_period")))
        out["trend"] = sma(out["close"], int(self.p("trend_sma")))
        out["atr"] = atr(out, int(self.p("atr_period")))
        return out

    def on_bar(self, df: pd.DataFrame, i: int, position: PositionState | None) -> Intent | None:
        if i < 1:
            return None
        r, pr, trend, close = (df["rsi"].iloc[i], df["rsi"].iloc[i - 1], df["trend"].iloc[i], float(df["close"].iloc[i]))
        if np.isnan(r) or np.isnan(pr) or np.isnan(trend):
            return None
        oversold = float(self.p("oversold"))
        if position is None and pr < oversold <= r and close > trend:
            a = float(df["atr"].iloc[i])
            if np.isnan(a):
                return None
            stop, target = self._stop_target(close, a, float(self.p("atr_mult")), float(self.p("target_r")))
            return Intent("buy", stop, target, f"RSI back above {oversold:g} in uptrend")
        if position is not None and r > float(self.p("exit_rsi")):
            return Intent("sell", reason=f"RSI above {self.p('exit_rsi')}")
        return None

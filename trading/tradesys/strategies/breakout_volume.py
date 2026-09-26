from __future__ import annotations

import numpy as np
import pandas as pd

from ..data.indicators import atr, sma, volume_spike
from .base import Intent, PositionState, Strategy


class BreakoutVolume(Strategy):
    name = "breakout_volume"
    description = "Buy a close above the prior N-bar high on a volume spike; exit on a close below the N-bar SMA."
    default_params = {"lookback": 20, "volume_window": 20, "volume_ratio": 1.8, "atr_period": 14, "atr_mult": 2.5,
                      "target_r": 2.5}

    @property
    def warmup(self) -> int:
        return int(max(self.p("lookback"), self.p("volume_window"), self.p("atr_period"))) + 2

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        lb = int(self.p("lookback"))
        out["prior_high"] = out["high"].shift(1).rolling(lb, min_periods=lb).max()
        out["trend"] = sma(out["close"], lb)
        out["atr"] = atr(out, int(self.p("atr_period")))
        vs = volume_spike(out["volume"], int(self.p("volume_window")), ratio_threshold=float(self.p("volume_ratio")),
                          z_threshold=99.0)
        out["volume_ratio"] = vs["volume_ratio"]
        return out

    def on_bar(self, df: pd.DataFrame, i: int, position: PositionState | None) -> Intent | None:
        close = float(df["close"].iloc[i])
        prior_high, trend, vr = df["prior_high"].iloc[i], df["trend"].iloc[i], df["volume_ratio"].iloc[i]
        if np.isnan(prior_high) or np.isnan(trend) or np.isnan(vr):
            return None
        if position is None and close > prior_high and vr >= float(self.p("volume_ratio")):
            a = float(df["atr"].iloc[i])
            if np.isnan(a):
                return None
            stop, target = self._stop_target(close, a, float(self.p("atr_mult")), float(self.p("target_r")))
            return Intent("buy", stop, target, f"breakout above {self.p('lookback')}-bar high on {vr:.1f}x volume")
        if position is not None and close < trend:
            return Intent("sell", reason="close below trend SMA")
        return None

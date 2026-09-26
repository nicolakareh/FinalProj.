"""Position sizing shared by the backtester and the live executor.

qty is the largest size such that
  * the loss at the stop is at most risk_pct% of the capital cap, and
  * notional fits inside both the remaining capital cap and the available cash
    (so nothing is ever bought on margin).
"""
from __future__ import annotations

import math


def position_size(capital_cap: float, risk_pct: float, entry: float, stop: float, cash_available: float,
                  deployed_notional: float, fractional: bool, min_notional: float = 1.0,
                  max_notional_pct: float = 100.0) -> float:
    if entry <= 0 or stop <= 0 or stop >= entry:
        return 0.0
    risk_per_unit = entry - stop
    max_risk = capital_cap * risk_pct / 100.0
    qty_by_risk = max_risk / risk_per_unit
    remaining_cap = max(0.0, capital_cap - deployed_notional)
    max_notional = min(remaining_cap, max(0.0, cash_available), capital_cap * max_notional_pct / 100.0)
    qty_by_notional = max_notional / entry
    qty = min(qty_by_risk, qty_by_notional)
    if fractional:
        qty = math.floor(qty * 1e6) / 1e6
    else:
        qty = float(math.floor(qty))
    if qty <= 0 or qty * entry < min_notional:
        return 0.0
    return qty

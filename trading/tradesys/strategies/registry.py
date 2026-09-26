from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

from ..common import canonical_json, sha256_of
from .base import Strategy
from .breakout_volume import BreakoutVolume
from .rsi_reversion import RSIReversion
from .sma_crossover import SMACrossover

STRATEGIES: dict[str, type[Strategy]] = {
    SMACrossover.name: SMACrossover,
    RSIReversion.name: RSIReversion,
    BreakoutVolume.name: BreakoutVolume,
}


def list_strategies() -> list[tuple[str, str, dict[str, Any]]]:
    return [(name, cls.description, dict(cls.default_params)) for name, cls in STRATEGIES.items()]


def create_strategy(name: str, params: dict[str, Any] | None = None) -> Strategy:
    if name not in STRATEGIES:
        raise KeyError(f"unknown strategy {name!r}; known: {sorted(STRATEGIES)}")
    return STRATEGIES[name](**(params or {}))


def strategy_code_hash(name: str, params: dict[str, Any] | None = None) -> str:
    """Hash of the strategy's source, the base class and its params. Approval is tied to this,
    so editing a strategy silently invalidates its approval until it is backtested again."""
    cls = STRATEGIES[name]
    src = Path(inspect.getfile(cls)).read_text()
    base_src = Path(inspect.getfile(Strategy)).read_text()
    return sha256_of(src, base_src, canonical_json(params or {}))

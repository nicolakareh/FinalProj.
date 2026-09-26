import numpy as np
import pandas as pd
import pytest

from alpaca.data.timeframe import TimeFrameUnit

from tradesys.data.market_data import MarketData, _normalize_bars, parse_timeframe, periods_per_year, timeframe_seconds
from tests.conftest import make_settings


def test_parse_timeframe():
    assert parse_timeframe("1Day").unit == TimeFrameUnit.Day
    assert parse_timeframe("15Min").amount == 15
    assert parse_timeframe("4Hour").unit == TimeFrameUnit.Hour
    with pytest.raises(ValueError):
        parse_timeframe("2Fortnight")
    assert timeframe_seconds("1Hour") == 3600
    assert periods_per_year("1Day", "SPY") == 252
    assert periods_per_year("1Day", "BTC/USD") == 365
    assert periods_per_year("1Hour", "BTC/USD") == 365 * 24


def test_normalize_bars_multiindex():
    idx = pd.MultiIndex.from_tuples(
        [("AAPL", pd.Timestamp("2024-01-02", tz="UTC")), ("AAPL", pd.Timestamp("2024-01-03", tz="UTC"))],
        names=["symbol", "timestamp"])
    raw = pd.DataFrame({"open": [1, 2], "high": [2, 3], "low": [0.5, 1.5], "close": [1.5, 2.5],
                        "volume": [10, 20], "trade_count": [1, 2], "vwap": [1.4, 2.4]}, index=idx)
    df = _normalize_bars(raw, "AAPL")
    assert list(df.columns) == ["open", "high", "low", "close", "volume", "trade_count", "vwap"]
    assert df.index.tz is not None and len(df) == 2


def test_history_cache_roundtrip(tmp_path, monkeypatch):
    settings = make_settings(tmp_path)
    md = MarketData(settings)
    idx = pd.date_range("2022-01-01", periods=900, freq="D", tz="UTC")
    fake = pd.DataFrame({"open": 1.0, "high": 2.0, "low": 0.5, "close": np.linspace(1, 2, 900), "volume": 100.0,
                         "trade_count": 1.0, "vwap": 1.0}, index=idx)
    calls = {"n": 0}

    def fake_get_bars(symbol, timeframe="1Day", start=None, end=None, limit=None):
        calls["n"] += 1
        return fake[(fake.index >= start) & (fake.index <= end)]

    monkeypatch.setattr(md, "get_bars", fake_get_bars)
    end = idx[-1].to_pydatetime()
    df1 = md.get_history("SPY", "1Day", years=2, end=end)
    df2 = md.get_history("SPY", "1Day", years=2, end=end)
    assert calls["n"] == 1  # second call came from the cache
    assert len(df1) == len(df2) > 700
    assert (md.cache_dir / "SPY_1Day.csv").exists()

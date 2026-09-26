import numpy as np
import pandas as pd

from tradesys.data.indicators import add_indicators, atr, ema, rolling_vwap, rsi, session_vwap, sma, volume_spike


def make_df(n=300, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    high = close + rng.uniform(0.1, 1.0, n)
    low = close - rng.uniform(0.1, 1.0, n)
    open_ = close + rng.normal(0, 0.3, n)
    vol = rng.uniform(1000, 2000, n)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": vol}, index=idx)


def test_sma_matches_manual():
    df = make_df()
    s = sma(df["close"], 20)
    assert np.isnan(s.iloc[18])
    assert abs(s.iloc[19] - df["close"].iloc[:20].mean()) < 1e-9
    assert abs(s.iloc[-1] - df["close"].iloc[-20:].mean()) < 1e-9


def test_ema_warmup_and_shape():
    df = make_df()
    e = ema(df["close"], 9)
    assert e.isna().sum() == 8
    assert len(e) == len(df)


def test_rsi_bounds_and_extremes():
    up = pd.Series(np.arange(1, 60, dtype=float))
    assert rsi(up, 14).dropna().min() > 99.0
    down = pd.Series(np.arange(60, 1, -1, dtype=float))
    assert rsi(down, 14).dropna().max() < 1.0
    df = make_df()
    r = rsi(df["close"], 14)
    assert r.dropna().between(0, 100).all()
    assert r.iloc[:14].isna().all()


def test_atr_positive():
    df = make_df()
    a = atr(df, 14)
    assert a.iloc[:13].isna().all()
    assert (a.dropna() > 0).all()


def test_rolling_and_session_vwap():
    df = make_df(n=48)
    rv = rolling_vwap(df, 5)
    typical = (df["high"] + df["low"] + df["close"]) / 3
    manual = (typical * df["volume"]).iloc[:5].sum() / df["volume"].iloc[:5].sum()
    assert abs(rv.iloc[4] - manual) < 1e-9
    sv = session_vwap(df)
    # first bar of a session equals its own typical price
    assert abs(sv.iloc[0] - typical.iloc[0]) < 1e-9
    # the session resets at the New York day boundary (05:00 UTC in January)
    ny_dates = df.index.tz_convert("America/New_York").date
    first_of_second_day = list(ny_dates).index(sorted(set(ny_dates))[1])
    assert abs(sv.iloc[first_of_second_day] - typical.iloc[first_of_second_day]) < 1e-9


def test_volume_spike_flags_outlier():
    df = make_df()
    vol = df["volume"].copy()
    vol.iloc[100] = vol.iloc[80:100].mean() * 5
    vs = volume_spike(vol, window=20)
    assert bool(vs["volume_spike"].iloc[100])
    assert not bool(vs["volume_spike"].iloc[99])
    assert vs["volume_ratio"].iloc[100] > 4


def test_add_indicators_columns():
    df = add_indicators(make_df())
    for col in ["sma_20", "sma_50", "sma_200", "ema_9", "ema_21", "rsi_14", "atr_14", "vwap_rolling",
                "vwap_session", "volume_ratio", "volume_z", "volume_spike"]:
        assert col in df.columns
    assert df["sma_200"].notna().sum() == len(df) - 199
